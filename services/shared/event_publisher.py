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
                     created_at: datetime) -> bool:
        """
        Publish customer event to RabbitMQ.
        
        Args:
            event_id: Event UUID from customer_events table
            event_type: Event type (customer_creation, customer_deletion, etc.)
            customer_id: Customer UUID
            name: Customer name
            status: Customer status
            created_at: Event timestamp
            
        Returns:
            True if published successfully, False otherwise
        """
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
            
            # Publish to exchange with routing key pattern: event_type
            channel.basic_publish(
                exchange='customer_events',
                routing_key=event_type.replace('_', '.'),  # Convert to dot notation for topic routing
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
                except:
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
