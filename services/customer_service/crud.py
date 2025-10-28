from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from uuid import UUID
from typing import Dict, Any, List
from services.customer_service.models import Customer, CustomerEvent, CustomerTag, CustomerArchive, AuditLog, CustomerAnalytics
from services.customer_service.schemas import CustomerCreate


def create_customer(db: Session, customer_data: CustomerCreate) -> Customer:
    """Create new customer in database."""
    db_customer = Customer(
        name=customer_data.name,
        status="ACTIVE"
    )
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer


def get_customer(db: Session, customer_id: UUID) -> Customer | None:
    """Retrieve customer by ID."""
    return db.query(Customer).filter(Customer.customer_id == customer_id).first()


def delete_customer(db: Session, customer_id: UUID) -> bool:
    """Physically delete customer by ID. Returns True if deleted, False if not found."""
    db_customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if db_customer:
        db.delete(db_customer)
        db.commit()
        return True
    return False


def update_customer_status(db: Session, customer_id: UUID, new_status: str) -> Customer | None:
    """Update customer status. Returns updated customer or None if not found."""
    db_customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
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
    publish_failure_reason: str | None = None
) -> CustomerEvent:
    """Create event entry in customer_events table with outbox pattern support."""
    db_event = CustomerEvent(
        customer_id=customer_id,
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


def get_customer_tags(db: Session, customer_id: UUID) -> List[CustomerTag]:
    """Retrieve all tags for a customer."""
    return db.query(CustomerTag).filter(CustomerTag.customer_id == customer_id).all()


def delete_customer_tags(db: Session, customer_id: UUID) -> int:
    """Delete all tags for a customer. Returns count of deleted tags."""
    count = db.query(CustomerTag).filter(CustomerTag.customer_id == customer_id).delete()
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


def create_customer_tag(db: Session, customer_id: UUID, tag_key: str, tag_value: str) -> CustomerTag:
    """Create or update a tag for a customer."""
    # Check if tag already exists
    existing_tag = db.query(CustomerTag).filter(
        CustomerTag.customer_id == customer_id,
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
            tag_key=tag_key,
            tag_value=tag_value
        )
        db.add(db_tag)
        db.commit()
        db.refresh(db_tag)
        return db_tag


def get_customer_tag(db: Session, customer_id: UUID, tag_key: str) -> CustomerTag | None:
    """Retrieve a specific tag for a customer."""
    return db.query(CustomerTag).filter(
        CustomerTag.customer_id == customer_id,
        CustomerTag.tag_key == tag_key
    ).first()


def delete_customer_tag(db: Session, customer_id: UUID, tag_key: str) -> bool:
    """Delete a specific tag for a customer. Returns True if deleted, False if not found."""
    db_tag = db.query(CustomerTag).filter(
        CustomerTag.customer_id == customer_id,
        CustomerTag.tag_key == tag_key
    ).first()
    
    if db_tag:
        db.delete(db_tag)
        db.commit()
        return True
    return False


def update_customer_tag_key(db: Session, customer_id: UUID, old_tag_key: str, new_tag_key: str) -> CustomerTag | None:
    """Update tag key for a customer. Returns updated tag or None if not found."""
    db_tag = db.query(CustomerTag).filter(
        CustomerTag.customer_id == customer_id,
        CustomerTag.tag_key == old_tag_key
    ).first()
    
    if db_tag:
        db_tag.tag_key = new_tag_key
        db.commit()
        db.refresh(db_tag)
        return db_tag
    return None


def update_customer_tag_value(db: Session, customer_id: UUID, tag_key: str, new_tag_value: str) -> CustomerTag | None:
    """Update tag value for a customer. Returns updated tag or None if not found."""
    db_tag = db.query(CustomerTag).filter(
        CustomerTag.customer_id == customer_id,
        CustomerTag.tag_key == tag_key
    ).first()
    
    if db_tag:
        db_tag.tag_value = new_tag_value
        db.commit()
        db.refresh(db_tag)
        return db_tag
    return None


def create_customer_analytics_snapshot(db: Session, customer_id: UUID) -> CustomerAnalytics:
    """
    Create an analytics snapshot for a customer.
    Captures current state: name, status, event count, tags, and calculated metrics.
    Multiple snapshots can exist for the same customer to track changes over time.
    """
    # Get customer data
    customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not customer:
        raise ValueError(f"Customer {customer_id} not found")
    
    # Get total event count
    total_events = db.query(func.count(CustomerEvent.event_id)).filter(
        CustomerEvent.customer_id == customer_id
    ).scalar() or 0
    
    # Get last event time
    last_event = db.query(CustomerEvent).filter(
        CustomerEvent.customer_id == customer_id
    ).order_by(desc(CustomerEvent.created_at)).first()
    last_event_time = last_event.created_at if last_event else None
    
    # Get all tags as JSONB
    tags = db.query(CustomerTag).filter(CustomerTag.customer_id == customer_id).all()
    tags_json = {tag.tag_key: tag.tag_value for tag in sorted(tags, key=lambda t: t.tag_key)}
    
    # Calculate metrics (example metrics - can be expanded)
    from datetime import datetime
    account_age_days = 0
    if customer.created_at:
        age_delta = datetime.now() - customer.created_at
        account_age_days = age_delta.days
    
    metrics_json = {
        "total_events": total_events,
        "tags_count": len(tags),
        "account_age_days": account_age_days,
        "status": customer.status
    }
    
    # Create analytics snapshot
    analytics_snapshot = CustomerAnalytics(
        customer_id=customer_id,
        name=customer.name,
        status=customer.status,
        created_at=customer.created_at,
        last_event_time=last_event_time,
        total_events=total_events,
        tags_json=tags_json,
        metrics_json=metrics_json
    )
    
    db.add(analytics_snapshot)
    db.commit()
    db.refresh(analytics_snapshot)
    return analytics_snapshot
