"""Typed errors and uniform JSON error responses.

Every failure returns the same envelope::

    {"error": {"code": "invalid_image", "message": "...", "request_id": "..."}}
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class FaceAPIError(Exception):
    """Base class for expected, client-facing failures."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class InvalidImage(FaceAPIError):
    status_code = 422
    code = "invalid_image"


class NoFaceFound(FaceAPIError):
    status_code = 422
    code = "no_face_found"


class AuthError(FaceAPIError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class PlanError(FaceAPIError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "plan_restricted"


class QuotaExceeded(FaceAPIError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "quota_exceeded"


class RateLimited(FaceAPIError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class NotFound(FaceAPIError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class Conflict(FaceAPIError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class EngineUnavailable(FaceAPIError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "engine_unavailable"


def _envelope(request: Request, code: str, message: str, extra: dict | None = None) -> dict:
    payload = {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", None),
        }
    }
    if extra:
        payload["error"].update(extra)
    return payload


def install_error_handlers(app: FastAPI) -> None:
    """Register handlers so *all* errors share one JSON shape."""

    @app.exception_handler(FaceAPIError)
    async def _faceapi_error(request: Request, exc: FaceAPIError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(request, exc.code, exc.message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        message = f"{loc}: {first.get('msg', 'invalid request')}" if loc else "invalid request"
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope(request, "validation_error", message),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(request, f"http_{exc.status_code}", str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # pragma: no cover - safety net
        request.app.state.logger.exception("unhandled error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(request, "internal_error", "internal server error"),
        )
