from fastapi import Request
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Dict, Any
from services.customer_service import crud
import uuid


def log_error_to_audit(
    db: Session,
    request: Request,
    entity: str,
    entity_id: UUID | str,
    action: str,
    error_response: Dict[str, Any]
):
    """
    Log API errors to audit_log table for analysis and statistics.
    
    Args:
        db: Database session
        request: FastAPI request object
        entity: Entity type (e.g., "customer")
        entity_id: UUID of affected entity (or generated UUID for validation errors)
        action: Action being performed (e.g., "create_customer", "delete_customer")
        error_response: Error response data including detail
    """
    try:
        # Extract client IP
        client_ip = request.client.host if request.client else None
        
        # Extract request data
        request_data = {
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": dict(request.query_params) if request.query_params else None
        }
        
        # Convert entity_id to UUID if string
        if isinstance(entity_id, str):
            try:
                entity_id = UUID(entity_id)
            except ValueError:
                # Generate random UUID for non-UUID entity_ids (e.g., validation errors)
                entity_id = uuid.uuid4()
        
        # Create audit log entry
        crud.create_audit_log(
            db=db,
            entity=entity,
            entity_id=entity_id,
            action=action,
            user_name="system",  # Future: extract from JWT/auth
            ip_address=client_ip,
            request_data=request_data,
            response_data=error_response
        )
    except Exception as e:
        # Fail silently to not disrupt error response to client
        print(f"Failed to log audit entry: {str(e)}")
