from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from uuid import UUID
import uuid
from datetime import datetime
from services.customer_service.database import get_db
from services.customer_service.schemas import (
    CustomerCreate, 
    CustomerCreateResponse, 
    CustomerResponse,
    CustomerStatusChange,
    CustomerTagCreate,
    CustomerTagGet,
    CustomerTagGetResponse,
    CustomerTagDelete,
    CustomerTagKeyUpdate,
    CustomerTagValueUpdate,
    CustomerAnalyticsCreate,
    CustomerCreateStandardResponse,
    CustomerGetStandardResponse,
    CustomerDeleteStandardResponse,
    CustomerStatusChangeStandardResponse,
    CustomerTagStandardResponse,
    CustomerTagGetStandardResponse,
    EventResendRequest,
    EventResendStandardResponse,
    EventHealthStandardResponse,
    EventConfirmDeliveryRequest,
    EventConfirmDeliveryStandardResponse,
    EventRedeliverRequest,
    EventRedeliverStandardResponse,
    ConsumerCreate,
    ConsumerCreateStandardResponse,
    ConsumerRotateKeyStandardResponse,
    ConsumerGetStandardResponse,
    ConsumerKeyStatusStandardResponse,
    ConsumerChangeStatusRequest,
    ConsumerChangeStatusStandardResponse
)
from services.customer_service import crud
from services.shared.response_handler import success_response, error_response
from services.shared.audit_logger import log_error_to_audit
from services.shared.event_publisher import get_event_publisher
from services.customer_service.middleware import verify_api_key

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
        
        # Create event entry first with 'pending' status (outbox pattern)
        event = crud.create_customer_event(
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
            },
            publish_status="pending",  # Default to pending
            published_at=None,
            publish_try_count=1,
            publish_last_tried_at=datetime.utcnow(),
            publish_failure_reason=None
        )
        
        # Now try to publish to RabbitMQ
        publish_success = False
        try:
            print(f"Attempting to publish event {event.event_id}: customer.creation for customer {db_customer.customer_id}")
            publisher = get_event_publisher()
            if publisher:
                publish_success = publisher.publish_event(
                    event_id=event.event_id,  # Use the event_id from DB
                    event_type="customer_creation",
                    customer_id=db_customer.customer_id,
                    name=db_customer.name,
                    status=db_customer.status,
                    created_at=event.created_at
                )
                
                if publish_success:
                    # Update event record - successfully published
                    event.publish_status = "published"
                    event.published_at = datetime.utcnow()
                    event.publish_failure_reason = None
                    # Track initial delivery attempt
                    event.deliver_try_count = 1
                    event.deliver_last_tried_at = datetime.utcnow()
                    db.commit()
                    print(f"RabbitMQ publish successful, event marked as published")
                else:
                    # Update failure reason
                    event.publish_failure_reason = "RabbitMQ publish returned False"
                    db.commit()
                    print(f"RabbitMQ publish failed: {event.publish_failure_reason}")
            else:
                # Update failure reason
                event.publish_failure_reason = "EventPublisher connection is None"
                db.commit()
                print(f"Publisher is None - RabbitMQ connection failed")
                
        except Exception as mq_error:
            # Update failure reason
            event.publish_failure_reason = f"{type(mq_error).__name__}: {str(mq_error)}"
            db.commit()
            print(f"RabbitMQ publish exception (non-blocking): {event.publish_failure_reason}")
            import traceback
            traceback.print_exc()
        
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
    
    Returns: Standardized response with customer_id, name, status, created_at, updated_at, tags
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
        
        # Get customer tags
        customer_tags = crud.get_customer_tags(db, customer_id)
        # Sort tags alphabetically by tag_key
        tags_dict = {tag.tag_key: tag.tag_value for tag in sorted(customer_tags, key=lambda t: t.tag_key)}
        
        response_data = CustomerResponse(
            customer_id=db_customer.customer_id,
            name=db_customer.name,
            status=db_customer.status,
            created_at=db_customer.created_at,
            updated_at=db_customer.updated_at,
            tags=tags_dict
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


@router.post("/customer/tag", response_model=CustomerTagStandardResponse, status_code=status.HTTP_201_CREATED)
def create_customer_tags(tag_data: CustomerTagCreate, request: Request, db: Session = Depends(get_db)):
    """
    Create multiple tags for a customer.
    
    - **customer_id**: UUID of the customer
    - **tag_keys**: List of tag keys
    - **tag_values**: List of tag values (positional correspondence with keys)
    
    Returns: Standardized response
    """
    try:
        # Validate customer exists
        db_customer = crud.get_customer(db, tag_data.customer_id)
        if not db_customer:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Customer with id {tag_data.customer_id} not found"
            )
            log_error_to_audit(db, request, "customer_tag", tag_data.customer_id, "create_tags", error_resp)
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)
        
        # Validate arrays have same length
        if len(tag_data.tag_keys) != len(tag_data.tag_values):
            error_resp = error_response(
                status.HTTP_400_BAD_REQUEST,
                "tag_keys and tag_values arrays must have the same length"
            )
            log_error_to_audit(db, request, "customer_tag", tag_data.customer_id, "create_tags", error_resp)
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_resp)
        
        # Create tags
        for key, value in zip(tag_data.tag_keys, tag_data.tag_values):
            crud.create_customer_tag(db, tag_data.customer_id, key, value)
        
        return success_response({}, status.HTTP_201_CREATED)
    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to create tags: {str(e)}")
        log_error_to_audit(db, request, "customer_tag", tag_data.customer_id, "create_tags", error_resp)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.get("/customer/tag-value", response_model=CustomerTagGetStandardResponse)
def get_customer_tag_value(customer_id: UUID, tag_key: str, request: Request, db: Session = Depends(get_db)):
    """
    Retrieve tag value for a customer by tag key.
    
    - **customer_id**: UUID of the customer (query parameter)
    - **tag_key**: Tag key (query parameter)
    
    Returns: Tag value
    """
    try:
        db_tag = crud.get_customer_tag(db, customer_id, tag_key)
        if not db_tag:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Tag '{tag_key}' not found for customer {customer_id}"
            )
            log_error_to_audit(db, request, "customer_tag", customer_id, "get_tag_value", error_resp)
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)
        
        response_data = CustomerTagGetResponse(tag_value=db_tag.tag_value)
        return success_response(response_data.model_dump(), status.HTTP_200_OK)
    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to retrieve tag: {str(e)}")
        log_error_to_audit(db, request, "customer_tag", customer_id, "get_tag_value", error_resp)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.delete("/customer/tag", response_model=CustomerTagStandardResponse, status_code=status.HTTP_200_OK)
def delete_customer_tag(tag_delete: CustomerTagDelete, request: Request, db: Session = Depends(get_db)):
    """
    Delete a tag for a customer.
    
    - **customer_id**: UUID of the customer
    - **tag_key**: Tag key to delete
    
    Returns: Standardized response
    """
    try:
        deleted = crud.delete_customer_tag(db, tag_delete.customer_id, tag_delete.tag_key)
        if not deleted:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Tag '{tag_delete.tag_key}' not found for customer {tag_delete.customer_id}"
            )
            log_error_to_audit(db, request, "customer_tag", tag_delete.customer_id, "delete_tag", error_resp)
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)
        
        return success_response({}, status.HTTP_200_OK)
    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to delete tag: {str(e)}")
        log_error_to_audit(db, request, "customer_tag", tag_delete.customer_id, "delete_tag", error_resp)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.patch("/customer/tag-key", response_model=CustomerTagStandardResponse, status_code=status.HTTP_200_OK)
def update_customer_tag_key(tag_update: CustomerTagKeyUpdate, request: Request, db: Session = Depends(get_db)):
    """
    Update tag key for a customer.
    
    - **customer_id**: UUID of the customer
    - **tag_key**: Current tag key
    - **new_tag_key**: New tag key
    
    Returns: Standardized response
    """
    try:
        updated_tag = crud.update_customer_tag_key(db, tag_update.customer_id, tag_update.tag_key, tag_update.new_tag_key)
        if not updated_tag:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Tag '{tag_update.tag_key}' not found for customer {tag_update.customer_id}"
            )
            log_error_to_audit(db, request, "customer_tag", tag_update.customer_id, "update_tag_key", error_resp)
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)
        
        return success_response({}, status.HTTP_200_OK)
    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to update tag key: {str(e)}")
        log_error_to_audit(db, request, "customer_tag", tag_update.customer_id, "update_tag_key", error_resp)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.patch("/customer/tag-value", response_model=CustomerTagStandardResponse, status_code=status.HTTP_200_OK)
def update_customer_tag_value(tag_update: CustomerTagValueUpdate, request: Request, db: Session = Depends(get_db)):
    """
    Update tag value for a customer.
    
    - **customer_id**: UUID of the customer
    - **tag_key**: Tag key
    - **new_tag_value**: New tag value
    
    Returns: Standardized response
    """
    try:
        updated_tag = crud.update_customer_tag_value(db, tag_update.customer_id, tag_update.tag_key, tag_update.new_tag_value)
        if not updated_tag:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Tag '{tag_update.tag_key}' not found for customer {tag_update.customer_id}"
            )
            log_error_to_audit(db, request, "customer_tag", tag_update.customer_id, "update_tag_value", error_resp)
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)
        
        return success_response({}, status.HTTP_200_OK)
    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to update tag value: {str(e)}")
        log_error_to_audit(db, request, "customer_tag", tag_update.customer_id, "update_tag_value", error_resp)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.post("/customer/analytics", response_model=CustomerTagStandardResponse, status_code=status.HTTP_201_CREATED)
def create_customer_analytics(analytics_data: CustomerAnalyticsCreate, request: Request, db: Session = Depends(get_db)):
    """
    Create an analytics snapshot for a customer.
    
    Captures time-lapsed data including:
    - Customer info (name, status, created_at)
    - Event statistics (total_events, last_event_time)
    - Tags snapshot (tags_json)
    - Calculated metrics (metrics_json)
    
    Multiple snapshots can exist for the same customer to enable trend analysis.
    
    - **customer_id**: UUID of the customer
    
    Returns: Standardized response with empty data object
    """
    try:
        # Create analytics snapshot (this validates customer exists)
        crud.create_customer_analytics_snapshot(db, analytics_data.customer_id)
        
        return success_response({}, status.HTTP_201_CREATED)
    except ValueError as e:
        # Customer not found
        error_resp = error_response(
            status.HTTP_404_NOT_FOUND,
            str(e)
        )
        log_error_to_audit(db, request, "customer_analytics", analytics_data.customer_id, "create_snapshot", error_resp)
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)
    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to create analytics snapshot: {str(e)}")
        log_error_to_audit(db, request, "customer_analytics", analytics_data.customer_id, "create_snapshot", error_resp)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


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
        
        # Step 4: Create event entry first with 'pending' status (outbox pattern)
        event = crud.create_customer_event(
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
            },
            publish_status="pending",
            published_at=None,
            publish_try_count=1,
            publish_last_tried_at=datetime.utcnow(),
            publish_failure_reason=None
        )
        
        # Step 5: Try to publish to RabbitMQ
        try:
            print(f"Attempting to publish event {event.event_id}: customer.deletion for customer {customer_id}")
            publisher = get_event_publisher()
            if publisher:
                publish_success = publisher.publish_event(
                    event_id=event.event_id,
                    event_type="customer_deletion",
                    customer_id=customer_id,
                    name=db_customer.name,
                    status=db_customer.status,
                    created_at=event.created_at
                )
                
                if publish_success:
                    event.publish_status = "published"
                    event.published_at = datetime.utcnow()
                    event.publish_failure_reason = None
                    # Track initial delivery attempt
                    event.deliver_try_count = 1
                    event.deliver_last_tried_at = datetime.utcnow()
                    db.commit()
                    print(f"RabbitMQ publish successful, event marked as published")
                else:
                    event.publish_failure_reason = "RabbitMQ publish returned False"
                    db.commit()
                    print(f"RabbitMQ publish failed: {event.publish_failure_reason}")
            else:
                event.publish_failure_reason = "EventPublisher connection is None"
                db.commit()
                print(f"Publisher is None - RabbitMQ connection failed")
        except Exception as mq_error:
            event.publish_failure_reason = f"{type(mq_error).__name__}: {str(mq_error)}"
            db.commit()
            print(f"RabbitMQ publish exception (non-blocking): {event.publish_failure_reason}")
            import traceback
            traceback.print_exc()
        
        # Step 6: Delete tags
        tags_deleted = crud.delete_customer_tags(db, customer_id)
        
        # Step 7: Delete customer
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
        
        # Refresh to get updated timestamp
        db.refresh(db_customer)
        
        # Create event entry first with 'pending' status (outbox pattern)
        event = crud.create_customer_event(
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
            },
            publish_status="pending",
            published_at=None,
            publish_try_count=1,
            publish_last_tried_at=datetime.utcnow(),
            publish_failure_reason=None
        )
        
        # Try to publish to RabbitMQ
        try:
            print(f"Attempting to publish event {event.event_id}: customer.status.change for customer {status_change.customer_id}")
            publisher = get_event_publisher()
            if publisher:
                publish_success = publisher.publish_event(
                    event_id=event.event_id,
                    event_type="customer_status_change",
                    customer_id=status_change.customer_id,
                    name=db_customer.name,
                    status=status_change.status,
                    created_at=event.created_at
                )
                
                if publish_success:
                    event.publish_status = "published"
                    event.published_at = datetime.utcnow()
                    event.publish_failure_reason = None
                    # Track initial delivery attempt
                    event.deliver_try_count = 1
                    event.deliver_last_tried_at = datetime.utcnow()
                    db.commit()
                    print(f"RabbitMQ publish successful, event marked as published")
                else:
                    event.publish_failure_reason = "RabbitMQ publish returned False"
                    db.commit()
                    print(f"RabbitMQ publish failed: {event.publish_failure_reason}")
            else:
                event.publish_failure_reason = "EventPublisher connection is None"
                db.commit()
                print(f"Publisher is None - RabbitMQ connection failed")
        except Exception as mq_error:
            event.publish_failure_reason = f"{type(mq_error).__name__}: {str(mq_error)}"
            db.commit()
            print(f"RabbitMQ publish exception (non-blocking): {event.publish_failure_reason}")
            import traceback
            traceback.print_exc()
        
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


@router.post("/events/resend", response_model=EventResendStandardResponse, status_code=status.HTTP_200_OK)
def resend_pending_events(resend_request: EventResendRequest, request: Request, db: Session = Depends(get_db)):
    """
    Resend pending events to RabbitMQ (Transactional Outbox Pattern).
    
    - **period_in_days**: Search for events created within this many days (1-365)
    - **max_try_count**: Optional - Skip events that exceeded this retry count
    - **event_types**: Optional - Filter by specific event types
    
    Returns: Summary of resend operation with failed event details
    """
    try:
        from datetime import timedelta
        from services.customer_service.models import CustomerEvent
        from sqlalchemy import and_
        
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=resend_request.period_in_days)
        
        # Build query filters
        filters = [
            CustomerEvent.created_at > cutoff_date,
            CustomerEvent.publish_status == 'pending'
        ]
        
        if resend_request.max_try_count is not None:
            filters.append(CustomerEvent.publish_try_count < resend_request.max_try_count)
        
        if resend_request.event_types:
            filters.append(CustomerEvent.event_type.in_(resend_request.event_types))
        
        # Query pending events
        pending_events = db.query(CustomerEvent).filter(and_(*filters)).all()
        
        # Initialize counters
        total_pending = len(pending_events)
        attempted = 0
        succeeded = 0
        failed = 0
        skipped = 0
        failed_events_list = []
        
        # Get publisher
        publisher = get_event_publisher()
        
        if not publisher:
            # If RabbitMQ is completely unavailable, return early
            from services.customer_service.schemas import EventResendResponseData, EventResendSummary
            response_data = EventResendResponseData(
                summary=EventResendSummary(
                    total_pending=total_pending,
                    attempted=0,
                    succeeded=0,
                    failed=0,
                    skipped=total_pending
                ),
                failed_events=[]
            )
            return success_response(response_data.model_dump(), status.HTTP_200_OK)
        
        # Attempt to republish each event
        for event in pending_events:
            # Check if should skip (max retry exceeded after query due to race conditions)
            if resend_request.max_try_count and event.publish_try_count >= resend_request.max_try_count:
                skipped += 1
                continue
            
            attempted += 1
            publish_success = False
            failure_reason = None
            
            try:
                # Extract data from payload
                payload = event.payload_json
                customer_id = UUID(payload.get("customer_id"))
                name = payload.get("name")
                status_val = payload.get("status")
                
                # Publish to RabbitMQ
                publish_success = publisher.publish_event(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    customer_id=customer_id,
                    name=name,
                    status=status_val,
                    created_at=event.created_at
                )
                
                if publish_success:
                    # Update event record - successfully published
                    event.publish_status = 'published'
                    event.published_at = datetime.utcnow()
                    event.publish_try_count += 1
                    event.publish_last_tried_at = datetime.utcnow()
                    event.publish_failure_reason = None
                    succeeded += 1
                else:
                    failure_reason = "RabbitMQ publish returned False"
                    
            except Exception as publish_error:
                failure_reason = f"{type(publish_error).__name__}: {str(publish_error)}"
            
            # If publishing failed, update record
            if not publish_success:
                event.publish_try_count += 1
                event.publish_last_tried_at = datetime.utcnow()
                event.publish_failure_reason = failure_reason
                
                # Mark as permanently failed if exceeded max retries (10)
                if event.publish_try_count >= 10:
                    event.publish_status = 'failed'
                
                failed += 1
                
                # Add to failed events list
                from services.customer_service.schemas import EventResendFailedEvent
                failed_events_list.append(
                    EventResendFailedEvent(
                        event_id=event.event_id,
                        event_type=event.event_type,
                        try_count=event.publish_try_count,
                        failure_reason=failure_reason
                    )
                )
        
        # Commit all updates
        db.commit()
        
        # Build response
        from services.customer_service.schemas import EventResendResponseData, EventResendSummary
        response_data = EventResendResponseData(
            summary=EventResendSummary(
                total_pending=total_pending,
                attempted=attempted,
                succeeded=succeeded,
                failed=failed,
                skipped=skipped
            ),
            failed_events=failed_events_list
        )
        
        return success_response(response_data.model_dump(), status.HTTP_200_OK)
        
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to resend events: {str(e)}"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp
        )


@router.get("/events/health", response_model=EventHealthStandardResponse, status_code=status.HTTP_200_OK)
def get_events_health(request: Request, db: Session = Depends(get_db)):
    """
    Get health status of event publishing system.
    
    Returns:
    - **pending_count**: Number of events waiting to be published
    - **oldest_pending_age_seconds**: Age in seconds of the oldest pending event
    - **failed_count**: Number of permanently failed events (exceeded max retries)
    """
    try:
        from services.customer_service.models import CustomerEvent
        from sqlalchemy import func
        
        # Count pending events
        pending_count = db.query(CustomerEvent).filter(
            CustomerEvent.publish_status == 'pending'
        ).count()
        
        # Find oldest pending event
        oldest_pending = db.query(func.min(CustomerEvent.created_at)).filter(
            CustomerEvent.publish_status == 'pending'
        ).scalar()
        
        # Calculate age in seconds
        oldest_pending_age_seconds = None
        if oldest_pending:
            age_delta = datetime.utcnow() - oldest_pending
            oldest_pending_age_seconds = round(age_delta.total_seconds(), 2)
        
        # Count failed events
        failed_count = db.query(CustomerEvent).filter(
            CustomerEvent.publish_status == 'failed'
        ).count()
        
        # Build response
        from services.customer_service.schemas import EventHealthResponseData
        response_data = EventHealthResponseData(
            pending_count=pending_count,
            oldest_pending_age_seconds=oldest_pending_age_seconds,
            failed_count=failed_count
        )
        
        return success_response(response_data.model_dump(), status.HTTP_200_OK)
        
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to get events health: {str(e)}"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp
        )

@router.post("/events/confirm-delivery", response_model=EventConfirmDeliveryStandardResponse, status_code=status.HTTP_200_OK)
def confirm_event_delivery(confirmation: EventConfirmDeliveryRequest, request: Request, db: Session = Depends(get_db)):
    """
    Consumer confirms successful receipt and processing of an event.
    
    - **event_id**: UUID of the event that was processed
    - **status**: Processing status ('received', 'processed', or 'failed')
    - **received_at**: Timestamp when consumer received the message
    - **failure_reason**: Optional - reason if processing failed
    
    Returns: Success confirmation
    """
    try:
        from services.customer_service.models import CustomerEvent, ConsumerEventReceipt
        
        # Find the event
        event = db.query(CustomerEvent).filter(CustomerEvent.event_id == confirmation.event_id).first()
        
        if not event:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Event {confirmation.event_id} not found"
            )
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=error_resp
            )
        
        # Check for duplicate delivery confirmation (idempotency)
        existing_receipt = db.query(ConsumerEventReceipt).filter(
            ConsumerEventReceipt.event_id == confirmation.event_id
        ).first()
        
        if existing_receipt:
            # Already processed - return success (idempotent)
            return success_response({}, status.HTTP_200_OK)
        
        # Create consumer receipt record
        receipt = ConsumerEventReceipt(
            consumer_id=None,  # Will be populated when authentication is added
            event_id=confirmation.event_id,
            customer_id=event.customer_id,
            event_type=event.event_type,
            received_at=confirmation.received_at,
            processing_status=confirmation.status,
            processing_failure_reason=confirmation.failure_reason
        )
        db.add(receipt)
        
        # Update event delivery status
        if confirmation.status in ['received', 'processed']:
            event.deliver_status = 'delivered'
            event.delivered_at = datetime.utcnow()
            event.deliver_failure_reason = None
        else:  # status == 'failed'
            event.deliver_status = 'failed'
            event.deliver_failure_reason = confirmation.failure_reason
        
        db.commit()
        
        return success_response({}, status.HTTP_200_OK)
        
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to confirm delivery: {str(e)}"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp
        )


@router.post("/events/redeliver", response_model=EventRedeliverStandardResponse, status_code=status.HTTP_200_OK)
def redeliver_pending_events(redeliver_request: EventRedeliverRequest, request: Request, db: Session = Depends(get_db)):
    """
    Redeliver events that failed delivery to consumers (admin troubleshooting).
    
    - **period_in_days**: Search for events created within this many days (1-365)
    - **max_try_count**: Optional - Skip events that exceeded this delivery retry count
    - **event_types**: Optional - Filter by specific event types
    
    Returns: Summary of redelivery operation with failed event details
    """
    try:
        from datetime import timedelta
        from services.customer_service.models import CustomerEvent
        from sqlalchemy import and_
        
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=redeliver_request.period_in_days)
        
        # Build query filters - events that were published but not delivered
        filters = [
            CustomerEvent.created_at > cutoff_date,
            CustomerEvent.publish_status == 'published',  # Successfully published
            CustomerEvent.deliver_status == 'pending'     # But not delivered
        ]
        
        if redeliver_request.max_try_count is not None:
            filters.append(CustomerEvent.deliver_try_count < redeliver_request.max_try_count)
        
        if redeliver_request.event_types:
            filters.append(CustomerEvent.event_type.in_(redeliver_request.event_types))
        
        # Query pending delivery events, ordered by created_at ASC for ordering guarantee
        pending_events = db.query(CustomerEvent).filter(and_(*filters)).order_by(CustomerEvent.created_at.asc()).all()
        
        # Initialize counters
        total_pending = len(pending_events)
        attempted = 0
        succeeded = 0
        failed = 0
        skipped = 0
        failed_events_list = []
        
        # Get publisher
        publisher = get_event_publisher()
        
        if not publisher:
            # If RabbitMQ is completely unavailable, return early
            from services.customer_service.schemas import EventRedeliverResponseData, EventRedeliverSummary
            response_data = EventRedeliverResponseData(
                summary=EventRedeliverSummary(
                    total_pending=total_pending,
                    attempted=0,
                    succeeded=0,
                    failed=0,
                    skipped=total_pending
                ),
                failed_events=[]
            )
            return success_response(response_data.model_dump(), status.HTTP_200_OK)
        
        # Attempt to republish each event
        for event in pending_events:
            # Check if should skip
            if redeliver_request.max_try_count and event.deliver_try_count >= redeliver_request.max_try_count:
                skipped += 1
                continue
            
            attempted += 1
            publish_success = False
            failure_reason = None
            
            try:
                # Extract data from payload
                payload = event.payload_json
                customer_id = UUID(payload.get("customer_id"))
                name = payload.get("name")
                status_val = payload.get("status")
                
                # Republish to RabbitMQ
                publish_success = publisher.publish_event(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    customer_id=customer_id,
                    name=name,
                    status=status_val,
                    created_at=event.created_at
                )
                
                if publish_success:
                    # Update delivery attempt tracking
                    event.deliver_try_count += 1
                    event.deliver_last_tried_at = datetime.utcnow()
                    event.deliver_failure_reason = None
                    succeeded += 1
                else:
                    failure_reason = "RabbitMQ publish returned False"
                    
            except Exception as publish_error:
                failure_reason = f"{type(publish_error).__name__}: {str(publish_error)}"
            
            # If republishing failed, update record
            if not publish_success:
                event.deliver_try_count += 1
                event.deliver_last_tried_at = datetime.utcnow()
                event.deliver_failure_reason = failure_reason
                
                # Mark as permanently failed if exceeded max retries (10)
                if event.deliver_try_count >= 10:
                    event.deliver_status = 'failed'
                
                failed += 1
                
                # Add to failed events list
                from services.customer_service.schemas import EventRedeliverFailedEvent
                failed_events_list.append(
                    EventRedeliverFailedEvent(
                        event_id=event.event_id,
                        event_type=event.event_type,
                        deliver_try_count=event.deliver_try_count,
                        deliver_failure_reason=failure_reason
                    )
                )
        
        # Commit all updates
        db.commit()
        
        # Build response
        from services.customer_service.schemas import EventRedeliverResponseData, EventRedeliverSummary
        response_data = EventRedeliverResponseData(
            summary=EventRedeliverSummary(
                total_pending=total_pending,
                attempted=attempted,
                succeeded=succeeded,
                failed=failed,
                skipped=skipped
            ),
            failed_events=failed_events_list
        )
        
        return success_response(response_data.model_dump(), status.HTTP_200_OK)
        
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to redeliver events: {str(e)}"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp
        )


# ==========================================
# Consumer Management Endpoints
# ==========================================

@router.post("/consumer/data", response_model=ConsumerCreateStandardResponse, status_code=status.HTTP_201_CREATED)
def create_consumer_endpoint(consumer: ConsumerCreate, request: Request, db: Session = Depends(get_db)):
    """
    Create new consumer with auto-generated API key.
    Returns consumer_id and plaintext API key (only shown once).
    """
    try:
        from services.customer_service.schemas import ConsumerCreateResponseData
        
        db_consumer, plaintext_key = crud.create_consumer(
            db=db,
            name=consumer.name,
            description=consumer.description
        )
        
        response_data = ConsumerCreateResponseData(
            consumer_id=db_consumer.consumer_id,
            api_key=plaintext_key
        )
        
        return success_response(response_data.model_dump(), status.HTTP_201_CREATED)
        
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to create consumer: {str(e)}"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp
        )


@router.post("/consumer/me/api-key/rotate", response_model=ConsumerRotateKeyStandardResponse, status_code=status.HTTP_200_OK)
def rotate_consumer_key(request: Request, db: Session = Depends(get_db), consumer = Depends(verify_api_key)):
    """
    Rotate API key for authenticated consumer.
    Deactivates old key and generates new one.
    """
    try:
        from services.customer_service.schemas import ConsumerRotateKeyResponseData
        
        plaintext_key = crud.rotate_api_key(db, consumer.consumer_id)
        
        if not plaintext_key:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                "Consumer not found or inactive"
            )
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=error_resp
            )
        
        response_data = ConsumerRotateKeyResponseData(api_key=plaintext_key)
        return success_response(response_data.model_dump(), status.HTTP_200_OK)
        
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to rotate API key: {str(e)}"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp
        )


@router.get("/consumer/me", response_model=ConsumerGetStandardResponse, status_code=status.HTTP_200_OK)
def get_consumer_me(request: Request, db: Session = Depends(get_db), consumer = Depends(verify_api_key)):
    """
    Get authenticated consumer's data.
    Consumer extracted from X-API-Key header.
    """
    try:
        from services.customer_service.schemas import ConsumerGetResponseData
        
        response_data = ConsumerGetResponseData(
            consumer_id=consumer.consumer_id,
            name=consumer.name,
            description=consumer.description,
            status=consumer.status,
            created_at=consumer.created_at,
            updated_at=consumer.updated_at
        )
        
        return success_response(response_data.model_dump(), status.HTTP_200_OK)
        
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to retrieve consumer data: {str(e)}"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp
        )


@router.get("/consumer/me/api-key", response_model=ConsumerKeyStatusStandardResponse, status_code=status.HTTP_200_OK)
def get_consumer_key_status(request: Request, db: Session = Depends(get_db), consumer = Depends(verify_api_key)):
    """
    Get authenticated consumer's API key metadata.
    Does not return key value, only status/timestamps.
    """
    try:
        from services.customer_service.schemas import ConsumerKeyStatusResponseData
        
        api_key_record = crud.get_api_key_status(db, consumer.consumer_id)
        
        if not api_key_record:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                "No active API key found"
            )
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=error_resp
            )
        
        response_data = ConsumerKeyStatusResponseData(
            status=api_key_record.status,
            created_at=api_key_record.created_at,
            expires_at=api_key_record.expires_at,
            last_used_at=api_key_record.last_used_at,
            updated_at=api_key_record.updated_at
        )
        
        return success_response(response_data.model_dump(), status.HTTP_200_OK)
        
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to retrieve API key status: {str(e)}"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp
        )


@router.post("/consumer/me/api-key/deactivate", response_model=CustomerTagStandardResponse, status_code=status.HTTP_200_OK)
def deactivate_consumer_key(request: Request, db: Session = Depends(get_db), consumer = Depends(verify_api_key)):
    """
    Deactivate authenticated consumer's API key.
    After this call, key becomes invalid.
    """
    try:
        success = crud.deactivate_api_key(db, consumer.consumer_id)
        
        if not success:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                "No active API key found to deactivate"
            )
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=error_resp
            )
        
        return success_response({}, status.HTTP_200_OK)
        
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to deactivate API key: {str(e)}"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp
        )


@router.post("/admin/consumer/{consumer_id}/change-status", response_model=ConsumerChangeStatusStandardResponse, status_code=status.HTTP_200_OK)
def change_consumer_status_admin(
    consumer_id: UUID,
    status_change: ConsumerChangeStatusRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Admin endpoint: Change consumer status.
    TODO: Add admin authentication middleware.
    """
    try:
        updated_consumer = crud.change_consumer_status(db, consumer_id, status_change.status)
        
        if not updated_consumer:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Consumer {consumer_id} not found"
            )
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=error_resp
            )
        
        return success_response({}, status.HTTP_200_OK)
        
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to change consumer status: {str(e)}"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp
        )