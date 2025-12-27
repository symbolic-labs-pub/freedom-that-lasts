# Freedom That Lasts - Deployment Guide

## Quick Start with Docker

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 2GB RAM minimum
- 10GB disk space

### Build and Run

```bash
# Build the Docker image
docker build -t freedom-that-lasts:1.0.0-dev .

# Run with docker-compose
docker-compose up -d

# Check health
curl http://localhost:8080/health

# View metrics
curl http://localhost:9090/metrics

# View logs
docker-compose logs -f ftl
```

### Run with Monitoring Stack

```bash
# Start FTL + Prometheus + Grafana
docker-compose --profile monitoring up -d

# Access services:
# - FTL Health: http://localhost:8080/health
# - Prometheus: http://localhost:9091
# - Grafana: http://localhost:3000 (admin/admin)
```

## Production Deployment

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FTL_DB_PATH` | `/app/data/ftl.db` | Path to SQLite database |
| `FTL_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `FTL_JSON_LOGS` | `true` | Output logs in JSON format |

### Docker Run Example

```bash
docker run -d \
  --name ftl-app \
  -p 8080:8080 \
  -p 9090:9090 \
  -v ftl-data:/app/data \
  -e FTL_LOG_LEVEL=INFO \
  -e FTL_JSON_LOGS=true \
  --user 1000:1000 \
  --read-only=false \
  --security-opt no-new-privileges:true \
  freedom-that-lasts:1.0.0-dev
```

### Health Checks

The container exposes three health endpoints:

1. **Liveness**: `GET /health/live`
   - Returns 200 if process is running
   - Kubernetes liveness probe

2. **Readiness**: `GET /health/ready`
   - Returns 200 if database is accessible
   - Kubernetes readiness probe

3. **Detailed Health**: `GET /health`
   - Returns comprehensive health status
   - Includes FreedomHealth metrics

### Resource Limits

Recommended production settings:

```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 512M
    reservations:
      cpus: '0.5'
      memory: 256M
```

## Kubernetes Deployment

### Apply Manifests

```bash
# Create namespace
kubectl create namespace ftl

# Deploy FTL
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
kubectl apply -f deploy/k8s/pvc.yaml

# Check status
kubectl get pods -n ftl
kubectl get svc -n ftl

# View logs
kubectl logs -n ftl -l app=ftl -f
```

### Ingress Example

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ftl-ingress
  namespace: ftl
spec:
  rules:
  - host: ftl.example.com
    http:
      paths:
      - path: /health
        pathType: Prefix
        backend:
          service:
            name: ftl-service
            port:
              number: 8080
      - path: /metrics
        pathType: Prefix
        backend:
          service:
            name: ftl-service
            port:
              number: 9090
```

## Monitoring

### Prometheus Metrics

Access metrics at: `http://localhost:9090/metrics`

Key metrics:
- `ftl_events_appended_total` - Event store writes
- `ftl_command_duration_seconds` - Command processing latency
- `ftl_risk_level` - System risk level (0=GREEN, 1=YELLOW, 2=RED)
- `ftl_delegation_gini_coefficient` - Delegation concentration
- `ftl_feasible_set_empty_total` - Procurement halts

### Grafana Dashboards

1. Import dashboards from `deploy/grafana/dashboards/`
2. Configure Prometheus datasource
3. View real-time governance metrics

### Alerts

Alert rules are defined in `deploy/prometheus/alerts.yml`:

**Critical Alerts:**
- `FTLRiskLevelRed` - Governance risk is RED
- `FTLEventStoreDown` - Service unavailable
- `FTLHighErrorRate` - >10% command failures

**Warning Alerts:**
- `FTLOverdueReviews` - Laws need review
- `FTLEmptyFeasibleSet` - Procurement blocked
- `FTLHighDelegationConcentration` - Gini >0.70

## Security

### Container Security

The container follows security best practices:

- ✅ **Non-root user** (UID 1000)
- ✅ **Minimal base image** (python:3.11-slim)
- ✅ **No new privileges** (security opt)
- ✅ **Multi-stage build** (smaller attack surface)
- ✅ **Dependency pinning** (reproducible builds)
- ✅ **Health checks** (automatic recovery)

### Network Security

```bash
# Run with custom network
docker network create ftl-secure
docker run --network ftl-secure ...

# Limit exposure (internal only)
docker run -p 127.0.0.1:8080:8080 ...
```

## Backup and Restore

### Database Backup

```bash
# Backup SQLite database
docker exec ftl-app sqlite3 /app/data/ftl.db ".backup '/app/data/ftl-backup.db'"

# Copy to host
docker cp ftl-app:/app/data/ftl-backup.db ./backups/

# Automated backups with cron
0 2 * * * docker exec ftl-app sqlite3 /app/data/ftl.db ".backup '/app/data/backup-$(date +\%Y\%m\%d).db'"
```

### Restore from Backup

```bash
# Stop container
docker-compose stop ftl

# Restore database
docker cp ./backups/ftl-backup.db ftl-app:/app/data/ftl.db

# Restart
docker-compose start ftl
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker logs ftl-app

# Inspect container
docker inspect ftl-app

# Check health
docker exec ftl-app curl http://localhost:8080/health/ready
```

### Database locked

```bash
# Check for multiple processes
docker exec ftl-app ps aux

# Check database locks
docker exec ftl-app sqlite3 /app/data/ftl.db "PRAGMA database_list;"
```

### High memory usage

```bash
# Check memory stats
docker stats ftl-app

# Rebuild projections (can use memory)
docker exec ftl-app ftl admin rebuild-projections --db /app/data/ftl.db
```

## Scaling

### Horizontal Scaling

⚠️ **Not supported** - SQLite is single-writer.

For multi-instance deployments:
1. Migrate to PostgreSQL/MySQL
2. Implement distributed locking
3. Use message queue for commands

### Vertical Scaling

Increase container resources:

```yaml
resources:
  limits:
    cpus: '2.0'
    memory: 1024M
```

## Performance Tuning

### SQLite Optimization

```bash
# WAL mode (already enabled)
# Pragma settings (in event_store.py):
# - journal_mode=WAL
# - synchronous=NORMAL

# Compact database
docker exec ftl-app sqlite3 /app/data/ftl.db "VACUUM;"
```

### Application Tuning

Environment variables for tuning:

```bash
# Increase log level for less I/O
-e FTL_LOG_LEVEL=WARNING

# Disable JSON logs for better performance (dev only)
-e FTL_JSON_LOGS=false
```

## Support

For issues or questions:
- GitHub Issues: https://github.com/freedom-that-lasts/freedom-that-lasts/issues
- Documentation: https://freedom-that-lasts.readthedocs.io
