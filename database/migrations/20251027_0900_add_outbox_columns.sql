-- Migration: Add Transactional Outbox Pattern columns to customer_events table
-- Date: 2025-10-27
-- Purpose: Support manual retry mechanism for failed RabbitMQ publishes

-- Add publish tracking columns
ALTER TABLE customer_events 
ADD COLUMN publish_status VARCHAR(20) DEFAULT 'published' 
    CHECK (publish_status IN ('pending', 'published', 'failed'));

ALTER TABLE customer_events 
ADD COLUMN published_at TIMESTAMP NULL;

ALTER TABLE customer_events 
ADD COLUMN publish_try_count INTEGER DEFAULT 1;

ALTER TABLE customer_events 
ADD COLUMN last_tried_at TIMESTAMP NULL;

ALTER TABLE customer_events 
ADD COLUMN failure_reason TEXT NULL;

-- Add performance index for /events/resend queries
CREATE INDEX idx_events_publish_retry 
ON customer_events(publish_status, created_at, publish_try_count);

-- Add comment for documentation
COMMENT ON COLUMN customer_events.publish_status IS 
'Status of RabbitMQ publish attempt: pending (not yet published or failed), published (successfully delivered), failed (exceeded max retry count of 10)';

COMMENT ON COLUMN customer_events.publish_try_count IS 
'Number of publish attempts. Initial value is 1 after first attempt. Incremented by POST /events/resend on each retry.';

COMMENT ON COLUMN customer_events.failure_reason IS 
'Stores pika exception message when RabbitMQ publish fails. Used for troubleshooting.';

-- Record migration execution
INSERT INTO migration_history (revision_id, description, executed_at, executed_by)
VALUES ('20251027_0900_add_outbox_columns', 'Add Transactional Outbox Pattern columns to customer_events table', NOW(), 'system');
