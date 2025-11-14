# Shared Utility Functions
from datetime import datetime, timezone


def utcnow() -> datetime:
    """
    Get current UTC datetime with timezone info.
    
    Replacement for deprecated datetime.utcnow() (Python 3.12+).
    
    Returns:
        datetime: Current UTC time with timezone.
    """
    return datetime.now(timezone.utc)
