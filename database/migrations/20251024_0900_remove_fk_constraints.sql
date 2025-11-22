-- Migration: 20251024_0900_remove_fk_constraints
-- Description: Remove foreign key constraints from customer_events, customer_archive, and customer_tags for maximum flexibility
-- Author: system
-- Date: 2025-10-24

-- Rollback instructions:
-- ALTER TABLE customer_events ADD CONSTRAINT customer_events_customer_id_fkey 
--   FOREIGN KEY (customer_id) REFERENCES customers(customer_id);
-- ALTER TABLE customer_archive ADD CONSTRAINT customer_archive_customer_id_fkey 
--   FOREIGN KEY (customer_id) REFERENCES customers(customer_id);
-- ALTER TABLE customer_tags ADD CONSTRAINT customer_tags_customer_id_fkey 
--   FOREIGN KEY (customer_id) REFERENCES customers(customer_id);

BEGIN;

-- Remove FK constraint from customer_events
-- Allows events to persist as immutable historical records after customer deletion
ALTER TABLE customer_events DROP CONSTRAINT IF EXISTS customer_events_customer_id_fkey;

-- Remove FK constraint from customer_archive
-- Allows archives to persist as historical snapshots after customer deletion
ALTER TABLE customer_archive DROP CONSTRAINT IF EXISTS customer_archive_customer_id_fkey;

-- Remove FK constraint from customer_tags
-- Allows flexible tag management without referential integrity enforcement
ALTER TABLE customer_tags DROP CONSTRAINT IF EXISTS customer_tags_customer_id_fkey;

-- Record migration execution
INSERT INTO migration_history (revision_id, description, executed_at, executed_by)
VALUES ('20251024_0900_remove_fk_constraints', 'Remove FK constraints for flexible data management', NOW(), 'system')
ON CONFLICT (revision_id) DO NOTHING;

COMMIT;
