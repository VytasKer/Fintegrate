"""
Authentication Middleware for API Key Validation
"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from services.customer_service.database import SessionLocal
from services.customer_service import crud
from services.shared.response_handler import error_response
import uuid


async def verify_api_key(request: Request):
    """
    Dependency to verify X-API-Key header and attach consumer to request state.
    Raises HTTPException if key invalid or missing.
    """
    api_key = request.headers.get("X-API-Key")
    
    if not api_key:
        # Log to audit - authentication failure
        db: Session = SessionLocal()
        try:
            from services.shared.audit_logger import log_error_to_audit
            error_resp = error_response(status.HTTP_401_UNAUTHORIZED, "Missing X-API-Key header")
            log_error_to_audit(
                db=db,
                request=request,
                entity="authentication",
                entity_id=str(uuid.uuid4()),  # Generate UUID for auth failures
                action="verify_api_key",
                error_response=error_resp
            )
            db.commit()
        except Exception as e:
            print(f"Failed to log authentication error to audit: {e}")
        finally:
            db.close()
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response(status.HTTP_401_UNAUTHORIZED, "Missing X-API-Key header")
        )
    
    # Validate minimum length
    if len(api_key) < 32:
        # Log to audit - authentication failure
        db: Session = SessionLocal()
        try:
            from services.shared.audit_logger import log_error_to_audit
            error_resp = error_response(status.HTTP_401_UNAUTHORIZED, "Invalid API key format")
            log_error_to_audit(
                db=db,
                request=request,
                entity="authentication",
                entity_id=str(uuid.uuid4()),
                action="verify_api_key",
                error_response=error_resp
            )
            db.commit()
        except Exception as e:
            print(f"Failed to log authentication error to audit: {e}")
        finally:
            db.close()
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response(status.HTTP_401_UNAUTHORIZED, "Invalid API key format")
        )
    
    # Authenticate key
    db: Session = SessionLocal()
    try:
        consumer = crud.get_consumer_by_api_key(db, api_key)
        
        if not consumer:
            # Log to audit - authentication failure
            from services.shared.audit_logger import log_error_to_audit
            error_resp = error_response(status.HTTP_401_UNAUTHORIZED, "Invalid or expired API key")
            log_error_to_audit(
                db=db,
                request=request,
                entity="authentication",
                entity_id=str(uuid.uuid4()),
                action="verify_api_key",
                error_response=error_resp
            )
            db.commit()
            db.close()
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_response(status.HTTP_401_UNAUTHORIZED, "Invalid or expired API key")
            )
        
        # Attach consumer to request state
        request.state.consumer = consumer
        request.state.consumer_id = consumer.consumer_id
        
    finally:
        db.close()
    
    return consumer
