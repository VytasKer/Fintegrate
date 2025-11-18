from typing import Any, Dict
from fastapi import status as http_status


def create_detail(status_code: int, description: str = "Success") -> Dict[str, str]:
    """
    Create standardized detail object.

    Args:
        status_code: HTTP status code
        description: Description of the status (default "Success" for successful calls)

    Returns:
        Dictionary with status_code, status_name, status_description
    """
    status_names = {
        200: "OK",
        201: "CREATED",
        204: "NO_CONTENT",
        302: "FOUND",
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "UNPROCESSABLE_ENTITY",
        500: "INTERNAL_SERVER_ERROR",
        501: "NOT_IMPLEMENTED",
    }

    # Ensure status_code is returned as a string to satisfy Pydantic response model validation
    return {
        "status_code": str(status_code),
        "status_name": status_names.get(status_code, "UNKNOWN"),
        "status_description": description,
    }


def success_response(data: Any, status_code: int = 200) -> Dict[str, Any]:
    """
    Create standardized success response.

    Args:
        data: Response data object
        status_code: HTTP status code (default 200)

    Returns:
        Standardized response with data and detail
    """
    return {"data": data, "detail": create_detail(status_code, "Success")}


def error_response(status_code: int, description: str) -> Dict[str, Any]:
    """
    Create standardized error response.

    Args:
        status_code: HTTP error status code
        description: Detailed error description

    Returns:
        Standardized error response with empty data and detail
    """
    return {"data": {}, "detail": create_detail(status_code, description)}
