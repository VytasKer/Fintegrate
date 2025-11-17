"""
AML Service Main Entry Point
Subscribes to customer_creation events, performs sanctions screening,
and updates customer status accordingly.
"""

import pika
import json
import sys
import os
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from services.aml_service.config import (
    DATABASE_URL,
    RABBITMQ_HOST,
    RABBITMQ_PORT,
    RABBITMQ_USER,
    RABBITMQ_PASS,
    AML_QUEUE_NAME,
    AML_EXCHANGE_NAME,
    AML_ROUTING_KEY,
)
from services.aml_service.sanctions_downloader import update_sanctions_list
from services.aml_service.sanctions_checker import perform_sanctions_check


def utcnow():
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc)


# Database session setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def update_customer_status(customer_id: str, new_status: str, consumer_id: str):
    """
    Update customer status in database.

    Args:
        customer_id: UUID of customer
        new_status: New status (ACTIVE or BLOCKED)
        consumer_id: UUID of consumer who owns the customer
    """
    db = SessionLocal()
    try:
        # Import models here to avoid circular imports
        from services.customer_service.models import Customer

        customer = (
            db.query(Customer).filter(Customer.customer_id == customer_id, Customer.consumer_id == consumer_id).first()
        )

        if customer:
            customer.status = new_status
            db.commit()
            print(f"[AML] Updated customer {customer_id} status to {new_status}")
        else:
            print(f"[AML] WARNING: Customer {customer_id} not found")

    except Exception as e:
        db.rollback()
        print(f"[AML] ERROR: Failed to update customer status: {type(e).__name__}: {str(e)}")
        raise
    finally:
        db.close()


def create_customer_event(customer_id: str, consumer_id: str, event_type: str, payload: dict, metadata: dict):
    """
    Create customer event in database.

    Args:
        customer_id: UUID of customer
        consumer_id: UUID of consumer
        event_type: Type of event (customer_blocked_aml, customer_status_change)
        payload: Event payload dict
        metadata: Event metadata dict
    """
    db = SessionLocal()
    try:
        from services.customer_service.models import CustomerEvent
        import uuid

        event = CustomerEvent(
            event_id=uuid.uuid4(),
            customer_id=customer_id,
            consumer_id=consumer_id,
            event_type=event_type,
            source_service="AML_SERVICE",
            payload_json=payload,
            metadata_json=metadata,
            publish_status="pending",
            publish_try_count=1,
            publish_last_tried_at=utcnow(),
        )

        db.add(event)
        db.commit()
        db.refresh(event)

        print(f"[AML] Created event {event.event_id} of type {event_type}")
        return event

    except Exception as e:
        db.rollback()
        print(f"[AML] ERROR: Failed to create event: {type(e).__name__}: {str(e)}")
        raise
    finally:
        db.close()


def publish_event_to_rabbitmq(
    channel,
    event_id: str,
    event_type: str,
    customer_id: str,
    customer_name: str,
    status: str,
    consumer_name: str,
    blocked_reason: str = None,
):
    """
    Publish event to RabbitMQ.

    Args:
        channel: Pika channel object
        event_id: UUID of event
        event_type: Type of event
        customer_id: UUID of customer
        customer_name: Customer name
        status: Customer status
        consumer_name: Consumer name for routing
        blocked_reason: Reason for blocking (if applicable)
    """
    try:
        message = {
            "event_id": str(event_id),
            "event_type": event_type,
            "data": {
                "customer_id": str(customer_id),
                "name": customer_name,
                "status": status,
            },
            "metadata": {
                "created_at": utcnow().isoformat() + "Z",
                "source": "AML_SERVICE",
            },
        }

        if blocked_reason:
            message["data"]["blocked_reason"] = blocked_reason

        routing_key = f"customer.{event_type.replace('customer_', '')}.{consumer_name}"

        channel.basic_publish(
            exchange=AML_EXCHANGE_NAME,
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Persistent
                content_type="application/json",
            ),
        )

        print(f"[AML] Published {event_type} event to {routing_key}")

        # Update event publish status in database
        db = SessionLocal()
        try:
            from services.customer_service.models import CustomerEvent

            event = db.query(CustomerEvent).filter(CustomerEvent.event_id == event_id).first()
            if event:
                event.publish_status = "published"
                event.published_at = utcnow()
                event.deliver_try_count = 1
                event.deliver_last_tried_at = utcnow()
                db.commit()
        finally:
            db.close()

    except Exception as e:
        print(f"[AML] ERROR: Failed to publish event: {type(e).__name__}: {str(e)}")

        # Update event publish failure in database
        db = SessionLocal()
        try:
            from services.customer_service.models import CustomerEvent

            event = db.query(CustomerEvent).filter(CustomerEvent.event_id == event_id).first()
            if event:
                event.publish_failure_reason = f"{type(e).__name__}: {str(e)}"
                db.commit()
        finally:
            db.close()


def process_customer_creation(ch, method, properties, body):
    """
    Process customer_creation event: check sanctions and update status.

    Args:
        ch: Pika channel
        method: Pika method
        properties: Pika properties
        body: Message body
    """
    try:
        message = json.loads(body)
        event_id = message["event_id"]
        customer_id = message["data"]["customer_id"]
        customer_name = message["data"]["name"]
        customer_status = message["data"]["status"]

        # Extract consumer info from metadata or routing key
        consumer_name = message.get("metadata", {}).get("consumer_name", "unknown")
        consumer_id = message.get("data", {}).get("consumer_id")

        print("\n" + "=" * 60)
        print("[AML] PROCESSING CUSTOMER CREATION EVENT")
        print("=" * 60)
        print(f"Event ID: {event_id}")
        print(f"Customer ID: {customer_id}")
        print(f"Customer Name: {customer_name}")
        print(f"Current Status: {customer_status}")
        print(f"Consumer: {consumer_name}")
        print("=" * 60)

        # Only process if status is PENDING_AML
        if customer_status != "PENDING_AML":
            print(f"[AML] Skipping - customer status is {customer_status}, not PENDING_AML")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # Update sanctions list (checks if already updated today)
        print("[AML] Checking sanctions list...")
        sanctions_available = update_sanctions_list()

        if not sanctions_available:
            print("[AML] ERROR: Sanctions list unavailable - FAILING OPEN (approving customer)")
            # Fail-open: Approve customer if sanctions list unavailable
            # In production, this should fail-closed or trigger manual review

            # Update customer status to ACTIVE (fail-open)
            update_customer_status(customer_id, "ACTIVE", consumer_id)

            # Create customer_status_change event
            event = create_customer_event(
                customer_id=customer_id,
                consumer_id=consumer_id,
                event_type="customer_status_change",
                payload={
                    "customer_id": customer_id,
                    "old_status": "PENDING_AML",
                    "new_status": "ACTIVE",
                    "reason": "FAIL_OPEN: Sanctions list unavailable",
                },
                metadata={"checked_at": utcnow().isoformat() + "Z", "source": "AML_SERVICE", "fail_open": True},
            )

            # Publish customer_status_change event
            publish_event_to_rabbitmq(
                channel=ch,
                event_id=event.event_id,
                event_type="customer_status_change",
                customer_id=customer_id,
                customer_name=customer_name,
                status="ACTIVE",
                consumer_name=consumer_name,
            )

            # Publish customer_creation event (approved)
            publish_event_to_rabbitmq(
                channel=ch,
                event_id=event_id,
                event_type="customer_creation",
                customer_id=customer_id,
                customer_name=customer_name,
                status="ACTIVE",
                consumer_name=consumer_name,
            )

            # ACK message to prevent requeue loop
            ch.basic_ack(delivery_tag=method.delivery_tag)
            print("[AML] Customer approved (fail-open), message acknowledged")
            return

        # Perform sanctions check
        print(f"[AML] Checking '{customer_name}' against sanctions list...")
        is_blocked, matched_name = perform_sanctions_check(customer_name)

        if is_blocked:
            # Customer found in sanctions list → BLOCK
            print(f"[AML] ⚠ BLOCKED: Customer matches '{matched_name}'")

            blocked_reason = (
                f"Customer creation blocked due to matching in sanction list '{matched_name}'. "
                "Please contact Fintegrate administrator."
            )

            # Update customer status to BLOCKED
            update_customer_status(customer_id, "BLOCKED", consumer_id)

            # Create customer_blocked_aml event
            event = create_customer_event(
                customer_id=customer_id,
                consumer_id=consumer_id,
                event_type="customer_blocked_aml",
                payload={
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "blocked_reason": blocked_reason,
                    "matched_sanctioned_entity": matched_name,
                },
                metadata={
                    "checked_at": utcnow().isoformat() + "Z",
                    "source": "AML_SERVICE",
                },
            )

            # Publish customer_blocked_aml event to RabbitMQ
            publish_event_to_rabbitmq(
                channel=ch,
                event_id=event.event_id,
                event_type="customer_blocked_aml",
                customer_id=customer_id,
                customer_name=customer_name,
                status="BLOCKED",
                consumer_name=consumer_name,
                blocked_reason=blocked_reason,
            )

        else:
            # Customer NOT found in sanctions list → APPROVE
            print(f"[AML] ✓ APPROVED: Customer '{customer_name}' is not sanctioned")

            # Update customer status to ACTIVE
            update_customer_status(customer_id, "ACTIVE", consumer_id)

            # Create customer_status_change event (PENDING_AML → ACTIVE)
            event = create_customer_event(
                customer_id=customer_id,
                consumer_id=consumer_id,
                event_type="customer_status_change",
                payload={
                    "customer_id": customer_id,
                    "old_status": "PENDING_AML",
                    "new_status": "ACTIVE",
                },
                metadata={
                    "checked_at": utcnow().isoformat() + "Z",
                    "source": "AML_SERVICE",
                },
            )

            # Publish customer_status_change event
            publish_event_to_rabbitmq(
                channel=ch,
                event_id=event.event_id,
                event_type="customer_status_change",
                customer_id=customer_id,
                customer_name=customer_name,
                status="ACTIVE",
                consumer_name=consumer_name,
            )

            # Publish customer_creation event (as originally intended)
            publish_event_to_rabbitmq(
                channel=ch,
                event_id=event_id,  # Use original event ID
                event_type="customer_creation",
                customer_id=customer_id,
                customer_name=customer_name,
                status="ACTIVE",
                consumer_name=consumer_name,
            )

        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"[AML] ERROR: Failed to process message: {type(e).__name__}: {str(e)}")
        print(f"Message body: {body}")
        # Reject without requeue on permanent errors
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main():
    """Start AML service and listen for customer_creation events."""
    try:
        print("=" * 60)
        print("[AML] STARTING AML SERVICE")
        print("=" * 60)
        print(f"RabbitMQ: {RABBITMQ_HOST}:{RABBITMQ_PORT}")
        print(f"Queue: {AML_QUEUE_NAME}")
        print(f"Exchange: {AML_EXCHANGE_NAME}")
        print(f"Routing Key: {AML_ROUTING_KEY}")
        print("=" * 60 + "\n")

        # Initial sanctions list update
        print("[AML] Performing initial sanctions list update...")
        update_sanctions_list()

        # Connect to RabbitMQ
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        parameters = pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT, credentials=credentials)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        # Declare exchange
        channel.exchange_declare(exchange=AML_EXCHANGE_NAME, exchange_type="topic", durable=True)

        # Declare AML queue with DLQ
        dlq_name = f"{AML_QUEUE_NAME}_DLQ"

        channel.queue_declare(queue=dlq_name, durable=True)

        channel.queue_declare(
            queue=AML_QUEUE_NAME,
            durable=True,
            arguments={
                "x-dead-letter-exchange": AML_EXCHANGE_NAME,
                "x-dead-letter-routing-key": "customer.dlq.aml_service",
                "x-message-ttl": 86400000,  # 24 hours
                "x-max-length": 100000,
            },
        )

        # Bind queue to exchange (subscribe to all customer.creation.* events)
        channel.queue_bind(exchange=AML_EXCHANGE_NAME, queue=AML_QUEUE_NAME, routing_key=AML_ROUTING_KEY)

        # Bind DLQ
        channel.queue_bind(exchange=AML_EXCHANGE_NAME, queue=dlq_name, routing_key="customer.dlq.aml_service")

        print("[AML] Waiting for customer_creation events...")
        print("Press Ctrl+C to exit\n")

        # Start consuming
        channel.basic_consume(queue=AML_QUEUE_NAME, on_message_callback=process_customer_creation)

        channel.start_consuming()

    except KeyboardInterrupt:
        print("\n[AML] Service stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"[AML] Service error: {type(e).__name__}: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
