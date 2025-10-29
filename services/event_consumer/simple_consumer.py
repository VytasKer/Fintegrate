"""
Simple RabbitMQ Consumer
Listens to customer_events queue and prints messages to console.
Confirms delivery to Fintegrate API for tracking.
"""
import pika
import json
import sys
import requests
import os
from datetime import datetime

# Global variable for customer service URL (set in main)
CUSTOMER_SERVICE_URL = "http://localhost:8000"


def callback(ch, method, properties, body):
    """Process received message and confirm delivery to Fintegrate API."""
    event_id = None
    processing_status = "received"
    failure_reason = None
    
    try:
        message = json.loads(body)
        event_id = message['event_id']
        
        print("\n" + "="*60)
        print("RECEIVED EVENT FROM RABBITMQ")
        print("="*60)
        print(f"Event ID: {event_id}")
        print(f"Event Type: {message['event_type']}")
        print(f"Customer ID: {message['data']['customer_id']}")
        print(f"Customer Name: {message['data']['name']}")
        print(f"Customer Status: {message['data']['status']}")
        print(f"Created At: {message['metadata']['created_at']}")
        print("="*60)
        
        # ===== TEMPORARY: DLQ Testing =====
        # Uncomment ONE scenario to test:
        
        # Scenario 1: Permanent error (missing field) → immediate DLQ
        # = message['data']['nonexistent_field']  # Raises KeyError
        
        # Scenario 2: Transient error → 3 retries then DLQ
        # raise ConnectionError("Simulated DB timeout")
        
        # Scenario 3: Malformed JSON → immediate DLQ
        # (Manually publish invalid JSON via RabbitMQ UI to test)
        # ===================================
        
        # Mark as successfully processed
        processing_status = "processed"
        
        # Acknowledge message (remove from queue)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
        # Confirm delivery to Fintegrate API
        try:
            confirmation_payload = {
                "event_id": event_id,
                "status": processing_status,
                "received_at": datetime.utcnow().isoformat() + "Z",
                "failure_reason": failure_reason
            }
            
            print(f"Calling POST /events/confirm-delivery for event {event_id}...")
            response = requests.post(
                f"{CUSTOMER_SERVICE_URL}/events/confirm-delivery",
                json=confirmation_payload,
                timeout=5
            )
            
            if response.status_code == 200:
                print(f"✓ Delivery confirmed successfully for event {event_id}")
            else:
                print(f"✗ Delivery confirmation failed: {response.status_code} - {response.text}")
                
        except requests.exceptions.RequestException as api_error:
            print(f"✗ Failed to call delivery confirmation API: {str(api_error)}")
        
        print("="*60 + "\n")
        
    except (KeyError, json.JSONDecodeError) as permanent_error:
        # Permanent error: malformed message, missing required fields
        processing_status = "failed"
        failure_reason = f"{type(permanent_error).__name__}: {str(permanent_error)}"
        
        print(f"PERMANENT ERROR - Sending to DLQ: {failure_reason}")
        print(f"Message body: {body}")
        
        # Reject without requeue → goes to DLQ
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        # Try to confirm failed delivery
        if event_id:
            try:
                confirmation_payload = {
                    "event_id": event_id,
                    "status": processing_status,
                    "received_at": datetime.utcnow().isoformat() + "Z",
                    "failure_reason": failure_reason
                }
                requests.post(
                    f"{CUSTOMER_SERVICE_URL}/events/confirm-delivery",
                    json=confirmation_payload,
                    timeout=5
                )
                print(f"✓ Failed delivery reported for event {event_id}")
            except:
                pass  # Silently ignore API errors for failed messages
        
    except Exception as transient_error:
        # Transient error: might succeed on retry
        failure_reason = f"{type(transient_error).__name__}: {str(transient_error)}"
        print(f"TRANSIENT ERROR - Will retry: {failure_reason}")
        
        # Check retry count from headers
        retry_count = 0
        if properties.headers and 'x-retry-count' in properties.headers:
            retry_count = properties.headers['x-retry-count']
        
        print(f"Current retry count from headers: {retry_count}")
        
        if retry_count >= 3:
            # Max retries exceeded → send to DLQ
            processing_status = "failed"
            print(f"Max retries ({retry_count}) exceeded - Sending to DLQ")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
            # Confirm failed delivery after max retries
            if event_id:
                try:
                    confirmation_payload = {
                        "event_id": event_id,
                        "status": processing_status,
                        "received_at": datetime.utcnow().isoformat() + "Z",
                        "failure_reason": f"Max retries exceeded: {failure_reason}"
                    }
                    requests.post(
                        f"{CUSTOMER_SERVICE_URL}/events/confirm-delivery",
                        json=confirmation_payload,
                        timeout=5
                    )
                    print(f"✓ Failed delivery (max retries) reported for event {event_id}")
                except:
                    pass
        else:
            # Increment retry counter and republish with delay
            print(f"Retry attempt {retry_count + 1}/3 - Republishing with retry header")
            new_headers = {'x-retry-count': retry_count + 1}
            if properties.headers:
                # Merge existing headers
                for key, value in properties.headers.items():
                    if key != 'x-retry-count':
                        new_headers[key] = value
            
            new_properties = pika.BasicProperties(
                headers=new_headers,
                delivery_mode=2,
                content_type='application/json'
            )
            
            # ACK original message first (remove from queue)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
            # Then republish with updated retry count
            # Note: Goes back to same queue immediately (no delay mechanism yet)
            ch.basic_publish(
                exchange='customer_events',
                routing_key=method.routing_key,
                body=body,
                properties=new_properties
            )
            print(f"Message republished with retry_count={retry_count + 1}")
            print("="*60 + "\n")


def main():
    """Start consumer and listen for messages."""
    global CUSTOMER_SERVICE_URL
    
    try:
        # Get configuration from environment variables (Docker) or use defaults (local)
        rabbitmq_host = os.getenv('RABBITMQ_HOST', 'localhost')
        rabbitmq_port = int(os.getenv('RABBITMQ_PORT', '5672'))
        rabbitmq_user = os.getenv('RABBITMQ_USER', 'fintegrate_user')
        rabbitmq_pass = os.getenv('RABBITMQ_PASS', 'fintegrate_pass')
        CUSTOMER_SERVICE_URL = os.getenv('CUSTOMER_SERVICE_URL', 'http://localhost:8000')
        
        # Connect to RabbitMQ
        credentials = pika.PlainCredentials(rabbitmq_user, rabbitmq_pass)
        parameters = pika.ConnectionParameters(
            host=rabbitmq_host,
            port=rabbitmq_port,
            credentials=credentials
        )
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        # Declare dead letter exchange (DLX)
        channel.exchange_declare(
            exchange='customer_events_dlx',
            exchange_type='direct',
            durable=True
        )
        
        # Declare dead letter queue (DLQ)
        channel.queue_declare(
            queue='customer_notifications_DLQ',
            durable=True
        )
        
        # Bind DLQ to DLX
        channel.queue_bind(
            exchange='customer_events_dlx',
            queue='customer_notifications_DLQ',
            routing_key='dlq'
        )
        
        # Declare exchange (matches publisher)
        channel.exchange_declare(
            exchange='customer_events',
            exchange_type='topic',
            durable=True
        )
        
        # Declare main queue with DLX configuration
        result = channel.queue_declare(
            queue='customer_notifications',
            durable=True,
            arguments={
                'x-dead-letter-exchange': 'customer_events_dlx',
                'x-dead-letter-routing-key': 'dlq'
            }
        )
        queue_name = result.method.queue
        
        # Bind queue to exchange (subscribe to all customer events)
        channel.queue_bind(
            exchange='customer_events',
            queue=queue_name,
            routing_key='customer.#'  # Matches customer.creation, customer.deletion, customer.status.change, etc.
        )
        
        print("="*60)
        print("CONSUMER STARTED - Waiting for messages...")
        print(f"Queue: {queue_name}")
        print(f"DLQ: customer_notifications_DLQ")
        print(f"Exchange: customer_events")
        print(f"Routing Key Pattern: customer.#")
        print(f"Max Retries: 3")
        print("Press Ctrl+C to exit")
        print("="*60 + "\n")
        
        # Start consuming
        channel.basic_consume(
            queue=queue_name,
            on_message_callback=callback
        )
        
        channel.start_consuming()
        
    except KeyboardInterrupt:
        print("\nConsumer stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"Consumer error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
