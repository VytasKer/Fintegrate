"""
Prometheus metrics for Customer Service.

Exposes key business and technical metrics for monitoring integration health.
"""

from prometheus_client import Counter, Histogram, Gauge, Info
import time

# === HTTP Metrics ===
http_requests_total = Counter(
    "customer_service_http_requests_total", "Total HTTP requests", ["method", "endpoint", "status_code", "consumer"]
)

http_request_duration_seconds = Histogram(
    "customer_service_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint", "consumer"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# === Business Metrics ===
customer_operations_total = Counter(
    "customer_service_operations_total", "Customer CRUD operations", ["operation", "consumer", "status"]
)

event_publish_total = Counter(
    "customer_service_event_publish_total", "Event publishing attempts", ["event_type", "consumer", "status"]
)

event_publish_duration_seconds = Histogram(
    "customer_service_event_publish_duration_seconds",
    "Event publish latency to RabbitMQ",
    ["event_type", "consumer"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# === Database Metrics ===
db_query_duration_seconds = Histogram(
    "customer_service_db_query_duration_seconds",
    "Database query latency",
    ["operation", "table"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

db_connection_pool_size = Gauge("customer_service_db_connection_pool_size", "Active database connections")

# === RabbitMQ Metrics ===
rabbitmq_publish_failures_total = Counter(
    "customer_service_rabbitmq_publish_failures_total",
    "Failed RabbitMQ publish attempts",
    ["event_type", "consumer", "reason"],
)

event_outbox_pending = Gauge(
    "customer_service_event_outbox_pending", "Events pending publish in outbox table", ["consumer"]
)

# === Service Info ===
service_info = Info("customer_service_info", "Customer Service version and build info")

service_info.info({"version": "1.0.0", "environment": "development", "service": "customer_service"})


# === Helper Functions ===


class MetricsTimer:
    """Context manager for tracking operation duration."""

    def __init__(self, histogram, **labels):
        self.histogram = histogram
        self.labels = labels
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.histogram.labels(**self.labels).observe(duration)


def record_customer_operation(operation: str, consumer: str, success: bool):
    """Record customer CRUD operation metric."""
    status = "success" if success else "failure"
    customer_operations_total.labels(operation=operation, consumer=consumer, status=status).inc()


def record_event_publish(event_type: str, consumer: str, success: bool, duration: float):
    """Record event publishing metrics."""
    status = "success" if success else "failure"

    event_publish_total.labels(event_type=event_type, consumer=consumer, status=status).inc()

    if success:
        event_publish_duration_seconds.labels(event_type=event_type, consumer=consumer).observe(duration)


def record_rabbitmq_failure(event_type: str, consumer: str, reason: str):
    """Record RabbitMQ publish failure."""
    rabbitmq_publish_failures_total.labels(event_type=event_type, consumer=consumer, reason=reason).inc()


def update_outbox_pending_count(consumer: str, count: int):
    """Update gauge for pending events in outbox."""
    event_outbox_pending.labels(consumer=consumer).set(count)
