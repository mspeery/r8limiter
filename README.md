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
# Run locally
docker compose up --build

# Test a request
curl -X POST "http://localhost:8000/allow?user_id=test"
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
rate-limiter/
  app/
    main.py
    limiter.py
    models.py
    admin.py
    config.py
  tests/
    test_core.py
  deploy/
    docker/Dockerfile
    docker/docker-compose.yml
    helm/Chart.yaml
    helm/values.yaml
    helm/templates/*.yaml
  ops/
    k6-smoke.js
    dashboards/prometheus-rules.yaml
    dashboards/grafana.json
  README.md
```
