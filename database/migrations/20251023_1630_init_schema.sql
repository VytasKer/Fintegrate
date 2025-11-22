-- Migration: 20251023_1630_init_schema
-- Description: Initial schema creation for Fintegrate project
-- Author: system
-- Date: 2025-10-23

-- Rollback instructions:
-- DROP TABLE IF EXISTS customer_archive CASCADE;
-- DROP TABLE IF EXISTS analytics_customers CASCADE;
-- DROP TABLE IF EXISTS audit_log CASCADE;
-- DROP TABLE IF EXISTS customer_tags CASCADE;
-- DROP TABLE IF EXISTS customer_events CASCADE;
-- DROP TABLE IF EXISTS customers CASCADE;
-- DROP TABLE IF EXISTS migration_history CASCADE;

BEGIN;

-- Migration tracking table
CREATE TABLE IF NOT EXISTS migration_history (
    migration_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    revision_id VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    executed_by VARCHAR(100)
);

-- 1. customers
CREATE TABLE IF NOT EXISTS customers (
    customer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. customer_events
CREATE TABLE IF NOT EXISTS customer_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(customer_id),
    event_type VARCHAR(100) NOT NULL,
    source_service VARCHAR(100),
    payload_json JSONB NOT NULL,
    metadata_json JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. customer_tags
CREATE TABLE IF NOT EXISTS customer_tags (
    tag_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(customer_id),
    tag_key VARCHAR(100) NOT NULL,
    tag_value VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (customer_id, tag_key)
);

-- 4. audit_log
CREATE TABLE IF NOT EXISTS audit_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity VARCHAR(100) NOT NULL,
    entity_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    user_name VARCHAR(100),
    ip_address VARCHAR(45),
    request_json JSONB,
    response_json JSONB,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 5. analytics_customers
CREATE TABLE IF NOT EXISTS analytics_customers (
    customer_id UUID PRIMARY KEY,
    name VARCHAR(255),
    status VARCHAR(50),
    created_at TIMESTAMP,
    last_event_time TIMESTAMP,
    total_events INT DEFAULT 0,
    tags_json JSONB,
    metrics_json JSONB,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. customer_archive
CREATE TABLE IF NOT EXISTS customer_archive (
    archive_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(customer_id),
    snapshot_json JSONB NOT NULL,
    trigger_event VARCHAR(100),
    archived_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance on integration-heavy operations
CREATE INDEX IF NOT EXISTS idx_customer_events_custid ON customer_events(customer_id);
CREATE INDEX IF NOT EXISTS idx_customer_events_created ON customer_events(created_at);
CREATE INDEX IF NOT EXISTS idx_customer_tags_custid ON customer_tags(customer_id);
CREATE INDEX IF NOT EXISTS idx_auditlog_entityid ON audit_log(entity_id);
CREATE INDEX IF NOT EXISTS idx_auditlog_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_customer_archive_custid ON customer_archive(customer_id);

-- Record migration execution
INSERT INTO migration_history (revision_id, description, executed_at, executed_by)
VALUES ('20251023_1630_init_schema', 'Initial schema creation for Fintegrate project', NOW(), 'system')
ON CONFLICT (revision_id) DO NOTHING;

COMMIT;
