from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.customer_service.routes import router
from services.customer_service.config import get_settings
from services.customer_service.database import engine, Base
from services.shared.response_handler import error_response
from services.customer_service.prometheus_middleware import PrometheusMiddleware

settings = get_settings()

# Create tables (if not exists)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Fintegrate Customer Service",
    description="Customer management microservice for integration learning",
    version=settings.service_version,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle Pydantic validation errors with standardized response format.
    """
    # Extract first validation error for simplified message
    errors = exc.errors()
    if errors:
        first_error = errors[0]
        field = " -> ".join(str(loc) for loc in first_error.get("loc", []))
        msg = first_error.get("msg", "Validation error")
        description = f"Validation error in field '{field}': {msg}"
    else:
        description = "Request validation failed"

    error_resp = error_response(status.HTTP_422_UNPROCESSABLE_ENTITY, description)

    # Log validation error to audit
    from services.customer_service.database import SessionLocal
    from services.shared.audit_logger import log_error_to_audit
    import uuid

    db = SessionLocal()
    try:
        log_error_to_audit(
            db=db,
            request=request,
            entity="validation",
            entity_id=str(uuid.uuid4()),
            action="validation_error",
            error_response=error_resp,
        )
    finally:
        db.close()

    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=error_resp)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Handle HTTPException with standardized response format.
    If exc.detail is already a dict (from error_response), use it directly.
    Otherwise, wrap it in error_response format.
    """
    # Check if detail is already in our standard format
    if isinstance(exc.detail, dict) and "data" in exc.detail and "detail" in exc.detail:
        # Already formatted by error_response()
        content = exc.detail
    else:
        # Plain string or other format - wrap it
        content = error_response(exc.status_code, str(exc.detail))

    return JSONResponse(status_code=exc.status_code, content=content)


# Add Prometheus metrics middleware FIRST
app.add_middleware(PrometheusMiddleware)

# Include routes
app.include_router(router, tags=["customers"])

# Mount Prometheus metrics endpoint LAST (after routes to avoid path conflicts)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/", tags=["health"])
def root():
    """Health check endpoint."""
    return {"service": settings.service_name, "version": settings.service_version, "status": "running"}
