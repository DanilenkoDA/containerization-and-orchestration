# Monitoring stack (Lab 2)

Helm-конфиги для Prometheus и Grafana. Namespace: `monitoring`.  
Сервис `api` ожидается в `lab2` (scrape: `api.lab2.svc.cluster.local:8000/metrics`).

## Prerequisites

- Работающий кластер (minikube / kind / …), `kubectl` и `Helm 3`
- Release `api` в namespace `lab2` (под Running, `/metrics` отдаётся)
- Репозитории чартов:

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
```

- Namespace:

```bash
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
```

- Для Grafana: утилита `envsubst` (пакет `gettext`)

## Переменные окружения

Нужны только для учётки Grafana. В git пароль не кладём — Secret собирается из env.

| Переменная | Обязательна | Описание |
|------------|-------------|----------|
| `GRAFANA_ADMIN_USER` | да | Логин админа (обычно `admin`) |
| `GRAFANA_ADMIN_PASSWORD` | да | Пароль админа |

```bash
export GRAFANA_ADMIN_USER=admin
export GRAFANA_ADMIN_PASSWORD='your-secure-password'
```

Prometheus отдельных env не требует.

## Prometheus

```bash
helm upgrade --install prometheus prometheus-community/prometheus \
  -n monitoring \
  -f monitoring/prometheus-values.yaml
```

Проверка scrape:

```bash
kubectl port-forward -n monitoring svc/prometheus-server 9090:80
```

UI → Status → Targets → job `api` = **UP**.  
Или PromQL: `up{job="api"}` → `1`.

Обновление values:

```bash
helm upgrade prometheus prometheus-community/prometheus \
  -n monitoring \
  -f monitoring/prometheus-values.yaml
```

Файл на диске сам в кластер не попадает — только через `helm upgrade`.

## Grafana

Сначала Secret из шаблона и env, потом Helm (порядок важен):

```bash
export GRAFANA_ADMIN_USER=admin
export GRAFANA_ADMIN_PASSWORD='your-secure-password'

envsubst < monitoring/grafana-admin-secret.yaml.tpl | kubectl apply -f -

helm upgrade --install grafana grafana/grafana \
  -n monitoring \
  -f monitoring/grafana-values.yaml
```

Вход:

```bash
kubectl port-forward -n monitoring svc/grafana 3000:80
```

http://localhost:3000 — логин/пароль из переменных выше.

Datasource Prometheus провижинится из values (`http://prometheus-server`). В UI: Connections → Data sources → Save & test.

Смена пароля: обновить env → снова `envsubst | kubectl apply` → рестарт пода Grafana при необходимости:

```bash
kubectl rollout restart deployment/grafana -n monitoring
```


