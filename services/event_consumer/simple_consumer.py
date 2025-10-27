"""
Simple RabbitMQ Consumer
Listens to customer_events queue and prints messages to console.
"""
import pika
import json
import sys


def callback(ch, method, properties, body):
    """Process received message."""
    try:
        message = json.loads(body)
        print("\n" + "="*60)
        print("RECEIVED EVENT FROM RABBITMQ")
        print("="*60)
        print(f"Event ID: {message['event_id']}")
        print(f"Event Type: {message['event_type']}")
        print(f"Customer ID: {message['data']['customer_id']}")
        print(f"Customer Name: {message['data']['name']}")
        print(f"Customer Status: {message['data']['status']}")
        print(f"Created At: {message['metadata']['created_at']}")
        print("="*60 + "\n")
        
        # Acknowledge message (remove from queue)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"Error processing message: {str(e)}")
        # Reject and requeue message on error
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def main():
    """Start consumer and listen for messages."""
    try:
        # Connect to RabbitMQ
        credentials = pika.PlainCredentials('fintegrate_user', 'fintegrate_pass')
        parameters = pika.ConnectionParameters(
            host='localhost',
            port=5672,
            credentials=credentials
        )
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        # Declare exchange (matches publisher)
        channel.exchange_declare(
            exchange='customer_events',
            exchange_type='topic',
            durable=True
        )
        
        # Declare queue
        result = channel.queue_declare(queue='customer_notifications', durable=True)
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
        print(f"Exchange: customer_events")
        print(f"Routing Key Pattern: customer.#")
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
