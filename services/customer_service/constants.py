"""
Constants for customer service.
Reduces code duplication and improves maintainability.
"""

# Event publishing error messages
PUBLISH_ERROR_RABBITMQ_FALSE = "RabbitMQ publish returned False"
PUBLISH_ERROR_PUBLISHER_NONE = "EventPublisher connection is None"

# Event statuses
EVENT_STATUS_PENDING = "pending"
EVENT_STATUS_PUBLISHED = "published"
EVENT_STATUS_FAILED = "failed"
EVENT_STATUS_DELIVERED = "delivered"

# Delivery statuses
DELIVERY_STATUS_PENDING = "pending"
DELIVERY_STATUS_DELIVERED = "delivered"
DELIVERY_STATUS_FAILED = "failed"
