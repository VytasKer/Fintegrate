-- Migration: 20251024_1000_update_customer_tags_and_analytics
-- Description: Add updated_at column to customer_tags and rename analytics_customers to customer_analytics
-- Author: System
-- Date: 2025-10-24

-- ==================================================================
-- CHANGE 1: Add updated_at column to customer_tags
-- ==================================================================

ALTER TABLE customer_tags 
ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Update existing rows to have current timestamp
UPDATE customer_tags 
SET updated_at = created_at 
WHERE updated_at IS NULL;

-- Make updated_at NOT NULL after setting values
ALTER TABLE customer_tags 
ALTER COLUMN updated_at SET NOT NULL;

-- Create trigger to auto-update updated_at on row modification
CREATE OR REPLACE FUNCTION update_customer_tags_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_customer_tags_updated_at
    BEFORE UPDATE ON customer_tags
    FOR EACH ROW
    EXECUTE FUNCTION update_customer_tags_updated_at();

-- ==================================================================
-- CHANGE 2: Rename analytics_customers to customer_analytics
-- ==================================================================

-- Check if customer_analytics already exists and drop it
DROP TABLE IF EXISTS customer_analytics CASCADE;

-- Rename analytics_customers to customer_analytics
ALTER TABLE analytics_customers 
RENAME TO customer_analytics;

-- Update index name to match new table name
ALTER INDEX idx_analytics_customers_customer_id 
RENAME TO idx_customer_analytics_customer_id;

-- ==================================================================
-- MIGRATION HISTORY RECORD
-- ==================================================================

INSERT INTO migration_history (revision_id, description, executed_at, executed_by)
VALUES (
    '20251024_1000_update_customer_tags_and_analytics',
    'Add updated_at column to customer_tags and rename analytics_customers to customer_analytics',
    NOW(),
    'system'
);

-- ==================================================================
-- VERIFICATION QUERIES (comment out before execution)
-- ==================================================================

-- SELECT column_name, data_type, is_nullable 
-- FROM information_schema.columns 
-- WHERE table_name = 'customer_tags' 
-- ORDER BY ordinal_position;

-- SELECT table_name 
-- FROM information_schema.tables 
-- WHERE table_schema = 'public' 
-- AND table_name LIKE '%analytics%';
