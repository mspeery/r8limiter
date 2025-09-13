# r8limiter Helm Chart

This chart deploys r8limiter with:
- Deployment (readiness/liveness probes on **/healthz** by default)
- Service (ClusterIP)
- ConfigMap (policy file mounted at `/config/policy.yaml`)
- Secret (Redis URL)
- **HPA** (CPU or optional custom metric via metrics adapter)
- **PodDisruptionBudget**
- **ServiceMonitor** (Prometheus Operator)
- Optional **Grafana dashboard**

## Quickstart (kind/minikube)
```bash
cd helm
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring --create-namespace
helm install r8limiter ./r8limiter   --set redis.auth.password=changeme
```

## Values (highlights)
- `probes.path`: default `/livez`
- `hpa.enabled=true` and `hpa.cpu.targetAverageUtilization=70`
- `hpa.custom.enabled=true` requires **prometheus-adapter** exposing a `requests_per_second` pods metric
- `serviceMonitor.enabled=true` requires **Prometheus Operator**
- `grafanaDashboard.enabled=true` creates a ConfigMap suitable for Grafana sidecar discovery

## Acceptance checks
1. **Install works & scrapeable**  
   - `kubectl port-forward svc/r8limiter-r8limiter 8000:8000` and then `curl localhost:8000/metrics`
2. **Scaling replicas**  
   - `kubectl scale deploy r8limiter-r8limiter --replicas=5`; limits remain enforced (state is in Redis)
3. **Chaos (delete a pod)**  
   - `kubectl delete pod -l app.kubernetes.io/name=r8limiter` → traffic continues without errors

## Helm tests
```bash
helm test r8limiter
```
