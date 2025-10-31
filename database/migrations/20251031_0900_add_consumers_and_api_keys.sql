-- Migration: Add consumers and API key management
-- Created: 2025-10-31
-- Purpose: Multi-consumer architecture with API key authentication

-- Step 1: Create consumers table
CREATE TABLE consumers (
    consumer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(230) NOT NULL UNIQUE,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_consumer_status CHECK (status IN ('active', 'deactivated', 'suspended')),
    CONSTRAINT chk_consumer_name_format CHECK (name ~ '^[a-z0-9_]+$')
);

-- Step 2: Create consumer_api_keys table
CREATE TABLE consumer_api_keys (
    api_key_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consumer_id UUID NOT NULL REFERENCES consumers(consumer_id) ON DELETE CASCADE,
    api_key_hash VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    expires_at TIMESTAMP,
    last_used_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_api_key_status CHECK (status IN ('active', 'expired', 'deactivated'))
);

-- Step 3: Add unique constraint for one active key per consumer
CREATE UNIQUE INDEX idx_one_active_key_per_consumer 
ON consumer_api_keys(consumer_id) 
WHERE status = 'active';

-- Step 4: Insert default consumer for existing data
INSERT INTO consumers (consumer_id, name, description, status)
VALUES ('00000000-0000-0000-0000-000000000001', 'system_default', 'Default consumer for legacy data', 'active');

-- Step 5: Add consumer_id to customer_events table (nullable initially)
ALTER TABLE customer_events
ADD COLUMN consumer_id UUID REFERENCES consumers(consumer_id) ON DELETE RESTRICT;

-- Step 6: Backfill existing events with default consumer
UPDATE customer_events
SET consumer_id = '00000000-0000-0000-0000-000000000001'
WHERE consumer_id IS NULL;

-- Step 7: Make consumer_id NOT NULL after backfill
ALTER TABLE customer_events
ALTER COLUMN consumer_id SET NOT NULL;

-- Step 8: Add foreign key constraint to consumer_event_receipts
ALTER TABLE consumer_event_receipts
ADD CONSTRAINT fk_consumer_event_receipts_consumer
FOREIGN KEY (consumer_id) REFERENCES consumers(consumer_id) ON DELETE RESTRICT;

-- Step 9: Create indexes for performance
CREATE INDEX idx_consumers_status ON consumers(status);
CREATE INDEX idx_consumers_name ON consumers(name);

CREATE INDEX idx_api_keys_consumer_id ON consumer_api_keys(consumer_id);
CREATE INDEX idx_api_keys_status ON consumer_api_keys(status);
CREATE INDEX idx_api_keys_hash ON consumer_api_keys(api_key_hash);

CREATE INDEX idx_customer_events_consumer_id ON customer_events(consumer_id);
CREATE INDEX idx_customer_events_consumer_deliver ON customer_events(consumer_id, deliver_status);

-- Step 10: Add comments for documentation
COMMENT ON TABLE consumers IS 'Event consumers with unique queue identifiers';
COMMENT ON COLUMN consumers.name IS 'Unique consumer identifier used in queue naming (alphanumeric + underscore only)';
COMMENT ON COLUMN consumers.status IS 'Consumer state: active (operational), suspended (temporary block), deactivated (permanent)';

COMMENT ON TABLE consumer_api_keys IS 'API authentication keys for consumers (one active key per consumer)';
COMMENT ON COLUMN consumer_api_keys.api_key_hash IS 'Bcrypt/Argon2 hash of API key value (never store plaintext)';
COMMENT ON COLUMN consumer_api_keys.status IS 'Key state: active (valid), expired (time-based), deactivated (manual revocation)';
COMMENT ON COLUMN consumer_api_keys.last_used_at IS 'Last successful authentication timestamp for security auditing';

COMMENT ON COLUMN customer_events.consumer_id IS 'Target consumer for event delivery and queue routing';

-- Step 11: Record migration execution
INSERT INTO migration_history (revision_id, description, executed_at, executed_by)
VALUES ('20251031_0900', 'Add consumers and API keys', NOW(), 'system');