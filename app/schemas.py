"""Request/response schemas — this is the public API contract."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------- basics
class Box(BaseModel):
    x: int = Field(..., description="Left edge in pixels.")
    y: int = Field(..., description="Top edge in pixels.")
    width: int = Field(..., description="Box width in pixels.")
    height: int = Field(..., description="Box height in pixels.")


class NormalizedBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class Landmark(BaseModel):
    x: float
    y: float


class ImageInfo(BaseModel):
    width: int
    height: int
    format: str | None = None


class UsageInfo(BaseModel):
    """Token/plan accounting echoed on every response, so clients can self-throttle."""

    plan: str
    request_id: str | None = None
    processing_ms: float
    rate_limit_per_minute: int | None = None
    rate_limit_remaining: int | None = None
    monthly_quota: int | None = None
    month_usage: int | None = None
    faces_detected: int = 0


# ---------------------------------------------------------------- /v1/detect
class FaceDetection(BaseModel):
    index: int = Field(..., description="0 = largest face.")
    box: Box
    box_normalized: NormalizedBox
    score: float = Field(..., ge=0, le=1, description="Detector confidence.")
    landmarks: list[Landmark] | None = Field(
        default=None, description="Right eye, left eye, nose, right mouth, left mouth."
    )


class DetectResponse(BaseModel):
    image: ImageInfo
    face_count: int
    faces: list[FaceDetection]
    model: dict[str, str]
    usage: UsageInfo


# ----------------------------------------------------------------- /v1/embed
class FaceEmbedding(BaseModel):
    index: int
    box: Box
    score: float
    embedding: list[float] = Field(..., description="L2-normalised 128-d vector.")
    dim: int = 128
    aligned_face_base64: str | None = Field(
        default=None, description="112x112 aligned JPEG crop, base64 (only when requested)."
    )


class EmbedResponse(BaseModel):
    image: ImageInfo
    face_count: int
    faces: list[FaceEmbedding]
    model: dict[str, str]
    usage: UsageInfo


# ---------------------------------------------------------------- /v1/verify
class VerifyResponse(BaseModel):
    match: bool = Field(..., description="True when similarity >= threshold (same person).")
    similarity: float = Field(..., description="Cosine similarity in [-1, 1].")
    threshold: float
    faces_in_image1: int
    faces_in_image2: int
    #: Which detected face was used from each image (largest by default).
    face_index_image1: int
    face_index_image2: int
    model: dict[str, str]
    usage: UsageInfo


# --------------------------------------------------------------- /v1/compare
class CompareRequest(BaseModel):
    embedding1: Annotated[list[float], Field(min_length=8)]
    embedding2: Annotated[list[float], Field(min_length=8)]
    threshold: float | None = Field(default=None, ge=-1.0, le=1.0)

    @field_validator("embedding1", "embedding2")
    @classmethod
    def _check_dim(cls, v: list[float]) -> list[float]:
        if len(v) != 128:
            raise ValueError(f"Embedding must have exactly 128 values, got {len(v)}.")
        return v


class CompareResponse(BaseModel):
    match: bool
    similarity: float
    threshold: float
    dim: int = 128


# -------------------------------------------------------------- /v1/identify
class IdentifyMatch(BaseModel):
    face_id: str
    external_id: str | None = None
    similarity: float
    metadata: dict[str, Any] | None = None
    created_at: str | None = None


class IdentifyResponse(BaseModel):
    collection: str
    match: bool
    threshold: float
    best_match: IdentifyMatch | None = None
    candidates: list[IdentifyMatch]
    faces_in_probe: int
    gallery_size: int
    model: dict[str, str]
    usage: UsageInfo
    is_live: bool = True
    liveness_score: float = 1.0
    spoof_reason: str | None = None


# ----------------------------------------------------------- /v1/collections
class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    description: str | None = Field(default=None, max_length=500)


class CollectionInfo(BaseModel):
    name: str
    description: str | None = None
    face_count: int
    created_at: str


class CollectionListResponse(BaseModel):
    collections: list[CollectionInfo]
    count: int


class FaceCreateResponse(BaseModel):
    collection: str
    face_id: str
    external_id: str | None = None
    det_score: float | None = None
    box: Box | None = None
    metadata: dict[str, Any] | None = None
    created_at: str


class FaceListResponse(BaseModel):
    collection: str
    faces: list[FaceCreateResponse]
    count: int
    limit: int
    offset: int


# -------------------------------------------------------------------- account
class MeResponse(BaseModel):
    key: dict[str, Any]
    usage: dict[str, Any]


# ---------------------------------------------------------------------- admin
class AdminKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Customer or app name.")
    plan: str = Field(default="starter", description="trial | starter | pro | business | enterprise | personal")
    email: str | None = Field(default=None, max_length=200)
    expires_at: str | None = Field(default=None, description="ISO-8601 UTC timestamp.")
    monthly_quota: int | None = Field(default=None, description="Override the plan quota.")
    rate_per_minute: int | None = Field(default=None, description="Override the plan rate limit.")
    note: str | None = Field(default=None, max_length=500)


class AdminKeyCreated(BaseModel):
    """Returned **once** on creation — the secret is never retrievable again."""

    key_id: str
    api_key: str
    name: str
    plan: str
    monthly_quota: int | None
    rate_limit_per_minute: int | None
    created_at: str
    warning: str = "Store this key now. It cannot be recovered later."


class AdminKeyUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    plan: str | None = None
    active: bool | None = None
    monthly_quota: int | None = None
    rate_per_minute: int | None = None
    note: str | None = None
    expires_at: str | None = None


class AdminKeyInfo(BaseModel):
    key_id: str
    key_prefix: str
    name: str
    email: str | None = None
    plan: str
    active: bool
    monthly_quota: int | None = None
    rate_per_minute: int | None = None
    created_at: str
    expires_at: str | None = None
    last_used_at: str | None = None
    revoked_at: str | None = None
    note: str | None = None
    month_usage: int | None = None


class AdminKeyListResponse(BaseModel):
    keys: list[AdminKeyInfo]
    count: int


class InvoiceSummaryResponse(BaseModel):
    month: str
    lines: list[dict[str, Any]]
    totals: dict[str, Any]


# ------------------------------------------------------------------ meta/info
class PlanInfo(BaseModel):
    name: str
    rate_limit_per_minute: int | None
    monthly_quota: int | None
    max_upload_mb: int
    max_faces_per_image: int
    collections: bool
    price_usd_month: float
    overage_per_1000_usd: float


class ServiceInfo(BaseModel):
    service: str
    version: str
    auth_mode: Literal["api_key", "personal"]
    endpoints: list[str]
    models: dict[str, str]
    plans: list[PlanInfo]
    docs_url: str | None = None
    openapi_url: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
