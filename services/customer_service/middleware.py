"""
Authentication Middleware for API Key Validation
"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from services.customer_service.database import SessionLocal
from services.customer_service import crud
from services.shared.response_handler import error_response
from services.shared.utils import utcnow
import uuid


def verify_api_key(request: Request):
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


def _log_rate_limit_violation_once_per_hour(redis_client, consumer_id, hour_bucket, current_count, limit, request):
    """
    Throttled audit logging for rate limit violations.
    Logs only the first violation per consumer per hour to avoid flooding audit_log.
    Uses Redis to track whether violation already logged for this hour.
    """
    from services.customer_service.database import SessionLocal
    from services.shared.audit_logger import log_error_to_audit
    
    # Redis key to track if we've already logged for this hour
    audit_log_key = f"audit:ratelimit:{consumer_id}:{hour_bucket}"
    
    try:
        # Check if already logged for this hour (returns 1 if key exists)
        already_logged = redis_client.exists(audit_log_key)
        
        if not already_logged:
            # First violation this hour - log to audit
            db: Session = SessionLocal()
            try:
                error_resp = error_response(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    f"Rate limit exceeded: {limit} requests per hour. Current count: {current_count}"
                )
                log_error_to_audit(
                    db=db,
                    request=request,
                    entity="rate_limiting",
                    entity_id=str(consumer_id),
                    action="api_key_rate_limit_exceeded",
                    error_response=error_resp
                )
                db.commit()
                
                # Mark as logged for this hour (TTL = 1 hour)
                redis_client.setex(audit_log_key, 3600, "1")
                
            except Exception as audit_error:
                print(f"Failed to log rate limit violation to audit: {audit_error}")
            finally:
                db.close()
                
    except Exception as redis_error:
        # Redis failure - skip audit logging (already failing open on rate limiting)
        print(f"Redis error during audit logging check: {redis_error}")


def rate_limit_middleware(request: Request):
    """
    Rate limiting middleware for authenticated API key requests.
    Uses Redis to track request counts per consumer per minute.
    Fails open (allows request) if Redis unavailable.
    """
    from services.shared.redis_client import get_redis_client
    from services.customer_service.config import get_settings
    from datetime import datetime
    import math
    
    # Only apply to authenticated endpoints
    if not hasattr(request.state, "consumer_id"):
        return
    
    consumer_id = request.state.consumer_id
    settings = get_settings()
    
    # Get Redis client (may be None if unavailable)
    redis_client = get_redis_client()
    if not redis_client:
        # Fail-open: allow request if Redis unavailable
        return
    
    try:
        # Calculate current minute bucket
        current_timestamp = utcnow().timestamp()
        minute_bucket = math.floor(current_timestamp / 60)
        
        # Redis key format: ratelimit:consumer:{consumer_id}:{minute_bucket}
        redis_key = f"ratelimit:consumer:{consumer_id}:{minute_bucket}"
        
        # Increment counter atomically
        current_count = redis_client.incr(redis_key)
        
        # Set TTL on first increment
        if current_count == 1:
            redis_client.expire(redis_key, 60)  # 1 minute TTL
        
        # Check if limit exceeded
        limit = settings.rate_limit_api_key_per_minute
        if current_count > limit:
            # Calculate seconds until next minute
            next_minute_timestamp = (minute_bucket + 1) * 60
            retry_after = int(next_minute_timestamp - current_timestamp)
            
            # Throttled audit logging: log first 429 per consumer per minute
            _log_rate_limit_violation_once_per_hour(
                redis_client, 
                consumer_id, 
                minute_bucket, 
                current_count, 
                limit,
                request
            )
            
            error_resp = error_response(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Rate limit exceeded: {limit} requests per minute. Current count: {current_count}"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=error_resp,
                headers={"Retry-After": str(retry_after)}
            )
            
    except HTTPException:
        # Re-raise HTTPException (rate limit exceeded)
        raise
    except Exception as e:
        # Log Redis errors but fail-open
        print(f"Rate limiting error (fail-open): {e}")
        return
