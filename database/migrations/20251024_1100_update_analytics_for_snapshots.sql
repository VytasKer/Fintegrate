-- Migration: 20251024_1100_update_analytics_for_snapshots
-- Description: Update customer_analytics to support multiple time-series snapshots per customer
-- Author: System
-- Date: 2025-10-24

-- ==================================================================
-- CHANGE: Restructure customer_analytics for time-series snapshots
-- ==================================================================

-- Drop existing customer_analytics table (renamed from analytics_customers)
DROP TABLE IF EXISTS customer_analytics CASCADE;

-- Recreate customer_analytics with analytics_id as primary key
-- This allows multiple snapshot entries for the same customer
CREATE TABLE customer_analytics (
    analytics_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL,
    name VARCHAR(255),
    status VARCHAR(50),
    created_at TIMESTAMP,
    last_event_time TIMESTAMP,
    total_events INT DEFAULT 0,
    tags_json JSONB,
    metrics_json JSONB,
    snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create index for efficient customer lookups
CREATE INDEX idx_customer_analytics_customer_id ON customer_analytics(customer_id);

-- Create index for time-series queries
CREATE INDEX idx_customer_analytics_snapshot_at ON customer_analytics(snapshot_at);

-- ==================================================================
-- MIGRATION HISTORY RECORD
-- ==================================================================

INSERT INTO migration_history (revision_id, description, applied_at)
VALUES (
    '20251024_1100',
    'Update customer_analytics to support multiple time-series snapshots per customer',
    CURRENT_TIMESTAMP
);

-- ==================================================================
-- VERIFICATION QUERIES (comment out before execution)
-- ==================================================================

-- SELECT column_name, data_type, is_nullable, column_default
-- FROM information_schema.columns 
-- WHERE table_name = 'customer_analytics' 
-- ORDER BY ordinal_position;

-- SELECT indexname, indexdef 
-- FROM pg_indexes 
-- WHERE tablename = 'customer_analytics';
