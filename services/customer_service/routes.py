from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional
import uuid
import os
from datetime import datetime, timedelta
from services.customer_service.database import get_db
from services.customer_service.models import Customer, Consumer
from services.shared.utils import utcnow
from services.customer_service import metrics
from services.customer_service.metrics import (
    record_customer_operation,
    record_event_publish,
    record_rabbitmq_failure,
    MetricsTimer,
)
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
    ConsumerChangeStatusStandardResponse,
)
from services.customer_service import crud
from services.customer_service.constants import PUBLISH_ERROR_RABBITMQ_FALSE, PUBLISH_ERROR_PUBLISHER_NONE
from services.shared.response_handler import success_response, error_response
from services.shared.audit_logger import log_error_to_audit
from services.shared.event_publisher import get_event_publisher
from services.customer_service.middleware import verify_api_key, rate_limit_middleware

router = APIRouter()

# Get instance ID from environment (for load balancing verification)
INSTANCE_ID = os.getenv("INSTANCE_ID", "unknown")


def validate_customer_status_for_operation(customer: Customer, operation: str) -> Optional[dict]:
    """
    Validate customer status allows the requested operation.
    Returns error response dict if blocked, None if allowed.

    Args:
        customer: Customer object to validate
        operation: Operation name (for logging)

    Returns:
        Error response dict if validation fails, None if allowed
    """
    from services.customer_service.constants import CUSTOMER_STATUS_BLOCKED, CUSTOMER_STATUS_PENDING_AML

    if customer.status == CUSTOMER_STATUS_BLOCKED:
        # Vague error message for security (don't reveal customer is sanctioned)
        return error_response(status.HTTP_403_FORBIDDEN, "Customer access restricted. Contact administrator.")

    if customer.status == CUSTOMER_STATUS_PENDING_AML:
        # Customer still being verified
        return error_response(status.HTTP_409_CONFLICT, "Customer verification in progress. Please try again later.")

    return None  # Validation passed


@router.post("/customer/data", response_model=CustomerCreateStandardResponse, status_code=status.HTTP_201_CREATED)
def create_customer(
    customer: CustomerCreate,
    request: Request,
    db: Session = Depends(get_db),
    consumer=Depends(verify_api_key),
    _=Depends(rate_limit_middleware),
):
    """
    Create a new customer.

    - **name**: Customer name (required)

    Returns: Standardized response with customer_id, status, created_at

    Requires: X-API-Key header with valid consumer API key
    """
    print(f"[{INSTANCE_ID}] Processing POST /customer/data - consumer: {consumer.name}")
    print(f"[DEBUG] Authenticated consumer: id={consumer.consumer_id}, name={consumer.name}")
    try:
        db_customer = crud.create_customer(db, customer, consumer.consumer_id)

        # Create event entry first with 'pending' status (outbox pattern)
        event = crud.create_customer_event(
            db=db,
            customer_id=db_customer.customer_id,
            event_type="customer_creation",
            source_service="POST: /customer/data",
            payload={
                "customer_id": str(db_customer.customer_id),
                "name": db_customer.name,
                "status": db_customer.status,
            },
            metadata={"created_at": db_customer.created_at.isoformat()},
            publish_status="pending",  # Default to pending
            published_at=None,
            publish_try_count=1,
            publish_last_tried_at=utcnow(),
            publish_failure_reason=None,
            consumer_id=consumer.consumer_id,  # Track which consumer created this event
        )

        # Now try to publish to RabbitMQ
        publish_success = False
        try:
            print(
                f"Attempting to publish event {event.event_id}: "
                f"customer.creation for customer {db_customer.customer_id}"
            )
            publisher = get_event_publisher()
            if publisher:
                with MetricsTimer(
                    metrics.event_publish_duration_seconds, event_type="customer_creation", consumer=consumer.name
                ):
                    publish_success = publisher.publish_event(
                        event_id=event.event_id,  # Use the event_id from DB
                        event_type="customer_creation",
                        customer_id=db_customer.customer_id,
                        name=db_customer.name,
                        status=db_customer.status,
                        created_at=event.created_at,
                        consumer_name=consumer.name,
                        consumer_id=consumer.consumer_id,  # Pass consumer_id for AML service
                    )

                if publish_success:
                    # Update event record - successfully published
                    event.publish_status = "published"
                    event.published_at = utcnow()
                    event.publish_failure_reason = None
                    # Track initial delivery attempt
                    event.deliver_try_count = 1
                    event.deliver_last_tried_at = utcnow()
                    db.commit()
                    print("RabbitMQ publish successful, event marked as published")
                else:
                    # Update failure reason
                    event.publish_failure_reason = PUBLISH_ERROR_RABBITMQ_FALSE
                    db.commit()
                    print(f"RabbitMQ publish failed: {event.publish_failure_reason}")
            else:
                # Update failure reason
                event.publish_failure_reason = PUBLISH_ERROR_PUBLISHER_NONE
                db.commit()
                print("Publisher is None - RabbitMQ connection failed")

        except Exception as mq_error:
            # Update failure reason
            event.publish_failure_reason = f"{type(mq_error).__name__}: {str(mq_error)}"
            db.commit()
            print(f"RabbitMQ publish exception (non-blocking): {event.publish_failure_reason}")
            import traceback

            traceback.print_exc()

        response_data = CustomerCreateResponse(
            customer_id=db_customer.customer_id, status=db_customer.status, created_at=db_customer.created_at
        )
        return success_response(response_data.model_dump(), status.HTTP_201_CREATED)
    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to create customer: {str(e)}")

        # Log error to audit
        log_error_to_audit(
            db=db,
            request=request,
            entity="customer",
            entity_id=str(uuid.uuid4()),  # No customer_id available yet
            action="create_customer",
            error_response=error_resp,
        )

        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.get("/customer/data", response_model=CustomerGetStandardResponse)
def get_customer(
    customer_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    consumer=Depends(verify_api_key),
    _=Depends(rate_limit_middleware),
):
    """
    Retrieve customer information by ID.

    - **customer_id**: UUID of the customer (query parameter)

    Returns: Standardized response with customer_id, name, status, created_at, updated_at, tags

    Requires: X-API-Key header with valid consumer API key
    """
    print(f"[{INSTANCE_ID}] Processing GET /customer/data - customer_id: {customer_id}")
    print(f"[DEBUG] GET authenticated consumer: id={consumer.consumer_id}, name={consumer.name}")
    try:
        # SECURITY: Filter by consumer_id to prevent cross-consumer data access
        db_customer = crud.get_customer(db, customer_id, consumer.consumer_id)
        if db_customer is None:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Customer with id {customer_id} not found",  # Don't reveal if customer exists for other consumer
            )

            # Log error to audit
            log_error_to_audit(
                db=db,
                request=request,
                entity="customer",
                entity_id=customer_id,
                action="get_customer",
                error_response=error_resp,
            )

            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)

        # Allow retrieval of customer data even if customer is BLOCKED.
        # Keep blocking only for customers pending AML verification.
        from services.customer_service.constants import CUSTOMER_STATUS_PENDING_AML

        if db_customer.status == CUSTOMER_STATUS_PENDING_AML:
            error_resp = error_response(
                status.HTTP_409_CONFLICT, "Customer verification in progress. Please try again later."
            )
            return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=error_resp)

        # SECURITY: Get customer tags with consumer_id validation
        customer_tags = crud.get_customer_tags(db, customer_id, consumer.consumer_id)
        # Create tags dict (order doesn't matter for JSON response)
        tags_dict = {str(tag.tag_key): tag.tag_value for tag in customer_tags}

        response_data = CustomerResponse(
            customer_id=db_customer.customer_id,
            name=db_customer.name,
            status=db_customer.status,
            created_at=db_customer.created_at,
            updated_at=db_customer.updated_at,
            tags=tags_dict,
        )
        return success_response(response_data.model_dump(), status.HTTP_200_OK)
    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to retrieve customer: {str(e)}")

        # Log error to audit
        log_error_to_audit(
            db=db,
            request=request,
            entity="customer",
            entity_id=customer_id,
            action="get_customer",
            error_response=error_resp,
        )

        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.post("/customer/tag", response_model=CustomerTagStandardResponse, status_code=status.HTTP_201_CREATED)
def create_customer_tags(
    tag_data: CustomerTagCreate,
    request: Request,
    db: Session = Depends(get_db),
    consumer=Depends(verify_api_key),
    _=Depends(rate_limit_middleware),
):
    """
    Create multiple tags for a customer.

    - **customer_id**: UUID of the customer
    - **tag_keys**: List of tag keys
    - **tag_values**: List of tag values (positional correspondence with keys)

    Returns: Standardized response

    Requires: X-API-Key header with valid consumer API key
    """
    try:
        # SECURITY: Validate customer exists and belongs to this consumer
        db_customer = crud.get_customer(db, tag_data.customer_id, consumer.consumer_id)
        if not db_customer:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Customer with id {tag_data.customer_id} not found",  # Don't reveal if exists for other consumer
            )
            log_error_to_audit(db, request, "customer_tag", tag_data.customer_id, "create_tags", error_resp)
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)

        # Validate arrays have same length
        if len(tag_data.tag_keys) != len(tag_data.tag_values):
            error_resp = error_response(
                status.HTTP_400_BAD_REQUEST, "tag_keys and tag_values arrays must have the same length"
            )
            log_error_to_audit(db, request, "customer_tag", tag_data.customer_id, "create_tags", error_resp)
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_resp)

        # Create tags (consumer_id from authenticated consumer)
        for key, value in zip(tag_data.tag_keys, tag_data.tag_values):
            crud.create_customer_tag(db, tag_data.customer_id, key, value, consumer.consumer_id)

        return success_response({}, status.HTTP_201_CREATED)
    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to create tags: {str(e)}")
        log_error_to_audit(db, request, "customer_tag", tag_data.customer_id, "create_tags", error_resp)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.get("/customer/tag-value", response_model=CustomerTagGetStandardResponse)
def get_customer_tag_value(
    customer_id: UUID,
    tag_key: str,
    request: Request,
    db: Session = Depends(get_db),
    consumer=Depends(verify_api_key),
    _=Depends(rate_limit_middleware),
):
    """
    Retrieve tag value for a customer by tag key.

    - **customer_id**: UUID of the customer (query parameter)
    - **tag_key**: Tag key (query parameter)

    Returns: Tag value

    Requires: X-API-Key header with valid consumer API key
    """
    try:
        # SECURITY: Filter by consumer_id from authenticated API key
        db_tag = crud.get_customer_tag(db, customer_id, tag_key, consumer.consumer_id)
        if not db_tag:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Tag '{tag_key}' not found for customer {customer_id}",  # Don't reveal if exists for other consumer
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
def delete_customer_tag(
    tag_delete: CustomerTagDelete,
    request: Request,
    db: Session = Depends(get_db),
    consumer=Depends(verify_api_key),
    _=Depends(rate_limit_middleware),
):
    """
    Delete a tag for a customer.

    - **customer_id**: UUID of the customer
    - **tag_key**: Tag key to delete

    Returns: Standardized response

    Requires: X-API-Key header with valid consumer API key
    """
    try:
        # SECURITY: Filter by consumer_id from authenticated API key
        deleted = crud.delete_customer_tag(db, tag_delete.customer_id, tag_delete.tag_key, consumer.consumer_id)
        if not deleted:
            # Don't reveal if tag exists for other consumer
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Tag '{tag_delete.tag_key}' not found for customer {tag_delete.customer_id}",
            )
            log_error_to_audit(db, request, "customer_tag", tag_delete.customer_id, "delete_tag", error_resp)
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)

        return success_response({}, status.HTTP_200_OK)
    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to delete tag: {str(e)}")
        log_error_to_audit(db, request, "customer_tag", tag_delete.customer_id, "delete_tag", error_resp)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.patch("/customer/tag-key", response_model=CustomerTagStandardResponse, status_code=status.HTTP_200_OK)
def update_customer_tag_key(
    tag_update: CustomerTagKeyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    consumer=Depends(verify_api_key),
    _=Depends(rate_limit_middleware),
):
    """
    Update tag key for a customer.

    - **customer_id**: UUID of the customer
    - **tag_key**: Current tag key
    - **new_tag_key**: New tag key

    Returns: Standardized response

    Requires: X-API-Key header with valid consumer API key
    """
    try:
        # SECURITY: Filter by consumer_id from authenticated API key
        updated_tag = crud.update_customer_tag_key(
            db, tag_update.customer_id, tag_update.tag_key, tag_update.new_tag_key, consumer.consumer_id
        )
        if not updated_tag:
            # Don't reveal if tag exists for other consumer
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Tag '{tag_update.tag_key}' not found for customer {tag_update.customer_id}",
            )
            log_error_to_audit(db, request, "customer_tag", tag_update.customer_id, "update_tag_key", error_resp)
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)

        return success_response({}, status.HTTP_200_OK)
    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to update tag key: {str(e)}")
        log_error_to_audit(db, request, "customer_tag", tag_update.customer_id, "update_tag_key", error_resp)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.patch("/customer/tag-value", response_model=CustomerTagStandardResponse, status_code=status.HTTP_200_OK)
def update_customer_tag_value(
    tag_update: CustomerTagValueUpdate,
    request: Request,
    db: Session = Depends(get_db),
    consumer=Depends(verify_api_key),
    _=Depends(rate_limit_middleware),
):
    """
    Update tag value for a customer.

    - **customer_id**: UUID of the customer
    - **tag_key**: Tag key
    - **new_tag_value**: New tag value

    Returns: Standardized response

    Requires: X-API-Key header with valid consumer API key
    """
    try:
        # SECURITY: Filter by consumer_id from authenticated API key
        updated_tag = crud.update_customer_tag_value(
            db, tag_update.customer_id, tag_update.tag_key, tag_update.new_tag_value, consumer.consumer_id
        )
        if not updated_tag:
            # Don't reveal if tag exists for other consumer
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Tag '{tag_update.tag_key}' not found for customer {tag_update.customer_id}",
            )
            log_error_to_audit(db, request, "customer_tag", tag_update.customer_id, "update_tag_value", error_resp)
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)

        return success_response({}, status.HTTP_200_OK)
    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to update tag value: {str(e)}")
        log_error_to_audit(db, request, "customer_tag", tag_update.customer_id, "update_tag_value", error_resp)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


# Deprecated: POST /customer/analytics removed (replaced by Airflow ETL job for consumer-level aggregates)
# Per-customer analytics snapshots no longer supported - use consumer_analytics table via scheduled ETL


@router.delete("/customer/data", response_model=CustomerDeleteStandardResponse, status_code=status.HTTP_200_OK)
def delete_customer(
    customer_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    consumer=Depends(verify_api_key),
    _=Depends(rate_limit_middleware),
):
    """
    Delete customer by ID (archive + physical deletion).

    Process:
    1. Archive customer data and tags to customer_archive
    2. Log deletion event in customer_events
    3. Delete all tags from customer_tags
    4. Physically delete customer from customers table

    - **customer_id**: UUID of the customer (query parameter)

    Returns: Standardized response with 200 OK if successful, 404 if not found

    Requires: X-API-Key header with valid consumer API key
    """
    try:
        # Step 1: SECURITY - Validate customer exists and belongs to this consumer
        db_customer = crud.get_customer(db, customer_id, consumer.consumer_id)
        if not db_customer:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Customer with id {customer_id} not found",  # Don't reveal if exists for other consumer
            )

            # Log error to audit
            log_error_to_audit(
                db=db,
                request=request,
                entity="customer",
                entity_id=customer_id,
                action="delete_customer",
                error_response=error_resp,
            )

            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)

        # Validate customer status allows deletion (block PENDING_AML, allow INACTIVE and BLOCKED)
        from services.customer_service.constants import CUSTOMER_STATUS_PENDING_AML

        if db_customer.status == CUSTOMER_STATUS_PENDING_AML:
            error_resp = error_response(
                status.HTTP_409_CONFLICT, "Cannot delete customer while verification is in progress."
            )
            return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=error_resp)

        # Step 2: SECURITY - Capture snapshot with consumer_id validation
        customer_tags = crud.get_customer_tags(db, customer_id, consumer.consumer_id)

        snapshot = {
            "customer": {
                "customer_id": str(db_customer.customer_id),
                "name": db_customer.name,
                "status": db_customer.status,
                "created_at": db_customer.created_at.isoformat(),
                "updated_at": db_customer.updated_at.isoformat(),
            },
            "tags": [
                {
                    "tag_id": str(tag.tag_id),
                    "tag_key": tag.tag_key,
                    "tag_value": tag.tag_value,
                    "created_at": tag.created_at.isoformat(),
                }
                for tag in customer_tags
            ],
        }

        # Step 3: Archive customer
        crud.create_customer_archive(
            db=db, customer_id=customer_id, snapshot=snapshot, trigger_event="customer_deletion"
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
                "tags_count": len(customer_tags),
            },
            metadata={"deleted_at": db_customer.updated_at.isoformat(), "archived": True},
            publish_status="pending",
            published_at=None,
            publish_try_count=1,
            publish_last_tried_at=utcnow(),
            publish_failure_reason=None,
            consumer_id=consumer.consumer_id,
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
                    created_at=event.created_at,
                    consumer_name=consumer.name,
                )

                if publish_success:
                    event.publish_status = "published"
                    event.published_at = utcnow()
                    event.publish_failure_reason = None
                    # Track initial delivery attempt
                    event.deliver_try_count = 1
                    event.deliver_last_tried_at = utcnow()
                    db.commit()
                    print("RabbitMQ publish successful, event marked as published")
                else:
                    event.publish_failure_reason = PUBLISH_ERROR_RABBITMQ_FALSE
                    db.commit()
                    print(f"RabbitMQ publish failed: {event.publish_failure_reason}")
            else:
                event.publish_failure_reason = PUBLISH_ERROR_PUBLISHER_NONE
                db.commit()
                print("Publisher is None - RabbitMQ connection failed")
        except Exception as mq_error:
            event.publish_failure_reason = f"{type(mq_error).__name__}: {str(mq_error)}"
            db.commit()
            print(f"RabbitMQ publish exception (non-blocking): {event.publish_failure_reason}")
            import traceback

            traceback.print_exc()

        # Step 6: SECURITY - Delete tags with consumer_id validation
        tags_deleted = crud.delete_customer_tags(db, customer_id, consumer.consumer_id)

        # Step 7: SECURITY - Delete customer with consumer_id validation
        crud.delete_customer(db, customer_id, consumer.consumer_id)

        return success_response(
            {"message": "Customer deleted successfully", "archived": True, "tags_deleted": tags_deleted},
            status.HTTP_200_OK,
        )
    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to delete customer: {str(e)}")

        # Log error to audit
        log_error_to_audit(
            db=db,
            request=request,
            entity="customer",
            entity_id=customer_id,
            action="delete_customer",
            error_response=error_resp,
        )

        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.patch(
    "/customer/change-status", response_model=CustomerStatusChangeStandardResponse, status_code=status.HTTP_200_OK
)
def change_customer_status(
    status_change: CustomerStatusChange,
    request: Request,
    db: Session = Depends(get_db),
    consumer=Depends(verify_api_key),
    _=Depends(rate_limit_middleware),
):
    """
    Change customer status (ACTIVE/INACTIVE).

    - **customer_id**: UUID of the customer
    - **status**: New status (ACTIVE or INACTIVE)

    Returns: Standardized response with detail only

    Requires: X-API-Key header with valid consumer API key
    """
    try:
        # SECURITY: Validate customer exists and belongs to this consumer
        db_customer = crud.get_customer(db, status_change.customer_id, consumer.consumer_id)

        if db_customer is None:
            error_resp = error_response(
                status.HTTP_404_NOT_FOUND,
                f"Customer with id {status_change.customer_id} not found",  # Don't reveal if exists for other consumer
            )

            # Log error to audit
            log_error_to_audit(
                db=db,
                request=request,
                entity="customer",
                entity_id=status_change.customer_id,
                action="change_customer_status",
                error_response=error_resp,
            )

            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)

        # Validate customer status allows this operation (consumers cannot change BLOCKED or PENDING_AML)
        from services.customer_service.constants import CUSTOMER_STATUS_BLOCKED, CUSTOMER_STATUS_PENDING_AML

        if db_customer.status in [CUSTOMER_STATUS_BLOCKED, CUSTOMER_STATUS_PENDING_AML]:
            error_resp = error_response(
                status.HTTP_403_FORBIDDEN, "Customer status change restricted. Contact administrator."
            )
            return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content=error_resp)

        # Check if customer already has the requested status
        if db_customer.status == status_change.status:
            error_resp = error_response(
                status.HTTP_409_CONFLICT, f"Customer {status_change.customer_id} is already {status_change.status}"
            )

            # Log error to audit
            log_error_to_audit(
                db=db,
                request=request,
                entity="customer",
                entity_id=status_change.customer_id,
                action="change_customer_status",
                error_response=error_resp,
            )

            return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=error_resp)

        # Store old status for event
        old_status = db_customer.status

        # SECURITY: Update status with consumer_id validation
        crud.update_customer_status(db, status_change.customer_id, status_change.status, consumer.consumer_id)

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
                "new_status": status_change.status,
            },
            metadata={"changed_at": db_customer.updated_at.isoformat()},
            publish_status="pending",
            published_at=None,
            publish_try_count=1,
            publish_last_tried_at=utcnow(),
            publish_failure_reason=None,
            consumer_id=consumer.consumer_id,
        )

        # Try to publish to RabbitMQ
        try:
            print(
                f"Attempting to publish event {event.event_id}: "
                f"customer.status.change for customer {status_change.customer_id}"
            )
            publisher = get_event_publisher()
            if publisher:
                publish_success = publisher.publish_event(
                    event_id=event.event_id,
                    event_type="customer_status_change",
                    customer_id=status_change.customer_id,
                    name=db_customer.name,
                    status=status_change.status,
                    created_at=event.created_at,
                    consumer_name=consumer.name,
                )

                if publish_success:
                    event.publish_status = "published"
                    event.published_at = utcnow()
                    event.publish_failure_reason = None
                    # Track initial delivery attempt
                    event.deliver_try_count = 1
                    event.deliver_last_tried_at = utcnow()
                    db.commit()
                    print("RabbitMQ publish successful, event marked as published")
                else:
                    event.publish_failure_reason = PUBLISH_ERROR_RABBITMQ_FALSE
                    db.commit()
                    print(f"RabbitMQ publish failed: {event.publish_failure_reason}")
            else:
                event.publish_failure_reason = PUBLISH_ERROR_PUBLISHER_NONE
                db.commit()
                print("Publisher is None - RabbitMQ connection failed")
        except Exception as mq_error:
            event.publish_failure_reason = f"{type(mq_error).__name__}: {str(mq_error)}"
            db.commit()
            print(f"RabbitMQ publish exception (non-blocking): {event.publish_failure_reason}")
            import traceback

            traceback.print_exc()

        return success_response({}, status.HTTP_200_OK)
    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to change customer status: {str(e)}"
        )

        # Log error to audit
        log_error_to_audit(
            db=db,
            request=request,
            entity="customer",
            entity_id=status_change.customer_id,
            action="change_customer_status",
            error_response=error_resp,
        )

        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


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
        cutoff_date = utcnow() - timedelta(days=resend_request.period_in_days)

        # Build query filters
        filters = [CustomerEvent.created_at > cutoff_date, CustomerEvent.publish_status == "pending"]

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
                    total_pending=total_pending, attempted=0, succeeded=0, failed=0, skipped=total_pending
                ),
                failed_events=[],
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

                # Lookup consumer name for queue routing
                consumer_name = "system_default"  # Default fallback
                if event.consumer_id:
                    consumer = crud.get_consumer_by_id(db, event.consumer_id)
                    consumer_name = consumer.name if consumer else "system_default"

                # Publish to RabbitMQ with consumer-specific queue
                publish_success = publisher.publish_event(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    customer_id=customer_id,
                    name=name,
                    status=status_val,
                    created_at=event.created_at,
                    consumer_name=consumer_name,
                )

                if publish_success:
                    # Update event record - successfully published
                    event.publish_status = "published"
                    event.published_at = utcnow()
                    event.publish_try_count += 1
                    event.publish_last_tried_at = utcnow()
                    event.publish_failure_reason = None
                    succeeded += 1
                else:
                    failure_reason = PUBLISH_ERROR_RABBITMQ_FALSE

            except Exception as publish_error:
                failure_reason = f"{type(publish_error).__name__}: {str(publish_error)}"

            # If publishing failed, update record
            if not publish_success:
                event.publish_try_count += 1
                event.publish_last_tried_at = utcnow()
                event.publish_failure_reason = failure_reason

                # Mark as permanently failed if exceeded max retries (10)
                if event.publish_try_count >= 10:
                    event.publish_status = "failed"

                failed += 1

                # Add to failed events list
                from services.customer_service.schemas import EventResendFailedEvent

                failed_events_list.append(
                    EventResendFailedEvent(
                        event_id=event.event_id,
                        event_type=event.event_type,
                        try_count=event.publish_try_count,
                        failure_reason=failure_reason,
                    )
                )

        # Commit all updates
        db.commit()

        # Build response
        from services.customer_service.schemas import EventResendResponseData, EventResendSummary

        response_data = EventResendResponseData(
            summary=EventResendSummary(
                total_pending=total_pending, attempted=attempted, succeeded=succeeded, failed=failed, skipped=skipped
            ),
            failed_events=failed_events_list,
        )

        return success_response(response_data.model_dump(), status.HTTP_200_OK)

    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to resend events: {str(e)}")

        # Log error to audit
        log_error_to_audit(
            db=db,
            request=request,
            entity="event",
            entity_id=None,
            action="resend_pending_events",
            error_response=error_resp,
        )

        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


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
        pending_count = db.query(CustomerEvent).filter(CustomerEvent.publish_status == "pending").count()

        # Find oldest pending event
        oldest_pending = (
            db.query(func.min(CustomerEvent.created_at)).filter(CustomerEvent.publish_status == "pending").scalar()
        )

        # Calculate age in seconds
        oldest_pending_age_seconds = None
        if oldest_pending:
            age_delta = utcnow() - oldest_pending
            oldest_pending_age_seconds = round(age_delta.total_seconds(), 2)

        # Count failed events
        failed_count = db.query(CustomerEvent).filter(CustomerEvent.publish_status == "failed").count()

        # Build response
        from services.customer_service.schemas import EventHealthResponseData

        response_data = EventHealthResponseData(
            pending_count=pending_count,
            oldest_pending_age_seconds=oldest_pending_age_seconds,
            failed_count=failed_count,
        )

        return success_response(response_data.model_dump(), status.HTTP_200_OK)

    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to get events health: {str(e)}")

        # Log error to audit
        log_error_to_audit(
            db=db,
            request=request,
            entity="event",
            entity_id=None,
            action="get_events_health",
            error_response=error_resp,
        )

        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.post(
    "/events/confirm-delivery", response_model=EventConfirmDeliveryStandardResponse, status_code=status.HTTP_200_OK
)
def confirm_event_delivery(confirmation: EventConfirmDeliveryRequest, request: Request, db: Session = Depends(get_db)):
    """
    Consumer confirms successful receipt and processing of an event.

    - **event_id**: UUID of the event that was processed
    - **status**: Processing status ('received', 'processed', or 'failed')
    - **received_at**: Timestamp when consumer received the message
    - **failure_reason**: Optional - reason if processing failed
    - **consumer_name**: Name of the consumer processing this event

    Returns: Success confirmation
    """
    try:
        from services.customer_service.models import CustomerEvent, ConsumerEventReceipt

        # Find the event
        event = db.query(CustomerEvent).filter(CustomerEvent.event_id == confirmation.event_id).first()

        if not event:
            error_resp = error_response(status.HTTP_404_NOT_FOUND, f"Event {confirmation.event_id} not found")

            # Log error to audit
            log_error_to_audit(
                db=db,
                request=request,
                entity="event",
                entity_id=confirmation.event_id,
                action="confirm_event_delivery",
                error_response=error_resp,
            )

            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)

        # Check for duplicate delivery confirmation (idempotency)
        existing_receipt = (
            db.query(ConsumerEventReceipt).filter(ConsumerEventReceipt.event_id == confirmation.event_id).first()
        )

        if existing_receipt:
            # Already processed - return success (idempotent)
            return success_response({}, status.HTTP_200_OK)

        # Look up consumer by name
        consumer = crud.get_consumer_by_name(db, confirmation.consumer_name)
        consumer_id = consumer.consumer_id if consumer else None

        # Create consumer receipt record
        receipt = ConsumerEventReceipt(
            consumer_id=consumer_id,
            event_id=confirmation.event_id,
            customer_id=event.customer_id,
            event_type=event.event_type,
            received_at=confirmation.received_at,
            processing_status=confirmation.status,
            processing_failure_reason=confirmation.failure_reason,
        )
        db.add(receipt)

        # Update event delivery status
        if confirmation.status in ["received", "processed"]:
            event.deliver_status = "delivered"
            event.delivered_at = utcnow()
            event.deliver_failure_reason = None
        else:  # status == 'failed'
            event.deliver_status = "failed"
            event.deliver_failure_reason = confirmation.failure_reason

        db.commit()

        return success_response({}, status.HTTP_200_OK)

    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to confirm delivery: {str(e)}")

        # Log error to audit
        log_error_to_audit(
            db=db,
            request=request,
            entity="event",
            entity_id=None,
            action="confirm_event_delivery",
            error_response=error_resp,
        )

        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


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
        cutoff_date = utcnow() - timedelta(days=redeliver_request.period_in_days)

        # Build query filters - events that were published but not delivered
        filters = [
            CustomerEvent.created_at > cutoff_date,
            CustomerEvent.publish_status == "published",  # Successfully published
            CustomerEvent.deliver_status == "pending",  # But not delivered
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
                    total_pending=total_pending, attempted=0, succeeded=0, failed=0, skipped=total_pending
                ),
                failed_events=[],
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

                # Lookup consumer name for queue routing
                consumer_name = "system_default"  # Default fallback
                if event.consumer_id:
                    consumer = crud.get_consumer_by_id(db, event.consumer_id)
                    consumer_name = consumer.name if consumer else "system_default"

                # Republish to RabbitMQ with consumer-specific queue
                publish_success = publisher.publish_event(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    customer_id=customer_id,
                    name=name,
                    status=status_val,
                    created_at=event.created_at,
                    consumer_name=consumer_name,
                )

                if publish_success:
                    # Update delivery attempt tracking
                    event.deliver_try_count += 1
                    event.deliver_last_tried_at = utcnow()
                    event.deliver_failure_reason = None
                    succeeded += 1
                else:
                    failure_reason = PUBLISH_ERROR_RABBITMQ_FALSE

            except Exception as publish_error:
                failure_reason = f"{type(publish_error).__name__}: {str(publish_error)}"

            # If republishing failed, update record
            if not publish_success:
                event.deliver_try_count += 1
                event.deliver_last_tried_at = utcnow()
                event.deliver_failure_reason = failure_reason

                # Mark as permanently failed if exceeded max retries (10)
                if event.deliver_try_count >= 10:
                    event.deliver_status = "failed"

                failed += 1

                # Add to failed events list
                from services.customer_service.schemas import EventRedeliverFailedEvent

                failed_events_list.append(
                    EventRedeliverFailedEvent(
                        event_id=event.event_id,
                        event_type=event.event_type,
                        deliver_try_count=event.deliver_try_count,
                        deliver_failure_reason=failure_reason,
                    )
                )

        # Commit all updates
        db.commit()

        # Build response
        from services.customer_service.schemas import EventRedeliverResponseData, EventRedeliverSummary

        response_data = EventRedeliverResponseData(
            summary=EventRedeliverSummary(
                total_pending=total_pending, attempted=attempted, succeeded=succeeded, failed=failed, skipped=skipped
            ),
            failed_events=failed_events_list,
        )

        return success_response(response_data.model_dump(), status.HTTP_200_OK)

    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to redeliver events: {str(e)}")

        # Log error to audit
        log_error_to_audit(
            db=db,
            request=request,
            entity="event",
            entity_id=None,
            action="redeliver_pending_events",
            error_response=error_resp,
        )

        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


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
        from services.shared.event_publisher import get_event_publisher

        db_consumer, plaintext_key, event = crud.create_consumer(
            db=db, name=consumer.name, description=consumer.description
        )

        # Try to publish consumer_created event to RabbitMQ
        try:
            publisher = get_event_publisher()
            if publisher:
                publish_success = publisher.publish_event(
                    event_id=event.event_id,
                    event_type="consumer_created",
                    customer_id=db_consumer.consumer_id,  # Using consumer_id as customer_id
                    name=db_consumer.name,
                    status=db_consumer.status,
                    created_at=event.created_at,
                    consumer_name=db_consumer.name,  # Consumer's name
                )

                if publish_success:
                    event.publish_status = "published"
                    event.published_at = utcnow()
                    event.deliver_try_count = 1
                    event.deliver_last_tried_at = utcnow()
                else:
                    event.publish_failure_reason = PUBLISH_ERROR_RABBITMQ_FALSE
                db.commit()
            else:
                event.publish_failure_reason = PUBLISH_ERROR_PUBLISHER_NONE
                db.commit()
        except Exception as mq_error:
            event.publish_failure_reason = f"{type(mq_error).__name__}: {str(mq_error)}"
            db.commit()

        response_data = ConsumerCreateResponseData(consumer_id=db_consumer.consumer_id, api_key=plaintext_key)

        return success_response(response_data.model_dump(), status.HTTP_201_CREATED)

    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to create consumer: {str(e)}")
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.post(
    "/consumer/me/api-key/rotate", response_model=ConsumerRotateKeyStandardResponse, status_code=status.HTTP_200_OK
)
def rotate_consumer_key(
    request: Request, db: Session = Depends(get_db), consumer=Depends(verify_api_key), _=Depends(rate_limit_middleware)
):
    """
    Rotate API key for authenticated consumer.
    Deactivates old key and generates new one.
    """
    try:
        from services.customer_service.schemas import ConsumerRotateKeyResponseData
        from services.shared.event_publisher import get_event_publisher

        plaintext_key, event = crud.rotate_api_key(db, consumer.consumer_id)

        if not plaintext_key:
            error_resp = error_response(status.HTTP_404_NOT_FOUND, "Consumer not found or inactive")
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)

        # Try to publish consumer_key_rotated event to RabbitMQ
        try:
            publisher = get_event_publisher()
            if publisher:
                publish_success = publisher.publish_event(
                    event_id=event.event_id,
                    event_type="consumer_key_rotated",
                    customer_id=consumer.consumer_id,  # Using consumer_id as customer_id
                    name=consumer.name,
                    status=consumer.status,
                    created_at=event.created_at,
                    consumer_name=consumer.name,
                )

                if publish_success:
                    event.publish_status = "published"
                    event.published_at = utcnow()
                    event.deliver_try_count = 1
                    event.deliver_last_tried_at = utcnow()
                else:
                    event.publish_failure_reason = PUBLISH_ERROR_RABBITMQ_FALSE
                db.commit()
            else:
                event.publish_failure_reason = PUBLISH_ERROR_PUBLISHER_NONE
                db.commit()
        except Exception as mq_error:
            event.publish_failure_reason = f"{type(mq_error).__name__}: {str(mq_error)}"
            db.commit()

        response_data = ConsumerRotateKeyResponseData(api_key=plaintext_key)
        return success_response(response_data.model_dump(), status.HTTP_200_OK)

    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to rotate API key: {str(e)}")
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.get("/consumer/me", response_model=ConsumerGetStandardResponse, status_code=status.HTTP_200_OK)
def get_consumer_me(
    request: Request, db: Session = Depends(get_db), consumer=Depends(verify_api_key), _=Depends(rate_limit_middleware)
):
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
            updated_at=consumer.updated_at,
        )

        return success_response(response_data.model_dump(), status.HTTP_200_OK)

    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to retrieve consumer data: {str(e)}"
        )
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.get("/consumer/me/api-key", response_model=ConsumerKeyStatusStandardResponse, status_code=status.HTTP_200_OK)
def get_consumer_key_status(
    request: Request, db: Session = Depends(get_db), consumer=Depends(verify_api_key), _=Depends(rate_limit_middleware)
):
    """
    Get authenticated consumer's API key metadata.
    Does not return key value, only status/timestamps.
    """
    try:
        from services.customer_service.schemas import ConsumerKeyStatusResponseData

        api_key_record = crud.get_api_key_status(db, consumer.consumer_id)

        if not api_key_record:
            error_resp = error_response(status.HTTP_404_NOT_FOUND, "No active API key found")
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)

        response_data = ConsumerKeyStatusResponseData(
            status=api_key_record.status,
            created_at=api_key_record.created_at,
            expires_at=api_key_record.expires_at,
            last_used_at=api_key_record.last_used_at,
            updated_at=api_key_record.updated_at,
        )

        return success_response(response_data.model_dump(), status.HTTP_200_OK)

    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to retrieve API key status: {str(e)}"
        )
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.post(
    "/consumer/me/api-key/deactivate", response_model=CustomerTagStandardResponse, status_code=status.HTTP_200_OK
)
def deactivate_consumer_key(
    request: Request, db: Session = Depends(get_db), consumer=Depends(verify_api_key), _=Depends(rate_limit_middleware)
):
    """
    Deactivate authenticated consumer's API key.
    After this call, key becomes invalid.
    """
    try:
        from services.shared.event_publisher import get_event_publisher

        success, event = crud.deactivate_api_key(db, consumer.consumer_id)

        if not success:
            error_resp = error_response(status.HTTP_404_NOT_FOUND, "No active API key found to deactivate")
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)

        # Try to publish consumer_key_deactivated event to RabbitMQ
        try:
            publisher = get_event_publisher()
            if publisher:
                publish_success = publisher.publish_event(
                    event_id=event.event_id,
                    event_type="consumer_key_deactivated",
                    customer_id=consumer.consumer_id,  # Using consumer_id as customer_id
                    name=consumer.name,
                    status=consumer.status,
                    created_at=event.created_at,
                    consumer_name=consumer.name,
                )

                if publish_success:
                    event.publish_status = "published"
                    event.published_at = utcnow()
                    event.deliver_try_count = 1
                    event.deliver_last_tried_at = utcnow()
                else:
                    event.publish_failure_reason = PUBLISH_ERROR_RABBITMQ_FALSE
                db.commit()
            else:
                event.publish_failure_reason = PUBLISH_ERROR_PUBLISHER_NONE
                db.commit()
        except Exception as mq_error:
            event.publish_failure_reason = f"{type(mq_error).__name__}: {str(mq_error)}"
            db.commit()

        return success_response({}, status.HTTP_200_OK)

    except Exception as e:
        error_resp = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to deactivate API key: {str(e)}")
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.post(
    "/admin/consumer/{consumer_id}/change-status",
    response_model=ConsumerChangeStatusStandardResponse,
    status_code=status.HTTP_200_OK,
)
def change_consumer_status_admin(
    consumer_id: UUID, status_change: ConsumerChangeStatusRequest, request: Request, db: Session = Depends(get_db)
):
    """
    Admin endpoint: Change consumer status.
    TODO: Add admin authentication middleware.
    """
    try:
        from services.shared.event_publisher import get_event_publisher

        updated_consumer, event = crud.change_consumer_status(db, consumer_id, status_change.status)

        if not updated_consumer:
            error_resp = error_response(status.HTTP_404_NOT_FOUND, f"Consumer {consumer_id} not found")
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)

        # Try to publish consumer_status_changed event to RabbitMQ
        try:
            publisher = get_event_publisher()
            if publisher:
                publish_success = publisher.publish_event(
                    event_id=event.event_id,
                    event_type="consumer_status_changed",
                    customer_id=consumer_id,  # Using consumer_id as customer_id
                    name=updated_consumer.name,
                    status=updated_consumer.status,
                    created_at=event.created_at,
                    consumer_name=updated_consumer.name,
                )

                if publish_success:
                    event.publish_status = "published"
                    event.published_at = utcnow()
                    event.deliver_try_count = 1
                    event.deliver_last_tried_at = utcnow()
                else:
                    event.publish_failure_reason = PUBLISH_ERROR_RABBITMQ_FALSE
                db.commit()
            else:
                event.publish_failure_reason = PUBLISH_ERROR_PUBLISHER_NONE
                db.commit()
        except Exception as mq_error:
            event.publish_failure_reason = f"{type(mq_error).__name__}: {str(mq_error)}"
            db.commit()

        return success_response({}, status.HTTP_200_OK)

    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to change consumer status: {str(e)}"
        )
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


@router.patch(
    "/admin/customer/{customer_id}/status",
    response_model=CustomerStatusChangeStandardResponse,
    status_code=status.HTTP_200_OK,
)
def change_customer_status_admin(
    customer_id: UUID, status_change: CustomerStatusChange, request: Request, db: Session = Depends(get_db)
):
    """
    Admin endpoint: Change customer status (including BLOCKED → ACTIVE unblock).
    Bypasses consumer isolation for admin operations.

    TODO: Add admin authentication middleware.

    Args:
        customer_id: UUID of customer
        status_change: New status (must include customer_id and status)

    Returns:
        Standardized response with detail only
    """
    from services.customer_service.constants import CUSTOMER_STATUS_TRANSITIONS, EVENT_TYPE_CUSTOMER_STATUS_CHANGE

    try:
        # Validate customer_id matches request body
        if status_change.customer_id != customer_id:
            error_resp = error_response(
                status.HTTP_400_BAD_REQUEST,
                f"customer_id in URL ({customer_id}) does not match request body ({status_change.customer_id})",
            )
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_resp)

        # Get customer WITHOUT consumer_id validation (admin access)
        db_customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()

        if not db_customer:
            error_resp = error_response(status.HTTP_404_NOT_FOUND, f"Customer {customer_id} not found")
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp)

        # Check if customer already has the requested status
        if db_customer.status == status_change.status:
            error_resp = error_response(
                status.HTTP_409_CONFLICT, f"Customer {customer_id} is already {status_change.status}"
            )
            return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=error_resp)

        # Validate status transition
        old_status = db_customer.status
        new_status = status_change.status

        allowed_transitions = CUSTOMER_STATUS_TRANSITIONS.get(old_status, [])
        if new_status not in allowed_transitions:
            error_resp = error_response(
                status.HTTP_400_BAD_REQUEST,
                f"Invalid status transition: {old_status} → {new_status}. Allowed: {allowed_transitions}",
            )
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_resp)

        # Update customer status (no consumer_id check - admin override)
        db_customer.status = new_status
        db.commit()
        db.refresh(db_customer)

        print(f"[ADMIN] Updated customer {customer_id} status: {old_status} → {new_status}")

        # Create customer_status_change event
        event = crud.create_customer_event(
            db=db,
            customer_id=customer_id,
            event_type=EVENT_TYPE_CUSTOMER_STATUS_CHANGE,
            source_service="PATCH: /admin/customer/{customer_id}/status",
            payload={
                "customer_id": str(customer_id),
                "old_status": old_status,
                "new_status": new_status,
                "admin_action": True,
            },
            metadata={"changed_at": db_customer.updated_at.isoformat(), "source": "ADMIN"},
            publish_status="pending",
            published_at=None,
            publish_try_count=1,
            publish_last_tried_at=utcnow(),
            publish_failure_reason=None,
            consumer_id=db_customer.consumer_id,
        )

        # Try to publish to RabbitMQ
        try:
            publisher = get_event_publisher()
            if publisher:
                # Get consumer name for routing
                consumer_obj = db.query(Consumer).filter(Consumer.consumer_id == db_customer.consumer_id).first()
                consumer_name = consumer_obj.name if consumer_obj else "unknown"

                publish_success = publisher.publish_event(
                    event_id=event.event_id,
                    event_type=EVENT_TYPE_CUSTOMER_STATUS_CHANGE,
                    customer_id=customer_id,
                    name=db_customer.name,
                    status=new_status,
                    created_at=event.created_at,
                    consumer_name=consumer_name,
                    consumer_id=db_customer.consumer_id,
                )

                if publish_success:
                    event.publish_status = "published"
                    event.published_at = utcnow()
                    event.deliver_try_count = 1
                    event.deliver_last_tried_at = utcnow()
                else:
                    event.publish_failure_reason = PUBLISH_ERROR_RABBITMQ_FALSE
                db.commit()
            else:
                event.publish_failure_reason = PUBLISH_ERROR_PUBLISHER_NONE
                db.commit()
        except Exception as mq_error:
            event.publish_failure_reason = f"{type(mq_error).__name__}: {str(mq_error)}"
            db.commit()
            print(f"[ADMIN] Event publish failed (non-blocking): {event.publish_failure_reason}")

        return success_response({}, status.HTTP_200_OK)

    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to change customer status: {str(e)}"
        )
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)


# ============================================
# Analytics API Endpoints (Power BI Integration - Task 1)
# ============================================


@router.get("/analytics/snapshots")
def get_analytics_snapshots(
    start_date: str = None,
    end_date: str = None,
    snapshot_type: str = "all",
    page: int = 1,
    page_size: int = 100,
    consumer=Depends(verify_api_key),
    _=Depends(rate_limit_middleware),
    db: Session = Depends(get_db),
):
    """
    Get analytics snapshots for authenticated consumer (Power BI data source).

    Query Parameters:
        - start_date: ISO 8601 date string (YYYY-MM-DD), default: 30 days ago
        - end_date: ISO 8601 date string (YYYY-MM-DD), default: today
        - snapshot_type: "all" | "consumer" | "global", default: "all"
        - page: Page number (1-indexed), default: 1
        - page_size: Records per page (1-1000), default: 100

    Returns:
        Paginated list of analytics snapshots (consumer's own + global)

    Security:
        - Consumer sees only their own snapshots + global snapshots
        - Cannot query other consumers' data
    """
    from datetime import date
    import math

    try:
        # Parse and validate date parameters
        if start_date:
            try:
                # Handle both date-only (YYYY-MM-DD) and full datetime strings
                if "T" in start_date:
                    start_dt = datetime.fromisoformat(start_date)
                else:
                    # Date only - set to beginning of day
                    start_dt = datetime.fromisoformat(start_date + "T00:00:00")
            except ValueError:
                error_resp = error_response(
                    status.HTTP_400_BAD_REQUEST,
                    f"Invalid start_date format. Expected YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS, got: {start_date}",
                )
                return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_resp)
        else:
            # Default: 30 days ago at beginning of day
            start_dt = datetime.combine(date.today() - timedelta(days=30), datetime.min.time())

        if end_date:
            try:
                # Handle both date-only (YYYY-MM-DD) and full datetime strings
                if "T" in end_date:
                    end_dt = datetime.fromisoformat(end_date)
                else:
                    # Date only - set to end of day
                    end_dt = datetime.fromisoformat(end_date + "T23:59:59.999999")
            except ValueError:
                error_resp = error_response(
                    status.HTTP_400_BAD_REQUEST,
                    f"Invalid end_date format. Expected YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS, got: {end_date}",
                )
                return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_resp)
        else:
            # Default: today end of day
            end_dt = datetime.combine(date.today(), datetime.max.time())

        # Validate date range
        if start_dt > end_dt:
            error_resp = error_response(
                status.HTTP_400_BAD_REQUEST,
                f"start_date ({start_date}) must be before or equal to end_date ({end_date})",
            )
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_resp)

        # Validate snapshot_type
        if snapshot_type not in ["all", "consumer", "global"]:
            error_resp = error_response(
                status.HTTP_400_BAD_REQUEST,
                f"Invalid snapshot_type. Expected 'all', 'consumer', or 'global', got: {snapshot_type}",
            )
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_resp)

        # Validate pagination parameters
        if page < 1:
            error_resp = error_response(status.HTTP_400_BAD_REQUEST, f"page must be >= 1, got: {page}")
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_resp)

        if page_size < 1 or page_size > 1000:
            error_resp = error_response(
                status.HTTP_400_BAD_REQUEST, f"page_size must be between 1 and 1000, got: {page_size}"
            )
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_resp)

        # Call CRUD function
        snapshots, total_count = crud.get_analytics_snapshots(
            db=db,
            authenticated_consumer_id=consumer.consumer_id,
            start_date=start_dt,
            end_date=end_dt,
            snapshot_type=snapshot_type,
            page=page,
            page_size=page_size,
        )

        # Calculate pagination metadata
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

        # Build response
        response_data = {
            "snapshots": snapshots,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_records": total_count,
                "total_pages": total_pages,
            },
        }

        return success_response(response_data, status.HTTP_200_OK)

    except Exception as e:
        error_resp = error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to retrieve analytics snapshots: {str(e)}"
        )
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp)
