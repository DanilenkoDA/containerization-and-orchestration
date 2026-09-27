# Handoff — Лаба 2 (observability)

Документ для нового AI-агента с пустым контекстом. Читай сначала `AGENTS.md` в корне репозитория — он обязателен.

Студент пишет по-русски. Аудитория — опытный devops (IaC/GitOps/Terragrunt); не пересказывать базу Docker/K8s.

---

## Обязательные правила работы (`AGENTS.md`)

- Наставник, не генератор решений. **Не выдавать полное решение лабы.**
- Поэтапно, **один этап за раз**. После этапа — **2–3 вопроса на понимание механизмов**.
- Дальше только если ответы **без ошибок**; иначе разъяснить и спросить снова.
- Исключение: подопытный сервис `api` можно генерировать целиком (уже сгенерирован).
- Инфраструктура (Helm, Prometheus, Loki, Jaeger, алерты) — только с обучением по шагам.

---

## Цель лабы

Полный стек мониторинга одного HTTP-сервиса в **Kubernetes через Helm** (не docker compose):

1. Метрики: Prometheus + Grafana (RED)
2. Логи: Loki + агент (Alloy/Promtail/Fluent Bit) + Grafana
3. Трейсы: OpenTelemetry → Jaeger
4. Алерты: Alertmanager + Karma, 3 критичных правила

Источник истины: `lecture-2-observability/lab.md`.

---

## Прогресс

| Этап | Статус | Комментарий |
|------|--------|-------------|
| 0. Сервис `api` | ✅ Готово | Код сгенерирован агентом |
| 1. Кластер + деплой `api` | ✅ Готово | Вопросы понимания закрыты |
| 2a. Prometheus + scrape `/metrics` | ⏳ **Текущий** | Grafana ещё не ставить |
| 2b. Grafana + RED-дашборд | ⏸️ После 2a | Студент явно хочет порядок как в lab.md: сначала Prometheus, потом Grafana |
| 3. Loki + агент | ⏸️ | |
| 4. Jaeger + OTel | ⏸️ | В Deployment пока нет env для OTLP |
| 5. Alertmanager + Karma | ⏸️ | |

**Важно:** студент поправил агента — не предлагать сразу `kube-prometheus-stack`. Сначала отдельный Prometheus, scrape, Target UP; **затем** отдельно Grafana.

---

## Что уже есть в окружении

- **Кластер:** minikube, работает.
- **Namespace:** `lab2`.
- **Helm release:** `api` (chart `charts/api`, revision 1).
- **Под:** `api-…` Running 1/1; **Service:** `api` ClusterIP порт **8000**.
- **Образ:** `lab2-api:1.0.0` (собирали через `minikube image build` из‑за старого Docker client; Docker Desktop могли обновить — уточнить при необходимости).
- Проверено студентом: `curl /health` → `{"status":"ok"}`, `/metrics` отдаёт `http_requests_total` и др.

Prometheus / Grafana / Loki / Jaeger — **ещё не установлены** (`helm list -A` показывает только `api`).

---

## Структура репозитория (лаба 2)

```
lecture-2-observability/
  lab.md                 # задание
  README.md              # лекция
  api/                   # FastAPI-сервис
    main.py
    Dockerfile
    requirements.txt
  charts/api/            # Helm-чарт приложения (скелет helm create, values подправлены)
  handoff.md             # этот файл
```

### Сервис `api` (важное для мониторинга)

- Эндпоинты: `/health`, `/fail`, `/slow`, `/load`, `/metrics`.
- Метрики RED: `http_requests_total`, `http_errors_total`, `http_request_duration_seconds`.
- JSON-логи в stdout с полем `trace_id`.
- OTel: спан `slow-op` на `/slow`, error status на `/fail`.
- OTLP по умолчанию: `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318` (в кластере пока Jaeger нет — на этапе 4 добавить env в Deployment/values).
- Порт контейнера: **8000**.

### Чарт `charts/api`

В `values.yaml` уже выставлено:

- `image.repository: lab2-api`, `tag: 1.0.0`, `pullPolicy: IfNotPresent`
- `service.port: 8000`
- probes на `/health`

Остальной скелет `helm create` (ingress/hpa/httproute выключены или лежат мёртвым грузом). **Env для OTel в deployment.yaml нет** — добавить на этапе трейсов.

Имя Service после install: `api` (не `api-api`).

---

## Этап 1 — что студент уже понял (закрыто)

1. Лаба в k8s, не compose: чтобы тренировать **service discovery** и агентов как **DaemonSet**, окружение ближе к прод.
2. У minikube свой store образов ≠ Docker на хосте → нужен `minikube image build` / `load` / `docker-env`.
3. Service нужен из‑за эфемерности IP пода (клиенты/scrape ломаются, не «сам приклад»).

---

## Что делать новому агенту прямо сейчас

### Этап 2a — Prometheus only

1. Кратко напомнить цель этапа (pull-модель, scrape `/metrics`).
2. Вести установку `prometheus-community/prometheus` через Helm в `lab2` (или отдельный ns — на выбор, но согласовать DNS цели).
3. Настроить scrape на `api.lab2.svc.cluster.local:8000` path `/metrics` (ключ values — смотреть актуальный `helm show values`; часто `extraScrapeConfigs` / serverFiles).
4. **Не** ставить Grafana, Loki, Jaeger, Alertmanager на этом шаге.
5. Критерий готовности: Prometheus UI → Status → Targets → job к `api` = **UP**.
6. Задать 2–3 вопроса на понимание (черновик из прошлого хода, можно адаптировать):
   - pull vs push и обнаружение «сервис умер»;
   - зачем стабильный Service для scrape;
   - зачем `rate()` на счётчиках, а не сырое значение.
7. Только после верных ответов → этап 2b (Grafana + datasource + RED-дашборд + нагрузка `/load` `/fail` `/slow`).

Не выдавать готовый полный `values.yaml` на весь стек. Минимум для текущего шага + объяснение *почему*.

### Дальнейшие этапы (не начинать заранее)

- **2b:** `grafana/grafana`, datasource → Prometheus, дашборд RED.
- **3:** Loki + DaemonSet-агент; не путать Loki (хранилище) и коллектор.
- **4:** Jaeger all-in-one, env `OTEL_EXPORTER_OTLP_ENDPOINT`, проверка `/slow` и `/fail`, связь лог↔trace по `trace_id`.
- **5:** 3 критичных алерта, Alertmanager, Karma; firing через кнопки сервиса.

---

## Технические ловушки, уже встреченные

1. **Старый Docker client (20.10 / API 1.41)** vs новый демон minikube (min API 1.44) после `eval $(minikube docker-env)` → ошибка `client version 1.41 is too old`. Обход: `minikube image build -t lab2-api:1.0.0 .` или обновить Docker Desktop.
2. `eval $(minikube docker-env)` переключает CLI на демон minikube только в текущей shell; сброс: `eval $(minikube docker-env -u)`.
3. Port-forward на 8000 мог быть занят — использовать другой локальный порт или убить старый forward.
4. Не путать `kube-prometheus-stack` (Operator + ServiceMonitor) с простым чартом `prometheus` — студент выбрал путь **как в lab.md**: сначала Prometheus, потом Grafana.

---

## Полезные команды (ориентир)

```bash
# api
kubectl get pods,svc -n lab2
kubectl port-forward -n lab2 svc/api 8000:8000
curl -s localhost:8000/health
curl -s localhost:8000/metrics | head

# образ в minikube
minikube image ls | grep lab2-api
minikube image build -t lab2-api:1.0.0 ./api

# helm api
helm upgrade --install api ./charts/api -n lab2
helm list -n lab2
```

---

## Как студенту стартовать нового агента

В новом чате примерно так:

> Работай по `AGENTS.md`. Читай `lecture-2-observability/handoff.md` и продолжи Лабу 2 с текущего шага (Prometheus, без Grafana).

---

## Дата снимка состояния

2026-09-27 (~22:30 MSK): `api` Running в `lab2`, мониторинг-стек не установлен, следующий шаг — Helm Prometheus + scrape.
