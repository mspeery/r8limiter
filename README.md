# r8limiter 🚦
*A distributed, Redis-backed rate limiting service with observability and Kubernetes-ready deployments.*

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Build](https://img.shields.io/github/actions/workflow/status/<your-username>/r8limiter/ci.yml?branch=main)](https://github.com/<your-username>/r8limiter/actions)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://hub.docker.com/r/<your-username>/r8limiter)
[![Docs](https://img.shields.io/badge/docs-available-brightgreen)](#)

---

## ✨ Features
- **Token Bucket Algorithm** – fair per-user throttling
- **Distributed State** – Redis-backed with atomic Lua scripts
- **Admin API** – stats, top offenders, per-user tokens
- **Observability** – Prometheus metrics, structured JSON logs
- **Kubernetes-Ready** – Helm charts, HPA, and dashboards

## 🚀 Quickstart
```bash
# 1) Start stack
docker-compose up --build

# 2) Hit the endpoint (allows up to capacity, then throttles)
curl -i -X POST "http://localhost:8000/allow?user_id=a&resource=read&cost=1"

# 3) Idempotent call (won’t double-spend within TTL)
curl -i -X POST "http://localhost:8000/allow?user_id=a&resource=pay&cost=1" \
  -H "Idempotency-Key: 12345"
curl -i -X POST "http://localhost:8000/allow?user_id=a&resource=pay&cost=1" \
  -H "Idempotency-Key: 12345"
```

## 🔧 API Spec
  - `POST /allow?user_id=<id>&resource=<opt>` -> `{ "allowed": bool, "remaining": int, "reset_ms": int }`
  - `GET /admin/stats?limit=50` (top offenders, totals)
  - `PUT /admin/policy`

## 🎯 Goals 
  - SLO: p99 < 10ms for in-memory
  - < 25ms Redis
  - correctness beats raw speed.

## 📂 Repo Layout
```
r8limiter/
├─ app/
│  ├─ __init__.py
│  ├─ limiter.lua
│  ├─ main.py
│  ├─ requirements.txt
│  └─ settings.py
├─ tests/
│  ├─ __init__.py
│  └─ test_rate_limiter_redis.py
├─ (TBD) deploy/
│  ├─ docker/Dockerfile
│  ├─ docker/docker-compose.yml
│  ├─ helm/Chart.yaml
│  ├─ helm/values.yaml
│  └─ helm/templates/*.yaml
├─ (TBD) ops/
│  ├─ k6-smoke.js
│  ├─ dashboards/prometheus-rules.yaml
│  └─ dashboards/grafana.json
├─ docker-compose.yml
├─ Dockerfile
└─ README.md
```
## 📝 Design Doc
[Rate Limiter Design](https://docs.google.com/document/d/1i_ah88lqwMl0kePaDvHtoqmIu5Zeh3Vv/edit?usp=sharing&ouid=107042604300121152772&rtpof=true&sd=true)


## 🗂 Legacy Code and Tests
Located in the /legacy directory
```
legacy/
├─ app/
│  └─ rate_limiter.py
├─ tests/
│  └─ test_rate_limiter.py
```

```bash
# Run locally (Uvicorn)
uvicorn app.main:app --reload

# Run locally (FastAPI Dev)
cd app/
fastapi dev main.py

# Run locally (FUTURE CASE)
docker compose up --build

# Test a request
curl -X POST "http://localhost:8000/allow?user_id=test"

# Run Unit Tests
pytest -q
```