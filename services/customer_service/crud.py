from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from uuid import UUID
from typing import Dict, Any, List, Optional
from datetime import datetime
import secrets
import hashlib
from services.customer_service.models import (
    Customer, CustomerEvent, CustomerTag, CustomerArchive, 
    AuditLog, Consumer, ConsumerApiKey, ConsumerAnalytics
)
from services.customer_service.schemas import CustomerCreate


def create_customer(db: Session, customer_data: CustomerCreate, consumer_id: UUID) -> Customer:
    """
    Create new customer in database.
    
    Args:
        db: Database session
        customer_data: Customer creation data
        consumer_id: UUID of the consumer creating this customer (for multi-tenant isolation)
    
    Returns:
        Created customer object
    """
    db_customer = Customer(
        consumer_id=consumer_id,
        name=customer_data.name,
        status="ACTIVE"
    )
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer


def get_customer(db: Session, customer_id: UUID, consumer_id: UUID | None = None) -> Customer | None:
    """
    Retrieve customer by ID.
    
    Args:
        db: Database session
        customer_id: Customer UUID
        consumer_id: Consumer UUID for ownership validation (required for security)
    
    Returns:
        Customer if found and belongs to consumer, None otherwise
    """
    query = db.query(Customer).filter(Customer.customer_id == customer_id)
    
    # SECURITY: Filter by consumer_id to prevent cross-consumer data access
    if consumer_id is not None:
        query = query.filter(Customer.consumer_id == consumer_id)
    
    return query.first()


def delete_customer(db: Session, customer_id: UUID, consumer_id: UUID | None = None) -> bool:
    """
    Physically delete customer by ID.
    
    Args:
        db: Database session
        customer_id: Customer UUID
        consumer_id: Consumer UUID for ownership validation (required for security)
    
    Returns:
        True if deleted, False if not found or doesn't belong to consumer
    """
    query = db.query(Customer).filter(Customer.customer_id == customer_id)
    
    # SECURITY: Filter by consumer_id to prevent cross-consumer data access
    if consumer_id is not None:
        query = query.filter(Customer.consumer_id == consumer_id)
    
    db_customer = query.first()
    if db_customer:
        db.delete(db_customer)
        db.commit()
        return True
    return False


def update_customer_status(db: Session, customer_id: UUID, new_status: str, consumer_id: UUID | None = None) -> Customer | None:
    """
    Update customer status.
    
    Args:
        db: Database session
        customer_id: Customer UUID
        new_status: New status value
        consumer_id: Consumer UUID for ownership validation (required for security)
    
    Returns:
        Updated customer or None if not found or doesn't belong to consumer
    """
    query = db.query(Customer).filter(Customer.customer_id == customer_id)
    
    # SECURITY: Filter by consumer_id to prevent cross-consumer data access
    if consumer_id is not None:
        query = query.filter(Customer.consumer_id == consumer_id)
    
    db_customer = query.first()
    if db_customer:
        db_customer.status = new_status
        db.commit()
        db.refresh(db_customer)
        return db_customer
    return None


def create_customer_event(
    db: Session,
    customer_id: UUID,
    event_type: str,
    source_service: str,
    payload: Dict[str, Any],
    metadata: Dict[str, Any] | None = None,
    publish_status: str = "published",
    published_at: Any = None,
    publish_try_count: int = 1,
    publish_last_tried_at: Any = None,
    publish_failure_reason: str | None = None,
    consumer_id: UUID | None = None
) -> CustomerEvent:
    """Create event entry in customer_events table with outbox pattern support."""
    # Default to system consumer if not specified
    if consumer_id is None:
        from uuid import UUID as UUID_Type
        consumer_id = UUID_Type('00000000-0000-0000-0000-000000000001')
    
    db_event = CustomerEvent(
        customer_id=customer_id,
        consumer_id=consumer_id,
        event_type=event_type,
        source_service=source_service,
        payload_json=payload,
        metadata_json=metadata,
        publish_status=publish_status,
        published_at=published_at,
        publish_try_count=publish_try_count,
        publish_last_tried_at=publish_last_tried_at,
        publish_failure_reason=publish_failure_reason
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event


def get_customer_tags(db: Session, customer_id: UUID, consumer_id: UUID | None = None) -> List[CustomerTag]:
    """
    Retrieve all tags for a customer.
    
    Args:
        db: Database session
        customer_id: Customer UUID
        consumer_id: Consumer UUID for ownership validation (required for security)
    
    Returns:
        List of tags for the customer (empty if customer doesn't belong to consumer)
    """
    query = db.query(CustomerTag).filter(CustomerTag.customer_id == customer_id)
    
    # SECURITY: Filter by consumer_id to prevent cross-consumer data access
    if consumer_id is not None:
        query = query.filter(CustomerTag.consumer_id == consumer_id)
    
    return query.all()


def delete_customer_tags(db: Session, customer_id: UUID, consumer_id: UUID | None = None) -> int:
    """
    Delete all tags for a customer.
    
    Args:
        db: Database session
        customer_id: Customer UUID
        consumer_id: Consumer UUID for ownership validation (required for security)
    
    Returns:
        Count of deleted tags (0 if customer doesn't belong to consumer)
    """
    query = db.query(CustomerTag).filter(CustomerTag.customer_id == customer_id)
    
    # SECURITY: Filter by consumer_id to prevent cross-consumer data access
    if consumer_id is not None:
        query = query.filter(CustomerTag.consumer_id == consumer_id)
    
    count = query.delete()
    db.commit()
    return count


def create_customer_archive(
    db: Session,
    customer_id: UUID,
    snapshot: Dict[str, Any],
    trigger_event: str
) -> CustomerArchive:
    """Create archive entry in customer_archive table."""
    db_archive = CustomerArchive(
        customer_id=customer_id,
        snapshot_json=snapshot,
        trigger_event=trigger_event
    )
    db.add(db_archive)
    db.commit()
    db.refresh(db_archive)
    return db_archive


def create_audit_log(
    db: Session,
    entity: str,
    entity_id: UUID,
    action: str,
    user_name: str | None,
    ip_address: str | None,
    request_data: Dict[str, Any] | None,
    response_data: Dict[str, Any] | None
) -> AuditLog:
    """Create audit log entry for errors and warnings."""
    db_audit = AuditLog(
        entity=entity,
        entity_id=entity_id,
        action=action,
        user_name=user_name,
        ip_address=ip_address,
        request_json=request_data,
        response_json=response_data
    )
    db.add(db_audit)
    db.commit()
    db.refresh(db_audit)
    return db_audit


def create_customer_tag(db: Session, customer_id: UUID, tag_key: str, tag_value: str, consumer_id: UUID) -> CustomerTag:
    """
    Create or update a tag for a customer.
    
    Args:
        db: Database session
        customer_id: Customer UUID
        tag_key: Tag key
        tag_value: Tag value
        consumer_id: Consumer UUID (required for multi-tenant isolation)
    
    Returns:
        Created or updated tag
    """
    # Check if tag already exists (with consumer_id filter for security)
    existing_tag = db.query(CustomerTag).filter(
        CustomerTag.customer_id == customer_id,
        CustomerTag.consumer_id == consumer_id,
        CustomerTag.tag_key == tag_key
    ).first()
    
    if existing_tag:
        # Update existing tag
        existing_tag.tag_value = tag_value
        db.commit()
        db.refresh(existing_tag)
        return existing_tag
    else:
        # Create new tag
        db_tag = CustomerTag(
            customer_id=customer_id,
            consumer_id=consumer_id,
            tag_key=tag_key,
            tag_value=tag_value
        )
        db.add(db_tag)
        db.commit()
        db.refresh(db_tag)
        return db_tag


def get_customer_tag(db: Session, customer_id: UUID, tag_key: str, consumer_id: UUID | None = None) -> CustomerTag | None:
    """
    Retrieve a specific tag for a customer.
    
    Args:
        db: Database session
        customer_id: Customer UUID
        tag_key: Tag key
        consumer_id: Consumer UUID for ownership validation (required for security)
    
    Returns:
        Tag if found and belongs to consumer, None otherwise
    """
    query = db.query(CustomerTag).filter(
        CustomerTag.customer_id == customer_id,
        CustomerTag.tag_key == tag_key
    )
    
    # SECURITY: Filter by consumer_id to prevent cross-consumer data access
    if consumer_id is not None:
        query = query.filter(CustomerTag.consumer_id == consumer_id)
    
    return query.first()


def delete_customer_tag(db: Session, customer_id: UUID, tag_key: str, consumer_id: UUID | None = None) -> bool:
    """
    Delete a specific tag for a customer.
    
    Args:
        db: Database session
        customer_id: Customer UUID
        tag_key: Tag key
        consumer_id: Consumer UUID for ownership validation (required for security)
    
    Returns:
        True if deleted, False if not found or doesn't belong to consumer
    """
    query = db.query(CustomerTag).filter(
        CustomerTag.customer_id == customer_id,
        CustomerTag.tag_key == tag_key
    )
    
    # SECURITY: Filter by consumer_id to prevent cross-consumer data access
    if consumer_id is not None:
        query = query.filter(CustomerTag.consumer_id == consumer_id)
    
    db_tag = query.first()
    
    if db_tag:
        db.delete(db_tag)
        db.commit()
        return True
    return False


def update_customer_tag_key(db: Session, customer_id: UUID, old_tag_key: str, new_tag_key: str, consumer_id: UUID | None = None) -> CustomerTag | None:
    """
    Update tag key for a customer.
    
    Args:
        db: Database session
        customer_id: Customer UUID
        old_tag_key: Current tag key
        new_tag_key: New tag key
        consumer_id: Consumer UUID for ownership validation (required for security)
    
    Returns:
        Updated tag or None if not found or doesn't belong to consumer
    """
    query = db.query(CustomerTag).filter(
        CustomerTag.customer_id == customer_id,
        CustomerTag.tag_key == old_tag_key
    )
    
    # SECURITY: Filter by consumer_id to prevent cross-consumer data access
    if consumer_id is not None:
        query = query.filter(CustomerTag.consumer_id == consumer_id)
    
    db_tag = query.first()
    
    if db_tag:
        db_tag.tag_key = new_tag_key
        db.commit()
        db.refresh(db_tag)
        return db_tag
    return None


def update_customer_tag_value(db: Session, customer_id: UUID, tag_key: str, new_tag_value: str, consumer_id: UUID | None = None) -> CustomerTag | None:
    """
    Update tag value for a customer.
    
    Args:
        db: Database session
        customer_id: Customer UUID
        tag_key: Tag key
        new_tag_value: New tag value
        consumer_id: Consumer UUID for ownership validation (required for security)
    
    Returns:
        Updated tag or None if not found or doesn't belong to consumer
    """
    query = db.query(CustomerTag).filter(
        CustomerTag.customer_id == customer_id,
        CustomerTag.tag_key == tag_key
    )
    
    # SECURITY: Filter by consumer_id to prevent cross-consumer data access
    if consumer_id is not None:
        query = query.filter(CustomerTag.consumer_id == consumer_id)
    
    db_tag = query.first()
    
    if db_tag:
        db_tag.tag_value = new_tag_value
        db.commit()
        db.refresh(db_tag)
        return db_tag
    return None


# Deprecated: create_customer_analytics_snapshot removed
# Analytics aggregation now handled by Airflow ETL job (consumer-level, not per-customer)
# Table renamed: customer_analytics -> consumer_analytics
# See: airflow/dags/consumer_analytics_etl.py


# Consumer Management Functions

def generate_api_key() -> str:
    """Generate cryptographically secure API key (32 bytes = 64 hex chars)."""
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """Hash API key using SHA-256."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def create_consumer(db: Session, name: str, description: Optional[str] = None) -> tuple[Consumer, str]:
    """
    Create new consumer with auto-generated API key.
    Returns tuple of (Consumer, plaintext_api_key).
    """
    # Create consumer
    db_consumer = Consumer(
        name=name,
        description=description,
        status="active"
    )
    db.add(db_consumer)
    db.flush()  # Get consumer_id without committing
    
    # Generate and hash API key
    plaintext_key = generate_api_key()
    hashed_key = hash_api_key(plaintext_key)
    
    # Create API key record
    db_api_key = ConsumerApiKey(
        consumer_id=db_consumer.consumer_id,
        api_key_hash=hashed_key,
        status="active",
        created_by="system"
    )
    db.add(db_api_key)
    
    # Create consumer creation event with pending status (will be published by route handler)
    db_event = CustomerEvent(
        customer_id=db_consumer.consumer_id,  # Using consumer_id as customer_id for this event type
        consumer_id=db_consumer.consumer_id,
        event_type="consumer_created",
        source_service="POST: /consumer/data",
        payload_json={"consumer_id": str(db_consumer.consumer_id), "name": name},
        metadata_json={"created_by": "system"},
        publish_status="pending",  # Will be published by route handler
        publish_try_count=1,
        publish_last_tried_at=datetime.utcnow()
    )
    db.add(db_event)
    
    db.commit()
    db.refresh(db_consumer)
    db.refresh(db_event)
    
    return db_consumer, plaintext_key, db_event


def get_consumer_by_id(db: Session, consumer_id: UUID) -> Optional[Consumer]:
    """Retrieve consumer by ID."""
    return db.query(Consumer).filter(Consumer.consumer_id == consumer_id).first()


def get_consumer_by_api_key(db: Session, api_key: str) -> Optional[Consumer]:
    """
    Authenticate API key and return associated consumer.
    Returns None if key invalid or expired.
    """
    hashed_key = hash_api_key(api_key)
    
    db_api_key = db.query(ConsumerApiKey).filter(
        ConsumerApiKey.api_key_hash == hashed_key,
        ConsumerApiKey.status == "active"
    ).first()
    
    if not db_api_key:
        return None
    
    # Check expiration
    if db_api_key.expires_at and db_api_key.expires_at < func.now():
        return None
    
    # Update last_used_at
    db_api_key.last_used_at = func.now()
    db.commit()
    
    # Return consumer
    return db.query(Consumer).filter(
        Consumer.consumer_id == db_api_key.consumer_id,
        Consumer.status == "active"
    ).first()


def get_consumer_by_name(db: Session, name: str) -> Optional[Consumer]:
    """Retrieve consumer by name."""
    return db.query(Consumer).filter(Consumer.name == name).first()


def rotate_api_key(db: Session, consumer_id: UUID) -> Optional[str]:
    """
    Deactivate existing active key and generate new one.
    Returns plaintext new key or None if consumer not found.
    """
    # Verify consumer exists and is active
    consumer = get_consumer_by_id(db, consumer_id)
    if not consumer or consumer.status != "active":
        return None
    
    # Deactivate existing active keys
    db.query(ConsumerApiKey).filter(
        ConsumerApiKey.consumer_id == consumer_id,
        ConsumerApiKey.status == "active"
    ).update({"status": "deactivated"})
    
    # Generate new key
    plaintext_key = generate_api_key()
    hashed_key = hash_api_key(plaintext_key)
    
    db_api_key = ConsumerApiKey(
        consumer_id=consumer_id,
        api_key_hash=hashed_key,
        status="active",
        created_by="consumer_rotation"
    )
    db.add(db_api_key)
    
    # Create key rotation event with pending status (will be published by route handler)
    db_event = CustomerEvent(
        customer_id=consumer_id,  # Using consumer_id as customer_id for this event type
        consumer_id=consumer_id,
        event_type="consumer_key_rotated",
        source_service="POST: /consumer/me/api-key/rotate",
        payload_json={"consumer_id": str(consumer_id)},
        metadata_json={"rotated_at": datetime.utcnow().isoformat(), "rotated_by": "consumer"},
        publish_status="pending",  # Will be published by route handler
        publish_try_count=1,
        publish_last_tried_at=datetime.utcnow()
    )
    db.add(db_event)
    
    db.commit()
    db.refresh(db_event)
    
    return plaintext_key, db_event


def deactivate_api_key(db: Session, consumer_id: UUID):
    """
    Deactivate consumer's active API key.
    Returns (success: bool, event: CustomerEvent | None).
    """
    result = db.query(ConsumerApiKey).filter(
        ConsumerApiKey.consumer_id == consumer_id,
        ConsumerApiKey.status == "active"
    ).update({"status": "deactivated"})
    
    if result > 0:
        # Create key deactivation event with pending status (will be published by route handler)
        db_event = CustomerEvent(
            customer_id=consumer_id,
            consumer_id=consumer_id,
            event_type="consumer_key_deactivated",
            source_service="POST: /consumer/me/api-key/deactivate",
            payload_json={"consumer_id": str(consumer_id)},
            metadata_json={"deactivated_at": datetime.utcnow().isoformat(), "deactivated_by": "consumer"},
            publish_status="pending",  # Will be published by route handler
            publish_try_count=1,
            publish_last_tried_at=datetime.utcnow()
        )
        db.add(db_event)
        db.commit()
        db.refresh(db_event)
        return True, db_event
    
    return False, None


def get_api_key_status(db: Session, consumer_id: UUID) -> Optional[ConsumerApiKey]:
    """Get active API key metadata for consumer."""
    return db.query(ConsumerApiKey).filter(
        ConsumerApiKey.consumer_id == consumer_id,
        ConsumerApiKey.status == "active"
    ).first()


def change_consumer_status(db: Session, consumer_id: UUID, new_status: str):
    """
    Change consumer status (admin operation).
    Returns (consumer: Consumer | None, event: CustomerEvent | None).
    """
    consumer = get_consumer_by_id(db, consumer_id)
    if not consumer:
        return None, None
    
    old_status = consumer.status
    consumer.status = new_status
    
    # Create status change event with pending status (will be published by route handler)
    db_event = CustomerEvent(
        customer_id=consumer_id,
        consumer_id=consumer_id,
        event_type="consumer_status_changed",
        source_service="POST: /admin/consumer/{consumer_id}/change-status",
        payload_json={
            "consumer_id": str(consumer_id),
            "old_status": old_status,
            "new_status": new_status
        },
        metadata_json={"changed_at": datetime.utcnow().isoformat(), "changed_by": "admin"},
        publish_status="pending",  # Will be published by route handler
        publish_try_count=1,
        publish_last_tried_at=datetime.utcnow()
    )
    db.add(db_event)
    
    db.commit()
    db.refresh(consumer)
    db.refresh(db_event)
    return consumer, db_event


# Analytics API Functions (Power BI Integration - Task 1)

def get_analytics_snapshots(
    db: Session,
    authenticated_consumer_id: UUID,
    start_date: datetime,
    end_date: datetime,
    snapshot_type: str,
    page: int,
    page_size: int
) -> tuple[List[Dict[str, Any]], int]:
    """
    Retrieve analytics snapshots with consumer isolation and pagination.
    
    Args:
        db: Database session
        authenticated_consumer_id: Consumer UUID from API key (for security filtering)
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        snapshot_type: Filter by type - "all", "consumer", or "global"
        page: Page number (1-indexed)
        page_size: Number of records per page
    
    Returns:
        Tuple of (snapshots_list, total_count)
    
    Security:
        - Consumer sees only their own snapshots + global snapshots
        - Cannot query other consumers' data
    """
    # Base query with security filter
    base_query = db.query(
        ConsumerAnalytics.analytics_id,
        ConsumerAnalytics.consumer_id,
        Consumer.name.label('consumer_name'),
        ConsumerAnalytics.snapshot_timestamp,
        ConsumerAnalytics.metrics_json
    ).outerjoin(
        Consumer, ConsumerAnalytics.consumer_id == Consumer.consumer_id
    ).filter(
        # Security: Only own data + global
        (ConsumerAnalytics.consumer_id == authenticated_consumer_id) | 
        (ConsumerAnalytics.consumer_id == None)
    ).filter(
        # Date range filter
        ConsumerAnalytics.snapshot_timestamp >= start_date,
        ConsumerAnalytics.snapshot_timestamp <= end_date
    )
    
    # Apply snapshot_type filter
    if snapshot_type == "consumer":
        base_query = base_query.filter(ConsumerAnalytics.consumer_id != None)
    elif snapshot_type == "global":
        base_query = base_query.filter(ConsumerAnalytics.consumer_id == None)
    # "all" - no additional filter
    
    # Count total records (before pagination)
    total_count = base_query.count()
    
    # Apply pagination and ordering
    offset = (page - 1) * page_size
    results = base_query.order_by(
        desc(ConsumerAnalytics.snapshot_timestamp)
    ).limit(page_size).offset(offset).all()
    
    # Transform to dict format
    snapshots = []
    for row in results:
        snapshots.append({
            "analytics_id": row.analytics_id,
            "consumer_id": row.consumer_id,
            "consumer_name": row.consumer_name,
            "snapshot_timestamp": row.snapshot_timestamp,
            "snapshot_type": "GLOBAL" if row.consumer_id is None else "CONSUMER",
            "metrics": row.metrics_json
        })
    
    return snapshots, total_count
