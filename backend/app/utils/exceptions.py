from fastapi import HTTPException, status
from typing import Any, Dict, Optional

class BiodataException(Exception):
    """Base exception class for biodata-assistant."""
    
    def __init__(self, message: str, error_code: Optional[str] = None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)

class DatabaseError(BiodataException):
    """Database operation error."""
    pass

class ExternalServiceError(BiodataException):
    """External service integration error."""
    pass

class ValidationError(BiodataException):
    """Data validation error."""
    pass

class NotFoundError(HTTPException):
    """Resource not found error."""
    
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} with identifier '{identifier}' not found"
        )

class ConflictError(HTTPException):
    """Resource conflict error."""
    
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=message
        )

class BadRequestError(HTTPException):
    """Bad request error."""
    
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

class InternalServerError(HTTPException):
    """Internal server error."""
    
    def __init__(self, message: str = "Internal server error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=message
        )
