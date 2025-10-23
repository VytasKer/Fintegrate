from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.customer_service.routes import router
from services.customer_service.config import get_settings
from services.customer_service.database import engine, Base
from services.shared.response_handler import error_response

settings = get_settings()

# Create tables (if not exists)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Fintegrate Customer Service",
    description="Customer management microservice for integration learning",
    version=settings.service_version
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
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            description
        )
    )


# Include routes
app.include_router(router, tags=["customers"])


@app.get("/", tags=["health"])
def root():
    """Health check endpoint."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running"
    }
