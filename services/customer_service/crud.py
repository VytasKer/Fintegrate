from sqlalchemy.orm import Session
from uuid import UUID
from typing import Dict, Any, List
from services.customer_service.models import Customer, CustomerEvent, CustomerTag, CustomerArchive, AuditLog
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
    metadata: Dict[str, Any] | None = None
) -> CustomerEvent:
    """Create event entry in customer_events table."""
    db_event = CustomerEvent(
        customer_id=customer_id,
        event_type=event_type,
        source_service=source_service,
        payload_json=payload,
        metadata_json=metadata
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
