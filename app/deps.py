"""Shared FastAPI dependencies and small request helpers.

Routes are deliberately **synchronous** (``def``): FastAPI then runs them in a
worker thread, which is exactly where CPU-bound OpenCV inference belongs. The
uploaded file is already buffered by the multipart parser, so reading it from
``UploadFile.file`` is a cheap local read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, File, Request, UploadFile

from .config import PlanLimits, Settings
from .engine import FaceEngine
from .errors import AuthError, InvalidImage, NoFaceFound
from .imaging import decode_image, sniff_format
from .schemas import Box, ImageInfo, Landmark, NormalizedBox, UsageInfo
from .security import (
    KeyContext,
    RateLimiter,
    admin_token_from_request,
    enforce_quota,
    enforce_rate_limit,
    extract_api_key,
    parse_api_key,
    personal_context,
    verify_admin_token,
)
from .storage import Storage


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_engine(request: Request) -> FaceEngine:
    return request.app.state.engine


def get_storage(request: Request) -> Storage:
    return request.app.state.storage


def get_limiter(request: Request) -> RateLimiter:
    return request.app.state.limiter


@dataclass(slots=True)
class CallContext:
    """Authenticated caller + accounting data for this request."""

    key: KeyContext
    settings: Settings
    storage: Storage
    rate_headers: dict[str, str] = field(default_factory=dict)
    month_usage: int = 0
    rate_remaining: int = -1
    request_id: str | None = None

    @property
    def owner(self) -> str:
        return self.key.owner

    @property
    def plan(self) -> PlanLimits:
        return self.key.plan

    @property
    def max_upload_bytes(self) -> int:
        return self.plan.max_upload_mb * 1024 * 1024

    def usage(self, *, processing_ms: float, faces: int = 0) -> UsageInfo:
        return UsageInfo(
            plan=self.key.plan.name,
            request_id=self.request_id,
            processing_ms=round(processing_ms, 2),
            rate_limit_per_minute=None if self.key.rate_unlimited else self.key.effective_rate,
            rate_limit_remaining=None if self.rate_remaining < 0 else self.rate_remaining,
            monthly_quota=None if self.key.quota_unlimited else self.key.effective_quota,
            month_usage=self.month_usage + 1,
            faces_detected=faces,
        )


def authenticate(request: Request) -> CallContext:
    """Auth + quota + rate-limit gate applied to every ``/v1/*`` endpoint."""
    settings: Settings = request.app.state.settings
    storage: Storage = request.app.state.storage
    limiter: RateLimiter = request.app.state.limiter

    request_id = getattr(request.state, "request_id", None)

    secret = extract_api_key(request)
    if secret:
        key = parse_api_key(settings, storage, secret)
        month_usage = enforce_quota(key, storage)
        remaining, headers = enforce_rate_limit(limiter, key)
        request.state.key_context = key
        return CallContext(
            key=key,
            settings=settings,
            storage=storage,
            rate_headers=headers,
            month_usage=month_usage,
            rate_remaining=remaining,
            request_id=request_id,
        )

    # Check if request is explicitly internal (e.g. direct call with X-Internal header from HRMS) or auth disabled
    is_internal = request.headers.get("x-internal") == "true"
    if is_internal or not settings.auth_enabled:
        key = personal_context(settings)
        request.state.key_context = key
        return CallContext(
            key=key, settings=settings, storage=storage, month_usage=0, request_id=request_id
        )

    raise AuthError(
        "Missing API key. Send your API key in the 'X-API-Key' header "
        "(or 'Authorization: Bearer <key>'). Generate your key at https://hrms.fakhriitservices.com/faceapi",
        code="missing_api_key",
    )


def require_admin(request: Request) -> None:
    """Gate for ``/admin/*`` — uses the admin token, never a customer key."""
    settings = request.app.state.settings
    verify_admin_token(settings, admin_token_from_request(request))


CurrentCall = Annotated[CallContext, Depends(authenticate)]
#: Router-level guard for ``/admin/*`` — use as ``dependencies=[AdminGuard]``.
AdminGuard = Depends(require_admin)
UploadedImage = Annotated[UploadFile, File(description="JPEG, PNG, WebP, BMP or TIFF image")]


# ------------------------------------------------------------------- helpers
def read_image_upload(file: UploadFile | None, call: CallContext) -> tuple["object", ImageInfo]:
    """Read + decode an uploaded image, enforcing the plan's size limit.

    Returns ``(bgr_ndarray, ImageInfo)``.
    """
    if file is None or not file.filename and not file.file:
        raise InvalidImage("No image uploaded. Send it as multipart/form-data field 'image'.")
    raw = file.file.read()
    fmt = sniff_format(raw) if raw else None
    image = decode_image(raw, max_side=call.settings.max_image_side, max_bytes=call.max_upload_bytes)
    height, width = image.shape[:2]
    return image, ImageInfo(width=width, height=height, format=fmt)


def embed_upload(
    file: UploadFile | None,
    call: CallContext,
    engine: FaceEngine,
    *,
    face_index: int = 0,
    face_mode: str = "largest",
    max_faces: int | None = None,
):
    """Decode an upload and return ``(image, image_info, face, embedding, all_faces)``.

    ``face_mode`` is ``largest`` (default) or ``index``. Raises
    :class:`NoFaceFound` when nothing is detected.
    """
    image, info = read_image_upload(file, call)
    limit = max_faces if max_faces is not None else call.plan.max_faces_per_image
    faces = engine.detect(image, max_faces=limit)
    if not faces:
        raise NoFaceFound("No face detected in the uploaded image.", code="no_face_found")

    if face_mode == "index":
        if face_index < 0 or face_index >= len(faces):
            raise NoFaceFound(
                f"face_index {face_index} is out of range; {len(faces)} face(s) detected.",
                code="face_index_out_of_range",
            )
        face = faces[face_index]
    else:
        face = faces[0]

    embedding = engine.embed(image, face)
    return image, info, face, embedding, faces


def to_box(x: int, y: int, width: int, height: int, image_width: int, image_height: int):
    """Build pixel + normalised boxes."""
    return Box(x=x, y=y, width=width, height=height), NormalizedBox(
        x=round(x / image_width, 6) if image_width else 0.0,
        y=round(y / image_height, 6) if image_height else 0.0,
        width=round(width / image_width, 6) if image_width else 0.0,
        height=round(height / image_height, 6) if image_height else 0.0,
    )


def to_landmarks(face) -> list[Landmark]:
    return [Landmark(x=round(float(px), 2), y=round(float(py), 2)) for px, py in face.landmarks]
