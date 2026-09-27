# Monitoring stack (Lab 2)

Helm-конфиги стека наблюдаемости. Namespace: `monitoring`.  
Сервис `api` — в `lab2` (`api.lab2.svc.cluster.local:8000`).

| Компонент | Роль | Values |
|-----------|------|--------|
| Prometheus | scrape `/metrics`, PromQL | `prometheus-values.yaml` |
| Grafana | UI: метрики + логи | `grafana-values.yaml` + Secret из tpl |
| Loki | хранилище логов (сам ничего не собирает) | `loki-values.yaml` |
| Promtail | DaemonSet: читает логи ноды → push в Loki | `promtail-values.yaml` |

Пока нет: Jaeger, Alertmanager, Karma (следующие этапы лабы).

## Prerequisites

- Кластер (minikube / kind / …), `kubectl`, `Helm 3`
- Release `api` в `lab2` (под Running, `/metrics` и stdout-логи)
- Репозитории:

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
```

- Namespace:

```bash
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
```

- Для Grafana: `envsubst` (пакет `gettext`)

## Переменные окружения

Только для учётки Grafana. Пароль в git не кладём — Secret из env.

| Переменная | Обязательна | Описание |
|------------|-------------|----------|
| `GRAFANA_ADMIN_USER` | да | Логин админа (обычно `admin`) |
| `GRAFANA_ADMIN_PASSWORD` | да | Пароль админа |

```bash
export GRAFANA_ADMIN_USER=admin
export GRAFANA_ADMIN_PASSWORD='your-secure-password'
```

Prometheus / Loki / Promtail отдельных env не требуют.

## Порядок установки

1. Prometheus  
2. Grafana (+ Secret)  
3. Loki  
4. Promtail  
5. Проверка: Targets UP → Explore Loki после `/fail`

Файл values сам в кластер не попадает — только через `helm upgrade`.

---

## Prometheus

```bash
helm upgrade --install prometheus prometheus-community/prometheus \
  -n monitoring \
  -f monitoring/prometheus-values.yaml
```

Scrape `api`: job `api` → `api.lab2.svc.cluster.local:8000/metrics`  
(Alertmanager и pushgateway в values выключены.)

```bash
kubectl port-forward -n monitoring svc/prometheus-server 9090:80
```

UI → Status → Targets → job `api` = **UP**.  
PromQL: `up{job="api"}` → `1`.

```bash
helm upgrade prometheus prometheus-community/prometheus \
  -n monitoring \
  -f monitoring/prometheus-values.yaml
```

---

## Grafana

Сначала Secret, потом Helm:

```bash
export GRAFANA_ADMIN_USER=admin
export GRAFANA_ADMIN_PASSWORD='your-secure-password'

envsubst < monitoring/grafana-admin-secret.yaml.tpl | kubectl apply -f -

helm upgrade --install grafana grafana/grafana \
  -n monitoring \
  -f monitoring/grafana-values.yaml
```

```bash
kubectl port-forward -n monitoring svc/grafana 3000:80
```

http://localhost:3000 — логин/пароль из env выше.

Datasources из values (оба в том же ns):

| Name | URL |
|------|-----|
| Prometheus (default) | `http://prometheus-server` |
| Loki | `http://loki-gateway` |

В UI: Connections → Data sources → Save & test.

Если health check идёт на `localhost:3100` — это ручной datasource с дефолтом UI; поправь URL на `http://loki-gateway` или переустанови Grafana из values.

Смена пароля: обновить env → `envsubst | kubectl apply` → при необходимости:

```bash
kubectl rollout restart deployment/grafana -n monitoring
```

Логи в UI: **Explore** → datasource **Loki** → например `{namespace="lab2", app="api"}`.

---

## Loki

Хранилище логов. **Сам по нодам не ходит** — нужен агент (Promtail).

Режим: SingleBinary + filesystem + PVC (5Gi).  
`write` / `read` / `backend` обнулены (иначе chart требует object storage / `bucketNames`).  
Gateway включён — точка push/query для агента и Grafana.

```bash
helm upgrade --install loki grafana/loki \
  -n monitoring \
  -f monitoring/loki-values.yaml
```

Smoke-check:

```bash
kubectl port-forward -n monitoring svc/loki-gateway 3100:80
curl -s http://localhost:3100/loki/api/v1/labels
```

`/ready` на gateway может отдавать 404 (nginx) — для проверки лучше `/loki/api/v1/labels` или ready у сервиса `loki:3100`.

Ожидаемые ресурсы: StatefulSet `loki` (+ PVC), Deployment `loki-gateway`.

---

## Promtail

DaemonSet: читает файлы логов контейнеров на ноде (`/var/log/pods`) и пушит в Loki.

```bash
# Чарты: grafana/promtail — НЕ grafana/grafana
# (ошибка: helm install promtail grafana/grafana → второй Grafana под именем promtail)
helm upgrade --install promtail grafana/promtail \
  -n monitoring \
  -f monitoring/promtail-values.yaml
```

В values:

- client: `http://loki-gateway/loki/api/v1/push`
- фильтр namespace: только `lab2`
- pipeline: `docker` → `json` → labels (`level`, `service`) → `output: msg`  
  (на minikube с Docker json-file без `docker:{}` в Grafana виден «двойной» JSON в поле `log`)

Проверка:

```bash
kubectl get ds,pods -n monitoring -l app.kubernetes.io/name=promtail
kubectl logs -n monitoring -l app.kubernetes.io/name=promtail --tail=50
```

Дёрни api и смотри Explore:

```bash
kubectl port-forward -n lab2 svc/api 8000:8000
curl -s localhost:8000/fail
```

```logql
{namespace="lab2", app="api"} |= "fail"
```

Ожидай строку вроде `intentional failure on /fail`.  
`Exception while exporting Span batch` — OTel не достучится до Jaeger, пока его нет; для этапа логов это шум.

Chart Promtail помечен deprecated upstream’ом (миграция на Alloy) — для лабы ок.

---

## Быстрый статус

```bash
helm list -n monitoring
kubectl get pods,svc,pvc -n monitoring
```

Ожидаемые releases: `prometheus`, `grafana`, `loki`, `promtail` (+ `api` в `lab2`).
