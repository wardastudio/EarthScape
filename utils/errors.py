from __future__ import annotations

from typing import Any, Dict, Optional


class AppError(Exception):
    status_code: int = 500
    error_type: str = "internal_error"

    def __init__(
        self,
        message: str = "An unexpected error occurred",
        status_code: Optional[int] = None,
        error_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if error_type is not None:
            self.error_type = error_type
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "error": self.error_type,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


class ValidationError(AppError):
    status_code = 422
    error_type = "validation_error"


class AuthenticationError(AppError):
    status_code = 401
    error_type = "authentication_error"


class AuthorizationError(AppError):
    status_code = 403
    error_type = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    error_type = "not_found"


class ConflictError(AppError):
    status_code = 409
    error_type = "conflict"


class RateLimitError(AppError):
    status_code = 429
    error_type = "too_many_requests"


class DatabaseError(AppError):
    status_code = 500
    error_type = "database_error"


class ExternalAPIError(AppError):
    status_code = 502
    error_type = "external_api_error"


class MLModelError(AppError):
    status_code = 500
    error_type = "ml_model_error"
