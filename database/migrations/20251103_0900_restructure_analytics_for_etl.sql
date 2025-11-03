-- Migration: 20251103_0900_restructure_analytics_for_etl
-- Description: Restructure customer_analytics for consumer-level ETL aggregates and add watermark tracking
-- Author: System
-- Date: 2025-11-03

-- Rollback instructions:
-- 1. DROP TABLE etl_job_watermarks;
-- 2. Restore customer_analytics schema from 20251024_1100 migration
-- 3. Rename consumer_analytics back to customer_analytics

-- ==================================================================
-- STEP 1: Rename table to reflect consumer-level aggregates
-- ==================================================================

ALTER TABLE customer_analytics RENAME TO consumer_analytics;

-- ==================================================================
-- STEP 2: Drop unused columns (per-customer fields not needed for aggregates)
-- ==================================================================

ALTER TABLE consumer_analytics DROP COLUMN IF EXISTS customer_id;
ALTER TABLE consumer_analytics DROP COLUMN IF EXISTS name;
ALTER TABLE consumer_analytics DROP COLUMN IF EXISTS status;
ALTER TABLE consumer_analytics DROP COLUMN IF EXISTS created_at;
ALTER TABLE consumer_analytics DROP COLUMN IF EXISTS last_event_time;
ALTER TABLE consumer_analytics DROP COLUMN IF EXISTS total_events;
ALTER TABLE consumer_analytics DROP COLUMN IF EXISTS tags_json;

-- ==================================================================
-- STEP 3: Rename snapshot_at to snapshot_timestamp (consistent naming)
-- ==================================================================

ALTER TABLE consumer_analytics RENAME COLUMN snapshot_at TO snapshot_timestamp;

-- ==================================================================
-- STEP 4: Add NOT NULL constraint to metrics_json (required field)
-- ==================================================================

ALTER TABLE consumer_analytics ALTER COLUMN metrics_json SET NOT NULL;

-- ==================================================================
-- STEP 5: Add UNIQUE constraint (one snapshot per consumer per timestamp)
-- ==================================================================

ALTER TABLE consumer_analytics 
ADD CONSTRAINT unique_consumer_snapshot UNIQUE (consumer_id, snapshot_timestamp);

-- ==================================================================
-- STEP 6: Drop old indexes and create optimized time-series index
-- ==================================================================

DROP INDEX IF EXISTS idx_customer_analytics_customer_id;
DROP INDEX IF EXISTS idx_customer_analytics_snapshot_at;

CREATE INDEX idx_consumer_analytics_consumer_timestamp 
ON consumer_analytics(consumer_id, snapshot_timestamp DESC);

-- ==================================================================
-- STEP 7: Create ETL watermark tracking table
-- ==================================================================

CREATE TABLE IF NOT EXISTS etl_job_watermarks (
    job_name VARCHAR(100) PRIMARY KEY,
    last_processed_timestamp TIMESTAMP NOT NULL,
    last_run_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_run_status VARCHAR(20) CHECK (last_run_status IN ('pending', 'running', 'success', 'failed')),
    records_processed INT DEFAULT 0,
    metadata_json JSONB
);

-- Insert initial watermark for consumer analytics job
INSERT INTO etl_job_watermarks (job_name, last_processed_timestamp, last_run_status)
VALUES ('consumer_analytics_daily', '1970-01-01 00:00:00', 'pending')
ON CONFLICT (job_name) DO NOTHING;

-- ==================================================================
-- STEP 8: Add comments for documentation
-- ==================================================================

COMMENT ON TABLE consumer_analytics IS 'Time-series snapshots of consumer-level aggregate metrics. Each row represents system or per-consumer metrics at a specific timestamp. Used by Airflow ETL jobs.';
COMMENT ON COLUMN consumer_analytics.consumer_id IS 'UUID of consumer. NULL indicates global/system-wide metrics aggregated across all consumers.';
COMMENT ON COLUMN consumer_analytics.snapshot_timestamp IS 'Timestamp when this snapshot was created. Used for time-series trend analysis.';
COMMENT ON COLUMN consumer_analytics.metrics_json IS 'JSONB containing aggregate metrics: total_customers, active_customers, events_by_type, avg_customer_lifetime_days, etc.';

COMMENT ON TABLE etl_job_watermarks IS 'Tracks last processed timestamp for incremental ETL jobs. Prevents reprocessing of already-handled events.';
COMMENT ON COLUMN etl_job_watermarks.job_name IS 'Unique identifier for ETL job (e.g., consumer_analytics_daily).';
COMMENT ON COLUMN etl_job_watermarks.last_processed_timestamp IS 'Maximum created_at timestamp from source table processed in last successful run.';
COMMENT ON COLUMN etl_job_watermarks.last_run_status IS 'Status of last execution: pending, running, success, failed.';

-- ==================================================================
-- MIGRATION HISTORY RECORD
-- ==================================================================

INSERT INTO migration_history (revision_id, description, executed_at, executed_by)
VALUES (
    '20251103_0900',
    'Restructure customer_analytics for consumer-level ETL aggregates and add watermark tracking',
    CURRENT_TIMESTAMP,
    'system'
);

-- ==================================================================
-- VERIFICATION QUERIES (uncomment to run after migration)
-- ==================================================================

-- Verify table renamed and columns updated
-- SELECT column_name, data_type, is_nullable, column_default
-- FROM information_schema.columns 
-- WHERE table_name = 'consumer_analytics' 
-- ORDER BY ordinal_position;

-- Verify indexes created
-- SELECT indexname, indexdef 
-- FROM pg_indexes 
-- WHERE tablename = 'consumer_analytics';

-- Verify watermark table structure
-- SELECT * FROM etl_job_watermarks;

-- Verify constraints
-- SELECT conname, contype, pg_get_constraintdef(oid) 
-- FROM pg_constraint 
-- WHERE conrelid = 'consumer_analytics'::regclass;
