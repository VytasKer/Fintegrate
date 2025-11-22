-- Migration: Allow NULL consumer_id for global analytics snapshots
-- Date: 2025-11-04 19:40
-- Purpose: Support system-wide global snapshots (consumer_id=NULL) in consumer_analytics table
-- Related: Task 6 - Multi-Consumer Analytics

BEGIN;

-- Drop existing unique constraint (requires consumer_id NOT NULL)
ALTER TABLE consumer_analytics 
DROP CONSTRAINT IF EXISTS unique_consumer_snapshot;

-- Allow NULL values in consumer_id column
ALTER TABLE consumer_analytics 
ALTER COLUMN consumer_id DROP NOT NULL;

-- Recreate unique constraint with support for NULL
-- PostgreSQL treats NULL as distinct values, so need partial unique index
CREATE UNIQUE INDEX unique_consumer_snapshot_not_null
ON consumer_analytics (consumer_id, snapshot_timestamp)
WHERE consumer_id IS NOT NULL;

-- Separate unique constraint for global snapshots (consumer_id IS NULL)
CREATE UNIQUE INDEX unique_global_snapshot
ON consumer_analytics (snapshot_timestamp)
WHERE consumer_id IS NULL;

-- Add comment explaining NULL semantics
COMMENT ON COLUMN consumer_analytics.consumer_id IS 
'Consumer UUID for per-consumer snapshots, or NULL for global system-wide snapshots';

-- Verify changes
SELECT 
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'consumer_analytics'
ORDER BY ordinal_position;

COMMIT;

-- Rollback instructions (if needed):
-- BEGIN;
-- ALTER TABLE consumer_analytics ALTER COLUMN consumer_id SET NOT NULL;
-- DROP INDEX IF EXISTS unique_consumer_snapshot_not_null;
-- DROP INDEX IF EXISTS unique_global_snapshot;
-- CREATE UNIQUE CONSTRAINT unique_consumer_snapshot UNIQUE (consumer_id, snapshot_timestamp);
-- COMMIT;

INSERT INTO migration_history (revision_id, description, executed_at, executed_by)
VALUES (
    '20251104_1940_allow_null_consumer_id_for_global',
    'Allow NULL consumer_id in consumer_analytics for global snapshots and adjust unique constraints accordingly',
    NOW(),
    'system'
);
