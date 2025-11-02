# Fintegrate AI Agent Instructions

## Project Overview
Fintegrate is a **learning-focused financial integration platform** simulating a microservices ecosystem with event-driven architecture. Core purpose: hands-on mastery of integration patterns, not production-grade financial software.

**Critical Philosophy**: Integration-first, not feature-first. Minimal viable domain with focus on reproducible patterns and infrastructure automation.

## Architecture at a Glance

```
Client (Postman) → Traefik Gateway → FastAPI Service → PostgreSQL
                                   ↓
                              RabbitMQ (per-consumer queues)
                                   ↓
                              Event Consumers
```

- **Customer Service** (`services/customer_service/`): FastAPI REST API with consumer-isolated multi-tenancy
- **Event Publisher** (`services/shared/event_publisher.py`): Transactional Outbox pattern publisher to RabbitMQ
- **Event Consumer** (`services/event_consumer/`): Subscribes to consumer-specific queues, confirms delivery via callback
- **API Gateway**: Traefik with IP and API-key rate limiting (Redis-backed)
- **Database**: PostgreSQL with manual SQL migrations (no ORM auto-migration)

## Response Format Standard (CRITICAL)

**Every API response** must use this structure:
```json
{
  "data": { /* actual response payload or {} */ },
  "detail": {
    "status_code": "200",
    "status_name": "OK",
    "status_description": "Success"  // Always "Success" on success, detailed error msg on failure
  }
}
```

Use `services/shared/response_handler.py`:
- `success_response(data_dict, status_code)` for 2xx responses
- `error_response(status_code, description)` for errors

**Never** return plain dicts or FastAPI defaults—all routes wrap responses through these helpers.

## Database Schema & Migration Rules

### Core Tables (see `database-context.txt` for full schema)
- `customers`: Master customer entity (UUID primary key)
- `customer_events`: **Append-only** event sourcing table with Transactional Outbox columns
- `customer_tags`: Key-value metadata (no foreign keys per 20251024_0900 migration)
- `customer_analytics`: Time-series snapshots (multiple per customer)
- `consumers`: Multi-tenant consumer definitions (queues named `customer_notification_{consumer.name}`)
- `consumer_api_keys`: API key authentication (one active key per consumer)
- `consumer_event_receipts`: Idempotency tracking for delivered events

### Migration Procedure
1. **Manual SQL only** (no Alembic until Phase 4). Files in `database/migrations/`
2. **Naming**: `YYYYMMDD_HHMM_description.sql`
3. **Idempotent**: Use `IF NOT EXISTS` / `IF EXISTS`
4. **No destructive ops**: Archive before structural changes
5. **Foreign keys removed** from base tables (flexibility over constraints)
6. **JSONB fields** for flexibility: `payload_json`, `metadata_json`, `tags_json`, `metrics_json`

**When asked to add columns**:
- Prefer JSONB extension fields over new columns unless critical for querying
- Always add indexes for UUID foreign keys and timestamp columns
- Update triggers if `updated_at` columns affected

## Event Flow & Transactional Outbox Pattern

### Publishing (from `routes.py` → `event_publisher.py`)
1. **Write to `customer_events`** with `publish_status='pending'`, `publish_try_count=1`
2. **Attempt RabbitMQ publish** to exchange `customer_events` with routing key `customer.{event_type}.{consumer_name}`
3. **On success**: Update `publish_status='published'`, `published_at=now()`
4. **On failure**: Keep `pending`, log `publish_failure_reason`
5. **Non-blocking**: API returns 201 even if publish fails

### Retry via Admin Endpoints
- `POST /events/resend`: Republish pending events (publish retries)
- `POST /events/redeliver`: Republish published-but-not-delivered events (delivery retries)
- Both support `period_in_days`, `max_try_count`, `event_types` filters

### Delivery Confirmation
- Consumer calls `POST /events/confirm-delivery` with `event_id`, `status` ('received'/'processed'/'failed')
- Writes to `consumer_event_receipts` (idempotency: duplicate confirmations return 200)
- Updates `customer_events.deliver_status='delivered'`

## API Authentication & Rate Limiting

### API Key Validation (`middleware.py`)
- **Header**: `X-API-Key: <consumer_api_key>`
- Validates against `consumer_api_keys` table (bcrypt hash)
- Attaches `consumer` object to `request.state` for tenant isolation
- **All customer operations filtered by `consumer_id`** (security-critical pattern)

### Rate Limiting (Two Layers)
1. **Traefik (IP-based)**: 100 req/min globally (anti-DDoS)
2. **Application (API-key)**: 50 req/min per consumer (Redis-backed, fail-open if Redis down)

**Testing config** in `docker-compose.yml`:
```yaml
RATE_LIMIT_API_KEY_PER_MINUTE: 50
RATE_LIMIT_API_KEY_BURST: 500
```

## RabbitMQ Patterns

### Queue Naming
- Main queue: `customer_notification_{consumer_name}`
- DLQ: `customer_notification_{consumer_name}_DLQ`
- Exchange: `customer_events` (topic exchange)
- Routing keys: `customer.{event_type}.{consumer_name}` (e.g., `customer.creation.consumer_test001`)

### Event Types (use `_` not `.`)
- `customer_creation`
- `customer_deletion`
- `customer_status_change`
- `consumer_created` (system events)

### DLQ Configuration
```python
queue_arguments = {
    'x-dead-letter-exchange': 'customer_events',
    'x-dead-letter-routing-key': f'customer.dlq.{consumer_name}',
    'x-message-ttl': 86400000,  # 24 hours
    'x-max-length': 100000
}
```

## Development Workflow

### Local Setup
```powershell
# Database (port 5435 not 5432)
# Connection: localhost:5435/fintegrate_db (fintegrate_user/fintegrate_pass)

# Run service locally (requires PostgreSQL + RabbitMQ + Redis running)
cd services/customer_service
uvicorn main:app --reload --port 8000

# Docker stack (includes Traefik gateway on port 80)
cd docker
docker-compose up --build
```

### Testing with Postman
- **Base URL**: `http://localhost/customer/data` (via Traefik) or `http://localhost:8000` (direct)
- **Auth**: Add `X-API-Key` header
- **Create consumer first**: `POST /consumer/data` → get API key
- **Rate limit testing**: See `gateway/test-gateway.ps1` for load test scripts

### Docker Services
- Traefik dashboard: http://localhost:8080
- RabbitMQ UI: http://localhost:15672 (fintegrate_user/fintegrate_pass)
- Customer service: Routed through Traefik (not exposed directly)

## Key Conventions

### Code Style
- **No emojis, filler, or verbose comments** (see `copilot-instructions.txt` tone guidance)
- **Blunt, directive**: Direct answers, no conversational transitions
- **Function docstrings**: Include purpose, args with types, return types
- **Error messages**: Specific, actionable (never reveal cross-tenant data existence)

### Security Patterns
- **Consumer isolation**: Every CRUD operation filters by `consumer_id` from authenticated API key
- **UUID primary keys**: Use `gen_random_uuid()` in DB, `uuid.uuid4()` in Python
- **No plaintext secrets**: API keys hashed with bcrypt before storage
- **Audit logging**: `services/shared/audit_logger.py` logs errors to `audit_log` table

### Naming
- **Tables**: `snake_case` (e.g., `customer_events`)
- **JSON fields**: `snake_case` in responses (not camelCase)
- **Event types**: `customer_` prefix (e.g., `customer_creation`)
- **Consumer names**: `lowercase_alphanumeric_underscore` (enforced by DB constraint)

## Common Tasks

### Adding a New API Endpoint
1. Define Pydantic schemas in `services/customer_service/schemas.py`
2. Add CRUD function in `crud.py` (always filter by `consumer_id`)
3. Add route in `routes.py` with dependencies: `consumer = Depends(verify_api_key), _ = Depends(rate_limit_middleware)`
4. Wrap response: `success_response(data_dict, status_code)` or `error_response(code, desc)`
5. Test with Postman (create consumer first, use its API key)

### Creating an Event
```python
event = crud.create_customer_event(
    db=db,
    customer_id=customer_id,
    event_type="customer_creation",  # Use underscore not dot
    source_service="POST: /customer/data",
    payload={"customer_id": str(customer_id), "name": name, "status": status},
    metadata={"created_at": timestamp.isoformat()},
    publish_status="pending",
    publish_try_count=1,
    consumer_id=consumer.consumer_id  # From authenticated consumer
)

# Publish to RabbitMQ (non-blocking)
publisher = get_event_publisher()
success = publisher.publish_event(
    event_id=event.event_id,
    event_type="customer_creation",
    customer_id=customer_id,
    name=name,
    status=status,
    created_at=event.created_at,
    consumer_name=consumer.name  # Routes to consumer-specific queue
)
```

### Database Migration
1. Create file: `database/migrations/YYYYMMDD_HHMM_description.sql`
2. Include rollback instructions in comments
3. Use `BEGIN; ... COMMIT;` transaction wrapper
4. Log in `migration_history` table
5. Execute via DBeaver or `psql -U fintegrate_user -d fintegrate_db -f migration.sql`

## Context Files (Read Before Making Changes)
- `project-context.txt`: Learning plan and phases
- `database-context.txt`: Full schema with migration history
- `copilot-instructions.txt`: Tone and operational behavior rules
- `prompts.txt`: User's historical development log (implementation decisions)

## Current Phase
**Phase 2**: Core Integration complete. Gateway, multi-consumer queues, rate limiting operational. 

**Next**: Load balancing test with two customer service instances (see `prompts.txt` line 709).

## Anti-Patterns to Avoid
❌ **Don't** add foreign key constraints to base tables (removed in 20251024_0900)  
❌ **Don't** use Alembic or auto-migrations  
❌ **Don't** expose customer data across consumers (filter by `consumer_id`)  
❌ **Don't** block API responses on RabbitMQ (Outbox pattern is non-blocking)  
❌ **Don't** use camelCase in JSON responses  
❌ **Don't** add generic "write tests" advice (document discoverable patterns only)

## Useful File Paths
- Customer routes: `services/customer_service/routes.py`
- Response handlers: `services/shared/response_handler.py`
- Event publisher: `services/shared/event_publisher.py`
- CRUD operations: `services/customer_service/crud.py`
- Schemas: `services/customer_service/schemas.py`
- Middleware: `services/customer_service/middleware.py`
- Docker config: `docker/docker-compose.yml`
- Migrations: `database/migrations/`
