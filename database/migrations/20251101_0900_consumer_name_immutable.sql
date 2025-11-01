-- Migration: Make consumer name immutable
-- Created: 2025-11-01
-- Purpose: Prevent consumer name changes to avoid orphaned queues

-- Create trigger function to prevent consumer name updates
CREATE OR REPLACE FUNCTION prevent_consumer_name_update()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.name IS DISTINCT FROM NEW.name THEN
        RAISE EXCEPTION 'Consumer name cannot be changed after creation. Queue name depends on consumer name for routing.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger on consumers table
CREATE TRIGGER trg_prevent_consumer_name_update
    BEFORE UPDATE ON consumers
    FOR EACH ROW
    EXECUTE FUNCTION prevent_consumer_name_update();

-- Add comment for documentation
COMMENT ON TRIGGER trg_prevent_consumer_name_update ON consumers IS 
'Prevents consumer name modification to maintain queue routing integrity. Consumer name determines RabbitMQ queue name pattern.';

-- Record migration execution
INSERT INTO migration_history (revision_id, description, executed_at, executed_by)
VALUES ('20251101_0900', 'Make consumer name immutable via trigger', NOW(), 'system');
