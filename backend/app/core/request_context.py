import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_principal_id: ContextVar[str | None] = ContextVar("principal_id", default=None)
_account_id: ContextVar[str | None] = ContextVar("account_id", default=None)


def get_request_id() -> str:
    return _request_id.get()


def get_principal_id() -> str | None:
    return _principal_id.get()


def get_account_id() -> str | None:
    return _account_id.get()


def set_principal_context(*, principal_id: str | None, account_id: str | None) -> None:
    """Set once per request by an auth dependency (app.modules.identity), after
    the caller is authenticated. Read by the RLS session-var setter and by
    logging — never trust a client-supplied header for these.
    """
    _principal_id.set(principal_id)
    _account_id.set(account_id)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request_id (accepting an inbound X-Request-Id for correlation
    across the frontend/BFF boundary, else generating one) and echoes it back.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        token = _request_id.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id.reset(token)
        response.headers["x-request-id"] = request_id
        return response
