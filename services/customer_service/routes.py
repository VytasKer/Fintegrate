from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from uuid import UUID
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

router = APIRouter()


@router.post("/customer/data", response_model=CustomerCreateStandardResponse, status_code=status.HTTP_201_CREATED)
def create_customer(customer: CustomerCreate, db: Session = Depends(get_db)):
    """
    Create a new customer.
    
    - **name**: Customer name (required)
    
    Returns: Standardized response with customer_id, status, created_at
    """
    try:
        db_customer = crud.create_customer(db, customer)
        response_data = CustomerCreateResponse(
            customer_id=db_customer.customer_id,
            status=db_customer.status,
            created_at=db_customer.created_at
        )
        return success_response(response_data.model_dump(), status.HTTP_201_CREATED)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                f"Failed to create customer: {str(e)}"
            )
        )


@router.get("/customer/data", response_model=CustomerGetStandardResponse)
def get_customer(customer_id: UUID, db: Session = Depends(get_db)):
    """
    Retrieve customer information by ID.
    
    - **customer_id**: UUID of the customer (query parameter)
    
    Returns: Standardized response with customer_id, name, status, created_at, updated_at
    """
    try:
        db_customer = crud.get_customer(db, customer_id)
        if db_customer is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=error_response(
                    status.HTTP_404_NOT_FOUND,
                    f"Customer with id {customer_id} not found"
                )
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
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                f"Failed to retrieve customer: {str(e)}"
            )
        )


@router.delete("/customer/data", response_model=CustomerDeleteStandardResponse, status_code=status.HTTP_200_OK)
def delete_customer(customer_id: UUID, db: Session = Depends(get_db)):
    """
    Delete customer by ID.
    
    - **customer_id**: UUID of the customer (query parameter)
    
    Returns: Standardized response with 200 OK if successful, 404 if not found
    """
    try:
        deleted = crud.delete_customer(db, customer_id)
        if not deleted:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=error_response(
                    status.HTTP_404_NOT_FOUND,
                    f"Customer with id {customer_id} not found"
                )
            )
        
        return success_response(
            {"message": "Customer deleted successfully"},
            status.HTTP_200_OK
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                f"Failed to delete customer: {str(e)}"
            )
        )


@router.patch("/customer/change-status", response_model=CustomerStatusChangeStandardResponse, status_code=status.HTTP_200_OK)
def change_customer_status(status_change: CustomerStatusChange, db: Session = Depends(get_db)):
    """
    Change customer status (ACTIVE/INACTIVE).
    
    - **customer_id**: UUID of the customer
    - **status**: New status (ACTIVE or INACTIVE)
    
    Returns: Standardized response with call_status only
    """
    try:
        db_customer = crud.get_customer(db, status_change.customer_id)
        
        if db_customer is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=error_response(
                    status.HTTP_404_NOT_FOUND,
                    f"Customer with id {status_change.customer_id} not found"
                )
            )
        
        # Check if customer already has the requested status
        if db_customer.status == status_change.status:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=error_response(
                    status.HTTP_409_CONFLICT,
                    f"Customer {status_change.customer_id} is already {status_change.status}"
                )
            )
        
        # Update status
        crud.update_customer_status(db, status_change.customer_id, status_change.status)
        
        return success_response({}, status.HTTP_200_OK)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                f"Failed to change customer status: {str(e)}"
            )
        )
