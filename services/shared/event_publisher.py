"""
Event Publisher for RabbitMQ
Publishes domain events to message queue for async processing.
"""
import pika
import json
import os
from typing import Dict, Any
from uuid import UUID
from datetime import datetime


class EventPublisher:
    """RabbitMQ event publisher with connection management."""
    
    def __init__(self, host: str = 'localhost', port: int = 5672, 
                 username: str = 'fintegrate_user', password: str = 'fintegrate_pass'):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.connection = None
        self.channel = None
    
    def connect(self):
        """Establish connection to RabbitMQ."""
        credentials = pika.PlainCredentials(self.username, self.password)
        parameters = pika.ConnectionParameters(
            host=self.host,
            port=self.port,
            credentials=credentials,
            connection_attempts=3,
            retry_delay=1,
            socket_timeout=5,
            blocked_connection_timeout=5
        )
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        
        # Declare exchange (topic exchange for routing flexibility)
        self.channel.exchange_declare(
            exchange='customer_events',
            exchange_type='topic',
            durable=True
        )
    
    def publish_event(self, event_id: UUID, event_type: str, 
                     customer_id: UUID, name: str, status: str, 
                     created_at: datetime, consumer_name: str = 'system_default') -> bool:
        """
        Publish customer event to consumer-specific RabbitMQ queue.
        
        Args:
            event_id: Event UUID from customer_events table
            event_type: Event type (customer_creation, customer_deletion, etc.)
            customer_id: Customer UUID
            name: Customer name
            status: Customer status
            created_at: Event timestamp
            consumer_name: Consumer name for queue routing (default: 'system_default')
            
        Returns:
            True if published successfully, False otherwise
        """
        print(f"[DEBUG] Publishing event {event_id} with consumer_name='{consumer_name}'")
        connection = None
        try:
            # Create fresh connection for each publish
            credentials = pika.PlainCredentials(self.username, self.password)
            parameters = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                credentials=credentials,
                connection_attempts=3,
                retry_delay=1,
                socket_timeout=5,
                blocked_connection_timeout=5
            )
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            
            # Declare exchange
            channel.exchange_declare(
                exchange='customer_events',
                exchange_type='topic',
                durable=True
            )
            
            # Construct consumer-specific queue names
            queue_name = f'customer_notification_{consumer_name}'
            dlq_name = f'customer_notification_{consumer_name}_DLQ'
            print(f"[DEBUG] Declaring queue: {queue_name}")
            
            # Declare DLQ (no dead-letter routing for DLQ itself)
            channel.queue_declare(
                queue=dlq_name,
                durable=True
            )
            
            # Declare main queue with DLQ configuration
            channel.queue_declare(
                queue=queue_name,
                durable=True,
                arguments={
                    'x-dead-letter-exchange': 'customer_events',
                    'x-dead-letter-routing-key': f'customer.dlq.{consumer_name}',
                    'x-message-ttl': 86400000,  # 24 hours in milliseconds
                    'x-max-length': 100000  # Prevent unbounded growth
                }
            )
            
            # Bind main queue to exchange with consumer-specific routing pattern
            # Pattern: customer.*.{consumer_name} matches all event types for this consumer
            channel.queue_bind(
                exchange='customer_events',
                queue=queue_name,
                routing_key=f'customer.*.{consumer_name}'
            )
            
            # Bind DLQ to exchange
            channel.queue_bind(
                exchange='customer_events',
                queue=dlq_name,
                routing_key=f'customer.dlq.{consumer_name}'
            )
            
            # Message structure matching customer_events table
            message = {
                "event_id": str(event_id) if event_id else None,
                "event_type": event_type,
                "data": {
                    "customer_id": str(customer_id),
                    "name": name,
                    "status": status
                },
                "metadata": {
                    "created_at": created_at.isoformat()
                }
            }
            
            # Publish to exchange with consumer-specific routing key
            # Pattern: customer.{event_type}.{consumer_name}
            # Note: event_type comes in as "customer_creation", "customer_deletion" etc.
            # We want routing key like: customer.creation.consumer_name (not customer.customer.creation...)
            # So we strip the "customer_" prefix from event_type before building routing key
            event_suffix = event_type.replace('customer_', '', 1) if event_type.startswith('customer_') else event_type
            routing_key = f"customer.{event_suffix}.{consumer_name}"
            print(f"[DEBUG] Publishing to exchange 'customer_events' with routing_key='{routing_key}'")
            
            channel.basic_publish(
                exchange='customer_events',
                routing_key=routing_key,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent message
                    content_type='application/json'
                )
            )
            
            return True
        except Exception as e:
            print(f"Failed to publish event to RabbitMQ: {str(e)}")
            return False
        finally:
            if connection and not connection.is_closed:
                try:
                    connection.close()
                except Exception:
                    pass
    
    def close(self):
        """Close RabbitMQ connection."""
        if self.connection and not self.connection.is_closed:
            self.connection.close()


# Singleton instance for reuse across requests
_publisher_instance = None

def get_event_publisher() -> EventPublisher:
    """Get or create EventPublisher singleton with environment variable support."""
    global _publisher_instance
    if _publisher_instance is None:
        # Use environment variables (Docker) or defaults (local)
        host = os.getenv('RABBITMQ_HOST', 'localhost')
        port = int(os.getenv('RABBITMQ_PORT', '5672'))
        username = os.getenv('RABBITMQ_USER', 'fintegrate_user')
        password = os.getenv('RABBITMQ_PASS', 'fintegrate_pass')
        
        _publisher_instance = EventPublisher(
            host=host,
            port=port,
            username=username,
            password=password
        )
    return _publisher_instance
