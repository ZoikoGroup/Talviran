"""Canonical error envelope and exception handling (API-001).

Every error response takes the shape:
    {"error": {code, message, request_id, retryable, retry_after_seconds, details}}

The status-code mapping below is a first-draft default (API-001 itself is not
yet an approved/signed contract) — confirm against the ratified OpenAPI spec
once API-001 is signed off, and update ERROR_STATUS in one place if it moves.
"""

from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import get_request_id


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    DATA_DELAYED = "DATA_DELAYED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    RIGHTS_RESTRICTED = "RIGHTS_RESTRICTED"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    JOB_FAILED = "JOB_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


ERROR_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.UNAUTHENTICATED: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.FORBIDDEN: status.HTTP_403_FORBIDDEN,
    ErrorCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.CONFLICT: status.HTTP_409_CONFLICT,
    ErrorCode.PRECONDITION_FAILED: status.HTTP_412_PRECONDITION_FAILED,
    ErrorCode.RATE_LIMITED: status.HTTP_429_TOO_MANY_REQUESTS,
    ErrorCode.DATA_DELAYED: status.HTTP_200_OK,
    ErrorCode.DATA_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
    ErrorCode.RIGHTS_RESTRICTED: status.HTTP_403_FORBIDDEN,
    ErrorCode.CAPABILITY_UNAVAILABLE: status.HTTP_403_FORBIDDEN,
    ErrorCode.POLICY_BLOCKED: status.HTTP_403_FORBIDDEN,
    ErrorCode.JOB_FAILED: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCode.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
}

_RETRYABLE = {ErrorCode.RATE_LIMITED, ErrorCode.DATA_UNAVAILABLE, ErrorCode.INTERNAL_ERROR}

# Reverse mapping for wrapping framework-raised HTTPExceptions (404 on an
# unmatched route, 405 Method Not Allowed, etc.) that never pass through
# TalvrinAPIError — explicit rather than derived from ERROR_STATUS, since
# several ErrorCodes share the same status (e.g. 403) and an inverted dict
# would pick one arbitrarily.
_STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    412: ErrorCode.PRECONDITION_FAILED,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
}


def _code_for_status(status_code: int) -> ErrorCode:
    if status_code in _STATUS_TO_CODE:
        return _STATUS_TO_CODE[status_code]
    return ErrorCode.INTERNAL_ERROR if status_code >= 500 else ErrorCode.VALIDATION_ERROR


class TalvrinAPIError(Exception):
    """Raise this anywhere in the request path to produce a canonical envelope."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retry_after_seconds: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        self.details = details
        super().__init__(message)

    def to_body(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "request_id": get_request_id(),
                "retryable": self.code in _RETRYABLE,
                "retry_after_seconds": self.retry_after_seconds,
                "details": self.details or {},
            }
        }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TalvrinAPIError)
    async def _talvrin_error(_: Request, exc: TalvrinAPIError) -> JSONResponse:
        return JSONResponse(status_code=ERROR_STATUS[exc.code], content=exc.to_body())

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Covers framework-raised HTTPExceptions our own code never
        # constructs directly — an unmatched route (404), a route matched
        # with the wrong HTTP method (405), etc. Uses exc.status_code as the
        # actual response status (not ERROR_STATUS[code]) since not every
        # raw status (405) has a corresponding ErrorCode/status pairing.
        wrapped = TalvrinAPIError(
            _code_for_status(exc.status_code),
            str(exc.detail) if exc.detail else "Request failed.",
        )
        return JSONResponse(status_code=exc.status_code, content=wrapped.to_body())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        wrapped = TalvrinAPIError(
            ErrorCode.VALIDATION_ERROR,
            "Request failed validation.",
            details={"errors": exc.errors()},
        )
        return JSONResponse(status_code=ERROR_STATUS[wrapped.code], content=wrapped.to_body())

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        wrapped = TalvrinAPIError(ErrorCode.INTERNAL_ERROR, "An internal error occurred.")
        return JSONResponse(status_code=ERROR_STATUS[wrapped.code], content=wrapped.to_body())
