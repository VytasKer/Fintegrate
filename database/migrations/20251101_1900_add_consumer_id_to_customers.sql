-- Migration: 20251101_1900_add_consumer_id_to_customers
-- Description: Add consumer_id column to customers table for multi-tenant data isolation
-- Author: system
-- Date: 2025-11-01
-- CRITICAL SECURITY FIX: Prevent cross-consumer data access

-- Rollback instructions:
-- ALTER TABLE customers DROP COLUMN consumer_id;
-- ALTER TABLE customer_tags DROP COLUMN consumer_id;
-- ALTER TABLE customer_analytics DROP COLUMN consumer_id;

BEGIN;

-- Add consumer_id to customers table
ALTER TABLE customers 
ADD COLUMN consumer_id UUID;

-- Set default consumer for existing customers (system_default)
UPDATE customers 
SET consumer_id = '00000000-0000-0000-0000-000000000001'::UUID
WHERE consumer_id IS NULL;

-- Make consumer_id NOT NULL after setting defaults
ALTER TABLE customers 
ALTER COLUMN consumer_id SET NOT NULL;

-- Add index for faster consumer-based queries
CREATE INDEX idx_customers_consumer_id ON customers(consumer_id);

-- Add composite index for common query patterns
CREATE INDEX idx_customers_consumer_customer ON customers(consumer_id, customer_id);

-- Add consumer_id to customer_tags for direct filtering
ALTER TABLE customer_tags
ADD COLUMN consumer_id UUID;

-- Populate consumer_id in customer_tags from customers table
UPDATE customer_tags ct
SET consumer_id = c.consumer_id
FROM customers c
WHERE ct.customer_id = c.customer_id;

-- Make consumer_id NOT NULL
ALTER TABLE customer_tags
ALTER COLUMN consumer_id SET NOT NULL;

-- Add index
CREATE INDEX idx_customer_tags_consumer_id ON customer_tags(consumer_id);

-- Add consumer_id to customer_analytics
ALTER TABLE customer_analytics
ADD COLUMN consumer_id UUID;

-- Populate from customers
UPDATE customer_analytics ca
SET consumer_id = c.consumer_id  
FROM customers c
WHERE ca.customer_id = c.customer_id;

-- Make NOT NULL
ALTER TABLE customer_analytics
ALTER COLUMN consumer_id SET NOT NULL;

-- Add index
CREATE INDEX idx_customer_analytics_consumer_id ON customer_analytics(consumer_id);

-- Record migration
INSERT INTO migration_history (revision_id, description, executed_atexecuted_by)
VALUES ('20251101_1900_add_consumer_id_to_customers', 'Add consumer_id to customers, customer_tags, and customer_analytics for multi-tenant isolation', NOW(), 'system');

COMMIT;

-- Verification queries:
-- SELECT COUNT(*) FROM customers WHERE consumer_id IS NULL; -- Should be 0
-- SELECT COUNT(*) FROM customer_tags WHERE consumer_id IS NULL; -- Should be 0  
-- SELECT COUNT(*) FROM customer_analytics WHERE consumer_id IS NULL; -- Should be 0
