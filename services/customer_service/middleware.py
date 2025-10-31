"""
Authentication Middleware for API Key Validation
"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from services.customer_service.database import SessionLocal
from services.customer_service import crud
from services.shared.response_handler import error_response


async def verify_api_key(request: Request):
    """
    Dependency to verify X-API-Key header and attach consumer to request state.
    Raises HTTPException if key invalid or missing.
    """
    api_key = request.headers.get("X-API-Key")
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response(
                status_code="401",
                status_name="UNAUTHORIZED",
                status_description="Missing X-API-Key header"
            )
        )
    
    # Validate minimum length
    if len(api_key) < 32:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response(
                status_code="401",
                status_name="UNAUTHORIZED",
                status_description="Invalid API key format"
            )
        )
    
    # Authenticate key
    db: Session = SessionLocal()
    try:
        consumer = crud.get_consumer_by_api_key(db, api_key)
        
        if not consumer:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_response(
                    status_code="401",
                    status_name="UNAUTHORIZED",
                    status_description="Invalid or expired API key"
                )
            )
        
        # Attach consumer to request state
        request.state.consumer = consumer
        request.state.consumer_id = consumer.consumer_id
        
    finally:
        db.close()
    
    return consumer
