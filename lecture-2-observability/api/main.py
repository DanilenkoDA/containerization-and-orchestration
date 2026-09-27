"""Подопытный HTTP-сервис api для лабы по наблюдаемости.

Эндпоинты: /health, /fail, /slow, /load, /metrics.
Метрики RED, JSON-логи с trace_id, OpenTelemetry-трейсы.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "api")
OTLP_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://jaeger:4318",
)


class JsonFormatter(logging.Formatter):
    """Структурированные JSON-логи с trace_id текущего спана."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        span = trace.get_current_span()
        ctx = span.get_span_context() if span is not None else None
        trace_id = format(ctx.trace_id, "032x") if ctx and ctx.is_valid else ""

        payload: dict[str, Any] = {
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
            "logger": record.name,
            "service": SERVICE_NAME,
            "trace_id": trace_id,
        }
        if hasattr(record, "endpoint"):
            payload["endpoint"] = record.endpoint
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> logging.Logger:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    LoggingInstrumentor().instrument(set_logging_format=False)
    return logging.getLogger(SERVICE_NAME)


def setup_tracing() -> trace.Tracer:
    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)
    # OTLP/HTTP: Jaeger all-in-one слушает 4318; путь /v1/traces добавляет экспортёр.
    endpoint = OTLP_ENDPOINT.rstrip("/")
    if not endpoint.endswith("/v1/traces"):
        endpoint = f"{endpoint}/v1/traces"
    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(SERVICE_NAME)


log = setup_logging()
tracer = setup_tracing()

REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
ERRORS = Counter(
    "http_errors_total",
    "Total HTTP 5xx responses",
    ["endpoint"],
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    HTTPXClientInstrumentor().instrument()
    log.info("api started", extra={"endpoint": "startup"})
    yield
    log.info("api stopped", extra={"endpoint": "shutdown"})


app = FastAPI(title="api", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app, excluded_urls="metrics,health")


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    endpoint = request.url.path
    method = request.method
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        elapsed = time.perf_counter() - start
        REQUESTS.labels(method=method, endpoint=endpoint, status=str(status_code)).inc()
        LATENCY.labels(method=method, endpoint=endpoint).observe(elapsed)
        if status_code >= 500:
            ERRORS.labels(endpoint=endpoint).inc()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/fail")
async def fail() -> Response:
    with tracer.start_as_current_span("fail-op") as span:
        span.set_status(Status(StatusCode.ERROR, "intentional failure"))
        span.record_exception(RuntimeError("intentional failure"))
        log.error("intentional failure on /fail", extra={"endpoint": "/fail"})
        return JSONResponse(
            status_code=500,
            content={"error": "intentional failure"},
        )


@app.get("/slow")
async def slow() -> dict[str, Any]:
    delay = random.uniform(1.0, 3.0)
    with tracer.start_as_current_span("slow-op") as span:
        span.set_attribute("delay_seconds", delay)
        log.info("sleeping on /slow", extra={"endpoint": "/slow"})
        await asyncio.sleep(delay)
    return {"slept": delay}


@app.get("/load")
async def load(request: Request) -> dict[str, Any]:
    """Пачка внутренних запросов к себе — поднимает RPS."""
    base = str(request.base_url).rstrip("/")
    paths = ["/health", "/health", "/slow", "/fail", "/health"]
    results: list[int] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for path in paths:
            r = await client.get(f"{base}{path}")
            results.append(r.status_code)
    log.info("load burst done", extra={"endpoint": "/load"})
    return {"calls": len(results), "statuses": results}


@app.get("/metrics")
async def metrics() -> Response:
    return PlainTextResponse(
        generate_latest().decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
    )
