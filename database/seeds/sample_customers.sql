-- Sample Customer Data for Testing
-- Run after initial schema migration

INSERT INTO customers (customer_id, name, status, created_at, updated_at)
VALUES 
    ('550e8400-e29b-41d4-a716-446655440001', 'John Doe', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('550e8400-e29b-41d4-a716-446655440002', 'Jane Smith', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('550e8400-e29b-41d4-a716-446655440003', 'Bob Johnson', 'INACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (customer_id) DO NOTHING;
