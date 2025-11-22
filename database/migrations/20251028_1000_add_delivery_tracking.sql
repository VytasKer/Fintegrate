-- Migration: Add delivery tracking columns and consumer receipts table
-- Created: 2025-10-28
-- Purpose: Track message delivery lifecycle and consumer acknowledgments

-- Step 1: Rename existing columns for clarity (publish lifecycle)
ALTER TABLE customer_events 
RENAME COLUMN last_tried_at TO publish_last_tried_at;

ALTER TABLE customer_events 
RENAME COLUMN failure_reason TO publish_failure_reason;

-- Step 2: Add delivery lifecycle columns
ALTER TABLE customer_events
ADD COLUMN deliver_status VARCHAR(20) DEFAULT 'pending',
ADD COLUMN delivered_at TIMESTAMP,
ADD COLUMN deliver_try_count INTEGER DEFAULT 0,
ADD COLUMN deliver_last_tried_at TIMESTAMP,
ADD COLUMN deliver_failure_reason TEXT;

-- Step 3: Create consumer event receipts table
CREATE TABLE consumer_event_receipts (
    receipt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consumer_id UUID,  -- NULL for now, will be FK to consumers table in future
    event_id UUID NOT NULL REFERENCES customer_events(event_id) ON DELETE CASCADE,
    customer_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    processing_status VARCHAR(20) NOT NULL,  -- received/processed/failed
    processing_failure_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Step 4: Create indexes for performance
CREATE INDEX idx_consumer_receipts_event_id ON consumer_event_receipts(event_id);
CREATE INDEX idx_consumer_receipts_customer_id ON consumer_event_receipts(customer_id);
CREATE INDEX idx_consumer_receipts_consumer_id ON consumer_event_receipts(consumer_id);
CREATE INDEX idx_customer_events_deliver_status ON customer_events(deliver_status);
CREATE INDEX idx_customer_events_customer_id_deliver ON customer_events(customer_id, deliver_status);

-- Step 5: Add comments for documentation
COMMENT ON COLUMN customer_events.deliver_status IS 'Message delivery status: pending/delivered/failed';
COMMENT ON COLUMN customer_events.delivered_at IS 'Timestamp when consumer confirmed receipt';
COMMENT ON COLUMN customer_events.deliver_try_count IS 'Number of delivery attempts to consumer';
COMMENT ON COLUMN customer_events.deliver_last_tried_at IS 'Last delivery attempt timestamp';
COMMENT ON COLUMN customer_events.deliver_failure_reason IS 'Reason for delivery failure (DLQ, timeout, etc)';

COMMENT ON TABLE consumer_event_receipts IS 'Tracks consumer acknowledgments for idempotency and audit';
COMMENT ON COLUMN consumer_event_receipts.processing_status IS 'Consumer processing result: received/processed/failed';

-- Record migration execution
INSERT INTO migration_history (revision_id, description, executed_at, executed_by)
VALUES ('20251028_1000_add_delivery_tracking', 'Add delivery tracking columns and consumer receipts table', NOW(), 'system');
