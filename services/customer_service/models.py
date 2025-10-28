from sqlalchemy import Column, String, TIMESTAMP, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
from services.customer_service.database import Base


class Customer(Base):
    __tablename__ = "customers"
    
    customer_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="ACTIVE")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())


class CustomerEvent(Base):
    __tablename__ = "customer_events"
    
    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    event_type = Column(String(100), nullable=False)
    source_service = Column(String(100))
    payload_json = Column(JSONB, nullable=False)
    metadata_json = Column(JSONB)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    
    # Transactional Outbox Pattern - Publish Lifecycle
    publish_status = Column(String(20), nullable=False, default="published")  # 'pending', 'published', 'failed'
    published_at = Column(TIMESTAMP, nullable=True)
    publish_try_count = Column(Integer, nullable=False, default=1)
    publish_last_tried_at = Column(TIMESTAMP, nullable=True)
    publish_failure_reason = Column(String, nullable=True)  # Stores pika exception details
    
    # Delivery Lifecycle
    deliver_status = Column(String(20), nullable=False, default="pending")  # 'pending', 'delivered', 'failed'
    delivered_at = Column(TIMESTAMP, nullable=True)
    deliver_try_count = Column(Integer, nullable=False, default=0)
    deliver_last_tried_at = Column(TIMESTAMP, nullable=True)
    deliver_failure_reason = Column(String, nullable=True)  # DLQ, timeout, etc


class CustomerTag(Base):
    __tablename__ = "customer_tags"
    
    tag_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    tag_key = Column(String(100), nullable=False)
    tag_value = Column(String(255))
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())


class CustomerArchive(Base):
    __tablename__ = "customer_archive"
    
    archive_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    snapshot_json = Column(JSONB, nullable=False)
    trigger_event = Column(String(100))
    archived_at = Column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())


class AuditLog(Base):
    __tablename__ = "audit_log"
    
    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity = Column(String(100), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(50), nullable=False)
    user_name = Column(String(100))
    ip_address = Column(String(45))
    request_json = Column(JSONB)
    response_json = Column(JSONB)
    timestamp = Column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())


class CustomerAnalytics(Base):
    """CustomerAnalytics model for analytics snapshots and time-series analysis."""
    __tablename__ = "customer_analytics"
    
    analytics_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    name = Column(String(255))
    status = Column(String(50))
    created_at = Column(TIMESTAMP)
    last_event_time = Column(TIMESTAMP)
    total_events = Column(Integer, default=0)
    tags_json = Column(JSONB)
    metrics_json = Column(JSONB)
    snapshot_at = Column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())


class ConsumerEventReceipt(Base):
    """Consumer event receipts for idempotency and delivery tracking."""
    __tablename__ = "consumer_event_receipts"
    
    receipt_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consumer_id = Column(UUID(as_uuid=True), nullable=True)  # NULL for now, FK later
    event_id = Column(UUID(as_uuid=True), nullable=False)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    event_type = Column(String(100), nullable=False)
    received_at = Column(TIMESTAMP, nullable=False)
    processing_status = Column(String(20), nullable=False)  # 'received', 'processed', 'failed'
    processing_failure_reason = Column(String, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
