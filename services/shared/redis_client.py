"""
Redis connection manager for rate limiting.
Provides connection pooling and error handling.
"""
import redis
import os
from typing import Optional
import logging

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """
    Get or create Redis client with connection pooling.
    Returns None if Redis unavailable (fail-open for rate limiting).
    """
    global _redis_client
    
    if _redis_client is not None:
        return _redis_client
    
    try:
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        
        _redis_client = redis.StrictRedis(
            host=redis_host,
            port=redis_port,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
            health_check_interval=30
        )
        
        # Test connection
        _redis_client.ping()
        logger.info(f"Redis connection established: {redis_host}:{redis_port}")
        return _redis_client
        
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        _redis_client = None
        return None


def close_redis_client():
    """Close Redis connection (cleanup on shutdown)."""
    global _redis_client
    if _redis_client:
        _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")
