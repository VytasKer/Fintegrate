"""
Middleware for automatic HTTP metrics collection.

Wraps all requests to track latency, status codes, and request counts.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP metrics for all requests."""

    async def dispatch(self, request: Request, call_next):
        # Import here to avoid circular dependencies
        from services.customer_service.metrics import http_requests_total, http_request_duration_seconds

        # Track request timing
        start_time = time.time()

        # Process request (auth happens inside call_next via route dependencies)
        response: Response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Extract endpoint path (remove query params)
        path = request.url.path

        # Re-check consumer AFTER request processing (auth dependency has now executed)
        consumer_obj = getattr(request.state, "consumer", None)
        consumer_label = consumer_obj.name if consumer_obj and hasattr(consumer_obj, "name") else "unauthenticated"

        # Record metrics with correct consumer label
        http_requests_total.labels(
            method=request.method, endpoint=path, status_code=response.status_code, consumer=consumer_label
        ).inc()

        http_request_duration_seconds.labels(method=request.method, endpoint=path, consumer=consumer_label).observe(
            duration
        )

        return response
