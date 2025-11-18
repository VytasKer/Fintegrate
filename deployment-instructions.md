# Fintegrate Deployment Instructions

## Overview

Fintegrate is a microservices-based financial integration platform deployed across two environments:

- **Local Development**: Docker Compose with load-balanced customer service instances
- **Production-like**: Minikube Kubernetes cluster with service isolation

## Architecture

```
Client → Traefik Gateway → Customer Service (FastAPI) → PostgreSQL
                    ↓
              RabbitMQ → Event Consumers
                    ↓
               AML Service
```

**Services**:
- `customer-service`: Main REST API (load balanced in Docker, single replica in K8s)
- `event-consumer-default/swadia/test001`: Consumer-specific event processors
- `aml-service`: Anti-Money Laundering processing
- `postgres`: Database
- `rabbitmq`: Message broker
- `redis`: Rate limiting and caching
- `prometheus/grafana`: Monitoring stack

## Environment Setup

### Prerequisites

- Docker Desktop with Kubernetes disabled
- Minikube installed
- PowerShell 5.1+
- Git with VS Code GitHub integration
- Python 3.11+ virtual environment

### Directory Structure

```
fintegrate/
├── services/                 # Source code
│   ├── customer_service/
│   ├── event_consumer/
│   └── shared/
├── docker/                   # Docker Compose files
│   ├── docker-compose.yml
│   └── Dockerfile.*
├── kubernetes/               # K8s manifests and scripts
│   ├── mng-fngrt.ps1        # Management script
│   ├── deployments/
│   └── .last_build_timestamp
├── database/                 # SQL migrations
└── requirements.txt
```

## Deployment Workflows

### 1. Initial Setup

#### Option A: Automated (Recommended)

```powershell
# 1. Start Minikube cluster
cd kubernetes
.\mng-fngrt.ps1
# Select option 2: Full Deploy

# This will:
# - Start Minikube
# - Build all images in Minikube Docker context
# - Deploy all services
# - Establish port-forwards
```

#### Option B: Manual Setup

```powershell
# 1. Start Minikube
minikube start

# 2. Enable metrics
minikube addons enable metrics-server

# 3. Switch to Minikube Docker context
& minikube docker-env --shell powershell | Invoke-Expression

# 4. Build images from project root
cd ..
docker build -f docker/Dockerfile.customer_service -t fintegrate-customer-service:v1.0 .
docker build -f docker/Dockerfile.event_consumer -t fintegrate-event-consumer:v1.0 .
docker build -f docker/Dockerfile.aml_service -t aml_service:latest .

# 5. Deploy Kubernetes resources
cd kubernetes
kubectl apply -f rbac/
kubectl apply -f configmaps/
kubectl apply -f secrets/
kubectl apply -f statefulsets/
Start-Sleep -Seconds 10
kubectl apply -f services/
kubectl apply -f deployments/
kubectl apply -f hpa/

# 6. Start port-forwards
kubectl port-forward svc/customer-service 8001:8000 &
kubectl port-forward svc/postgres 5436:5432 &
kubectl port-forward svc/rabbitmq 15673:15672 &
kubectl port-forward svc/rabbitmq 5673:5672 &
```

### 2. Code Change Deployment Example

**Scenario**: Fix bug in `services/customer_service/routes.py` (remove sorted() call causing TypeError)

#### Phase 1: Local Development Testing

```powershell
# 1. Make code changes in VS Code
# Edit services/customer_service/routes.py
# Remove sorted() call from customer_tags processing

# 2. Test in Docker Compose environment
cd docker
docker-compose up -d --build customer_service_1 customer_service_2

# 3. Verify fix works
curl -H "X-API-Key: test_consumer_key" http://localhost:8000/customer/data

# 4. Run tests
cd ..
python -m pytest tests/ -v

# 5. Commit changes
# In VS Code: Source Control panel
# Stage changes: services/customer_service/routes.py
# Commit message: "Fix TypeError in customer tags sorting"
# Push to main branch
```

#### Phase 2: Update Version

```powershell
# 1. Update VERSION file
# Increment version: 1.0.0 → 1.0.1
notepad VERSION

# 2. Update CHANGELOG.md
# Add new section with changes
notepad CHANGELOG.md

# 3. Commit version bump
git add VERSION CHANGELOG.md
git commit -m "Bump version to 1.0.1"
git tag v1.0.1
git push origin main --tags
```

#### Phase 3: Deploy to Minikube

##### Option A: Automated Smart Update

```powershell
cd kubernetes
.\mng-fngrt.ps1
# Select option 10: Update Service Images

# This will:
# - Check if source files changed since last build
# - Rebuild images only if needed
# - Update .last_build_timestamp
# - Restart all deployments
```

##### Option B: Manual Update

```powershell
# 1. Switch to Minikube Docker context
& minikube docker-env --shell powershell | Invoke-Expression

# 2. Rebuild updated images
cd ..
docker build -f docker/Dockerfile.customer_service -t fintegrate-customer-service:v1.0 .

# 3. Force rollout restart
cd kubernetes
kubectl rollout restart deployment/customer-service

# 4. Wait for readiness
kubectl wait --for=condition=ready pod -l app=customer-service --timeout=60s
```

##### Option C: Full Redeploy

```powershell
cd kubernetes
.\mng-fngrt.ps1
# Select option 2: Full Deploy

# This rebuilds all images regardless of changes
# Use when multiple services changed or for clean state
```

### 3. Environment Management

#### Local Docker Compose

```powershell
cd docker

# Start all services
docker-compose up -d

# Start specific services
docker-compose up -d customer_service_1 customer_service_2

# Rebuild and restart
docker-compose up -d --build --force-recreate customer_service_1

# View logs
docker-compose logs -f customer_service_1

# Stop all
docker-compose down
```

#### Minikube Operations

```powershell
cd kubernetes
.\mng-fngrt.ps1

# Available options:
# 1. Start Cluster          - Quick start with persistence
# 2. Full Deploy           - Complete rebuild and deploy
# 3. Restart Services      - Restart pods (no image rebuild)
# 4. Stop Cluster (Safe)   - Stop with database backup
# 5. Hard Reset           - Delete everything
# 6. View Logs            - Service logs
# 7. Open Dashboards      - Launch monitoring UIs
# 8. Run Migrations       - Database schema updates
# 9. Cluster Status       - Health and resource info
# 10. Update Images       - Smart rebuild based on source changes
```

## Image Management

### Current Image Structure

**Minikube Docker Context**:
- `fintegrate-customer-service:v1.0` - Production customer service
- `fintegrate-event-consumer:v1.0` - Production event consumer
- `aml_service:latest` - AML processing service

**Local Docker Context**:
- `fintegrate-customer_service_1:latest` - Dev instance 1
- `fintegrate-customer_service_2:latest` - Dev instance 2
- `fintegrate-event_consumer:latest` - Dev event consumer

### Image Cleanup

```powershell
# Remove dangling images
docker image prune -f

# Remove specific old images
docker rmi $(docker images -f "dangling=true" -q)

# Clean Minikube images
& minikube docker-env --shell powershell | Invoke-Expression
docker system prune -f
```

### Version Strategy

**Simple Approach**: Use `VERSION` file and Git tags.

- **VERSION file**: Contains current version (e.g., `1.0.0`)
- **Git tags**: `git tag v1.0.0` for releases
- **CHANGELOG.md**: Documents what changed

**Image Tags**:
- Development: `latest`
- Production: `v1.0.0` (matches VERSION file)

**Process**:
1. Make code changes
2. Test locally
3. Update VERSION file (patch: 1.0.0 → 1.0.1, minor: 1.0.0 → 1.1.0, major: 1.0.0 → 2.0.0)
4. Update CHANGELOG.md
5. Commit and tag: `git tag v1.0.1`
6. Deploy with new version tag

## Troubleshooting

### Common Issues

#### 1. Image Not Updated in Minikube

**Problem**: Code changes not reflected after deployment
**Cause**: Images built in local Docker, not Minikube context

**Solution**:
```powershell
# Always switch context before building
& minikube docker-env --shell powershell | Invoke-Expression
cd ..
docker build -f docker/Dockerfile.customer_service -t fintegrate-customer-service:v1.0 .
```

#### 2. Pods Stuck in Pending/CrashLoopBackOff

**Check pod status**:
```powershell
kubectl get pods -o wide
kubectl describe pod <pod-name>
kubectl logs <pod-name> --previous
```

**Common causes**:
- Image pull errors: Verify image exists in Minikube context
- Resource constraints: Check memory/CPU limits
- Config errors: Validate ConfigMaps/Secrets

#### 3. Port Conflicts

**Local development ports**:
- Customer API: `localhost:8000-8001`
- RabbitMQ UI: `localhost:15672`
- PostgreSQL: `localhost:5435`

**Minikube ports** (via port-forward):
- Customer API: `localhost:8001`
- RabbitMQ UI: `localhost:15673`
- PostgreSQL: `localhost:5436`

#### 4. Database Connection Issues

**Verify connections**:
```powershell
# Local
psql -h localhost -p 5435 -U fintegrate_user -d fintegrate_db

# Minikube
kubectl exec -it postgres-0 -- psql -U fintegrate_user -d fintegrate_db
```

### Monitoring and Logs

#### Service Logs

```powershell
# Docker Compose
docker-compose logs -f customer_service_1

# Minikube
cd kubernetes
.\mng-fngrt.ps1
# Select option 6: View Logs
```

#### Health Checks

```powershell
# API health
curl http://localhost:8001/events/health

# Pod health
kubectl get pods
kubectl top pods

# Resource usage
kubectl describe nodes
```

## CI/CD Integration

### GitHub Actions (Future)

```yaml
# .github/workflows/deploy.yml
name: Deploy to Minikube
on:
  push:
    branches: [ main ]
    paths:
      - 'services/**'
      - 'docker/**'
      - 'kubernetes/**'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: |
          pip install -r requirements.txt
          python -m pytest

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to Minikube
        run: |
          # Minikube setup and deployment commands
```

## Backup and Recovery

### Database Backups

```powershell
cd kubernetes
.\mng-fngrt.ps1
# Select option 4: Stop Cluster (Safe)
# Automatic backup created in kubernetes/backups/
```

### Cluster Recovery

```powershell
# Hard reset and rebuild
cd kubernetes
.\mng-fngrt.ps1
# Select option 5: Hard Reset
# Then option 2: Full Deploy
```

## Performance Optimization

### Resource Limits

**Development** (docker-compose.yml):
```yaml
customer_service_1:
  deploy:
    resources:
      limits:
        memory: 512M
        cpus: '0.5'
```

**Production** (kubernetes/deployments/):
```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "200m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

### Scaling

```powershell
# Horizontal scaling
kubectl scale deployment customer-service --replicas=3

# Vertical scaling (update deployment YAML)
kubectl apply -f deployments/customer-service.yaml
```

## Security Considerations

- API keys stored in Kubernetes secrets
- Database passwords hashed
- Network policies isolate services
- RBAC controls access
- Rate limiting via Redis/Traefik

## Maintenance Tasks

### Regular Cleanup

```powershell
# Weekly
docker system prune -f
kubectl delete pods --field-selector=status.phase=Succeeded

# Monthly
cd kubernetes
.\mng-fngrt.ps1
# Option 4: Safe stop with backup
# Option 2: Full redeploy
```

### Updates

- Monitor Kubernetes versions
- Update base images quarterly
- Review and rotate API keys
- Update dependencies regularly

---

**Note**: Always test deployments in local Docker environment before Minikube deployment. Use the management script (`mng-fngrt.ps1`) for automated operations to ensure consistency.</content>
<parameter name="filePath">deployment-instructions.md