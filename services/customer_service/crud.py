from sqlalchemy.orm import Session
from uuid import UUID
from services.customer_service.models import Customer
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
    """Delete customer by ID. Returns True if deleted, False if not found."""
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
