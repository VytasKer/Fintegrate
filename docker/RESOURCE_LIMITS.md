# Docker Resource Limits Configuration

## Overview
Resource limits prevent containers from consuming all host resources, ensuring:
- **Multi-container stability** (no single service starves others)
- **Predictable performance** (consistent resource allocation)
- **Production readiness** (prevents OOM kills, CPU throttling)

## Resource Allocation Strategy

### Application Services (FastAPI)
**Customer Service (2 instances)**: 1 CPU / 512 MB per instance
- Limits: 1.0 CPU, 512 MB memory
- Reservations: 0.5 CPU, 256 MB memory
- Rationale: API services need moderate resources, 2 instances for load balancing

### Event Consumers (3 instances)
**Event Consumers**: 0.5 CPU / 256 MB per instance
- Limits: 0.5 CPU, 256 MB memory
- Reservations: 0.25 CPU, 128 MB memory
- Rationale: Lightweight message processors, minimal CPU/memory footprint

### Infrastructure Services

**PostgreSQL**: 2 CPUs / 1024 MB
- Limits: 2.0 CPU, 1024 MB memory
- Reservations: 1.0 CPU, 512 MB memory
- Rationale: Database needs more resources for queries, indexing, connections

**RabbitMQ**: 1 CPU / 512 MB
- Limits: 1.0 CPU, 512 MB memory
- Reservations: 0.5 CPU, 256 MB memory
- Rationale: Message broker needs moderate resources for queue management

**Redis**: 0.5 CPU / 256 MB
- Limits: 0.5 CPU, 256 MB memory
- Reservations: 0.25 CPU, 128 MB memory
- Rationale: In-memory cache with minimal resource needs (rate limiting state only)

**Traefik Gateway**: 0.5 CPU / 256 MB
- Limits: 0.5 CPU, 256 MB memory
- Reservations: 0.25 CPU, 128 MB memory
- Rationale: Reverse proxy with minimal overhead (routing, rate limiting)

### ETL/Orchestration Services

**Airflow Webserver**: 1 CPU / 1024 MB
- Limits: 1.0 CPU, 1024 MB memory
- Reservations: 0.5 CPU, 512 MB memory
- Rationale: UI server needs more memory for web framework and session management

**Airflow Scheduler**: 1 CPU / 1024 MB
- Limits: 1.0 CPU, 1024 MB memory
- Reservations: 0.5 CPU, 512 MB memory
- Rationale: DAG execution engine needs resources for task scheduling and monitoring

## Total Resource Requirements

### Maximum (Limits)
- **Total CPUs**: 10.0 CPUs
  - Application: 2.0 CPUs (2 customer service instances)
  - Consumers: 1.5 CPUs (3 event consumer instances)
  - Infrastructure: 3.5 CPUs (postgres 2.0 + rabbitmq 1.0 + redis 0.5)
  - Gateway: 0.5 CPUs (traefik)
  - Orchestration: 2.5 CPUs (airflow webserver 1.0 + scheduler 1.0, init excluded)

- **Total Memory**: 6.25 GB
  - Application: 1.0 GB (2 × 512 MB)
  - Consumers: 0.75 GB (3 × 256 MB)
  - Infrastructure: 1.75 GB (postgres 1024 MB + rabbitmq 512 MB + redis 256 MB)
  - Gateway: 0.25 GB (traefik 256 MB)
  - Orchestration: 2.5 GB (airflow webserver 1024 MB + scheduler 1024 MB, init excluded)

### Minimum (Reservations)
- **Total CPUs**: 5.0 CPUs
- **Total Memory**: 3.125 GB

## Verification Commands

### Check Current Resource Usage
```powershell
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
```

### Inspect Container Resource Config
```powershell
docker inspect fintegrate-customer-service-1 | Select-String -Pattern "Memory|NanoCpus" -Context 0,1
```

### Monitor Resource Constraints
```powershell
# Watch resource usage in real-time
docker stats
```

## Expected Performance (Observed)

Based on current deployment:
- **Airflow Webserver**: 60-90% CPU (initialization), 500-600 MB memory
- **Airflow Scheduler**: 1-5% CPU (idle), 400-500 MB memory
- **Customer Service**: 0.1% CPU (idle), 60-70 MB memory per instance
- **PostgreSQL**: 0.5-1% CPU (idle), 30-40 MB memory
- **RabbitMQ**: 0.1% CPU (idle), 120-130 MB memory
- **Redis**: 0.3% CPU (idle), 4-5 MB memory
- **Traefik**: 0% CPU (idle), 27-28 MB memory
- **Event Consumers**: 0% CPU (idle), 18-20 MB memory per instance

All services operating well within limits. Airflow webserver temporarily exceeds CPU limit during initialization (normal behavior).

## Production Tuning Recommendations

### For Higher Load
- **Customer Service**: Scale to 3-4 instances (horizontal scaling)
- **PostgreSQL**: Increase to 4 CPUs / 2 GB memory
- **RabbitMQ**: Monitor queue depth, increase to 2 CPUs / 1 GB if needed

### For Resource-Constrained Environments
- **Reduce Airflow**: 0.5 CPU / 512 MB each (webserver + scheduler)
- **Single Customer Service**: Remove one instance (no load balancing)
- **PostgreSQL**: Reduce to 1 CPU / 512 MB (development only)

## Implementation Date
November 5, 2025 - Resource limits added to complete "Dockerize all services" DevOps topic.

## Related Files
- `docker/docker-compose.yml`: Resource configuration in `deploy.resources` sections
- Docker Compose documentation: https://docs.docker.com/compose/compose-file/deploy/#resources
