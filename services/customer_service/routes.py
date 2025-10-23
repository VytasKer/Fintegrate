from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from uuid import UUID
import uuid
from services.customer_service.database import get_db
from services.customer_service.schemas import (
    CustomerCreate, 
    CustomerCreateResponse, 
    CustomerResponse,
    CustomerStatusChange,
    CustomerCreateStandardResponse,
    CustomerGetStandardResponse,
    CustomerDeleteStandardResponse,
    CustomerStatusChangeStandardResponse
)
from services.customer_service import crud
from services.shared.response_handler import success_response, error_response
from services.shared.audit_logger import log_error_to_audit

router = APIRouter()


@router.post("/customer/data", response_model=CustomerCreateStandardResponse, status_code=status.HTTP_201_CREATED)
def create_customer(customer: CustomerCreate, request: Request, db: Session = Depends(get_db)):
    """
    Create a new customer.
    
    - **name**: Customer name (required)
    
    Returns: Standardized response with customer_id, status, created_at
    """
    try:
        db_customer = crud.create_customer(db, customer)
        
        # Create event entry
        crud.create_customer_event(
            db=db,
            customer_id=db_customer.customer_id,
            event_type="customer_creation",
            source_service="POST: /customer/data",
            payload={
                "customer_id": str(db_customer.customer_id),
                "name": db_customer.name,
                "status": db_customer.status
            },
            metadata={
                "created_at": db_customer.created_at.isoformat()
            }
        )
        
        response_data = CustomerCreateResponse(
            customer_id=db_customer.customer_id,
            status=db_customer.status,
            created_at=db_customer.created_at
        )
        return success_response(response_data.model_dump(), status.HTTP_201_CREATED)
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to create customer: {str(e)}"
        )
        
        # Log error to audit
        log_error_to_audit(
            db=db,
            request=request,
            entity="customer",
            entity_id=str(uuid.uuid4()),  # No customer_id available yet
            action="create_customer",
            error_response=error_resp
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp
        )


@router.get("/customer/data", response_model=CustomerGetStandardResponse)
def get_customer(customer_id: UUID, request: Request, db: Session = Depends(get_db)):
    """
    Retrieve customer information by ID.
    
    - **customer_id**: UUID of the customer (query parameter)
    
    Returns: Standardized response with customer_id, name, status, created_at, updated_at
    """
    try:
        db_customer = crud.get_customer(db, customer_id)
        if db_customer is None:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Customer with id {customer_id} not found"
            )
            
            # Log error to audit
            log_error_to_audit(
                db=db,
                request=request,
                entity="customer",
                entity_id=customer_id,
                action="get_customer",
                error_response=error_resp
            )
            
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=error_resp
            )
        
        response_data = CustomerResponse(
            customer_id=db_customer.customer_id,
            name=db_customer.name,
            status=db_customer.status,
            created_at=db_customer.created_at,
            updated_at=db_customer.updated_at
        )
        return success_response(response_data.model_dump(), status.HTTP_200_OK)
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to retrieve customer: {str(e)}"
        )
        
        # Log error to audit
        log_error_to_audit(
            db=db,
            request=request,
            entity="customer",
            entity_id=customer_id,
            action="get_customer",
            error_response=error_resp
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp
        )


@router.delete("/customer/data", response_model=CustomerDeleteStandardResponse, status_code=status.HTTP_200_OK)
def delete_customer(customer_id: UUID, request: Request, db: Session = Depends(get_db)):
    """
    Delete customer by ID (archive + physical deletion).
    
    Process:
    1. Archive customer data and tags to customer_archive
    2. Log deletion event in customer_events
    3. Delete all tags from customer_tags
    4. Physically delete customer from customers table
    
    - **customer_id**: UUID of the customer (query parameter)
    
    Returns: Standardized response with 200 OK if successful, 404 if not found
    """
    try:
        # Step 1: Validate customer exists
        db_customer = crud.get_customer(db, customer_id)
        if not db_customer:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Customer with id {customer_id} not found"
            )
            
            # Log error to audit
            log_error_to_audit(
                db=db,
                request=request,
                entity="customer",
                entity_id=customer_id,
                action="delete_customer",
                error_response=error_resp
            )
            
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=error_resp
            )
        
        # Step 2: Capture snapshot (customer + tags)
        customer_tags = crud.get_customer_tags(db, customer_id)
        
        snapshot = {
            "customer": {
                "customer_id": str(db_customer.customer_id),
                "name": db_customer.name,
                "status": db_customer.status,
                "created_at": db_customer.created_at.isoformat(),
                "updated_at": db_customer.updated_at.isoformat()
            },
            "tags": [
                {
                    "tag_id": str(tag.tag_id),
                    "tag_key": tag.tag_key,
                    "tag_value": tag.tag_value,
                    "created_at": tag.created_at.isoformat()
                }
                for tag in customer_tags
            ]
        }
        
        # Step 3: Archive customer
        crud.create_customer_archive(
            db=db,
            customer_id=customer_id,
            snapshot=snapshot,
            trigger_event="customer_deletion"
        )
        
        # Step 4: Log deletion event
        crud.create_customer_event(
            db=db,
            customer_id=customer_id,
            event_type="customer_deletion",
            source_service="DELETE: /customer/data",
            payload={
                "customer_id": str(customer_id),
                "name": db_customer.name,
                "status": db_customer.status,
                "tags_count": len(customer_tags)
            },
            metadata={
                "deleted_at": db_customer.updated_at.isoformat(),
                "archived": True
            }
        )
        
        # Step 5: Delete tags
        tags_deleted = crud.delete_customer_tags(db, customer_id)
        
        # Step 6: Delete customer
        crud.delete_customer(db, customer_id)
        
        return success_response(
            {
                "message": "Customer deleted successfully",
                "archived": True,
                "tags_deleted": tags_deleted
            },
            status.HTTP_200_OK
        )
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to delete customer: {str(e)}"
        )
        
        # Log error to audit
        log_error_to_audit(
            db=db,
            request=request,
            entity="customer",
            entity_id=customer_id,
            action="delete_customer",
            error_response=error_resp
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp
        )


@router.patch("/customer/change-status", response_model=CustomerStatusChangeStandardResponse, status_code=status.HTTP_200_OK)
def change_customer_status(status_change: CustomerStatusChange, request: Request, db: Session = Depends(get_db)):
    """
    Change customer status (ACTIVE/INACTIVE).
    
    - **customer_id**: UUID of the customer
    - **status**: New status (ACTIVE or INACTIVE)
    
    Returns: Standardized response with detail only
    """
    try:
        db_customer = crud.get_customer(db, status_change.customer_id)
        
        if db_customer is None:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Customer with id {status_change.customer_id} not found"
            )
            
            # Log error to audit
            log_error_to_audit(
                db=db,
                request=request,
                entity="customer",
                entity_id=status_change.customer_id,
                action="change_customer_status",
                error_response=error_resp
            )
            
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=error_resp
            )
        
        # Check if customer already has the requested status
        if db_customer.status == status_change.status:
            error_resp = error_response(
                status.HTTP_409_CONFLICT,
                f"Customer {status_change.customer_id} is already {status_change.status}"
            )
            
            # Log error to audit
            log_error_to_audit(
                db=db,
                request=request,
                entity="customer",
                entity_id=status_change.customer_id,
                action="change_customer_status",
                error_response=error_resp
            )
            
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=error_resp
            )
        
        # Store old status for event
        old_status = db_customer.status
        
        # Update status
        crud.update_customer_status(db, status_change.customer_id, status_change.status)
        
        # Create event entry
        crud.create_customer_event(
            db=db,
            customer_id=status_change.customer_id,
            event_type="customer_status_change",
            source_service="PATCH: /customer/change-status",
            payload={
                "customer_id": str(status_change.customer_id),
                "old_status": old_status,
                "new_status": status_change.status
            },
            metadata={
                "changed_at": db_customer.updated_at.isoformat()
            }
        )
        
        return success_response({}, status.HTTP_200_OK)
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to change customer status: {str(e)}"
        )
        
        # Log error to audit
        log_error_to_audit(
            db=db,
            request=request,
            entity="customer",
            entity_id=status_change.customer_id,
            action="change_customer_status",
            error_response=error_resp
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp
        )
