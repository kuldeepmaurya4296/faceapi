"""Configuration and commercial plan definitions.

Every setting can be overridden with an environment variable prefixed with
``FACEAPI_`` (or via a ``.env`` file next to the project root), e.g.::

    FACEAPI_AUTH_ENABLED=false
    FACEAPI_ADMIN_TOKEN=super-secret
    FACEAPI_VERIFY_THRESHOLD=0.36
"""

from __future__ import annotations

import secrets
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class PlanLimits(BaseModel):
    """Commercial limits attached to a plan.

    ``monthly_quota = -1`` and ``rate_per_minute = -1`` mean "unlimited".
    ``price_usd_month`` / ``overage_per_1000_usd`` are only used by the
    invoicing summary endpoint, so resellers can bill their own customers.
    """

    name: str
    rate_per_minute: int
    monthly_quota: int
    max_upload_mb: int = 10
    max_faces_per_image: int = 50
    allow_collections: bool = True
    price_usd_month: float = 0.0
    overage_per_1000_usd: float = 0.0

    @property
    def unlimited_rate(self) -> bool:
        return self.rate_per_minute < 0

    @property
    def unlimited_quota(self) -> bool:
        return self.monthly_quota < 0


#: Out-of-the-box plans. Edit the prices freely — they are *your* prices.
PLANS: dict[str, PlanLimits] = {
    "personal": PlanLimits(
        name="personal",
        rate_per_minute=-1,
        monthly_quota=-1,
        max_upload_mb=25,
        max_faces_per_image=200,
        allow_collections=True,
        price_usd_month=0.0,
    ),
    "trial": PlanLimits(
        name="trial",
        rate_per_minute=10,
        monthly_quota=500,
        max_upload_mb=5,
        max_faces_per_image=20,
        allow_collections=False,
    ),
    "starter": PlanLimits(
        name="starter",
        rate_per_minute=60,
        monthly_quota=25_000,
        max_upload_mb=10,
        max_faces_per_image=50,
        allow_collections=True,
        price_usd_month=19.0,
        overage_per_1000_usd=0.60,
    ),
    "pro": PlanLimits(
        name="pro",
        rate_per_minute=300,
        monthly_quota=250_000,
        max_upload_mb=15,
        max_faces_per_image=100,
        allow_collections=True,
        price_usd_month=79.0,
        overage_per_1000_usd=0.35,
    ),
    "business": PlanLimits(
        name="business",
        rate_per_minute=1_200,
        monthly_quota=2_000_000,
        max_upload_mb=25,
        max_faces_per_image=200,
        allow_collections=True,
        price_usd_month=299.0,
        overage_per_1000_usd=0.15,
    ),
    "enterprise": PlanLimits(
        name="enterprise",
        rate_per_minute=-1,
        monthly_quota=-1,
        max_upload_mb=50,
        max_faces_per_image=500,
        allow_collections=True,
        price_usd_month=0.0,
        overage_per_1000_usd=0.0,
    ),
}

DEFAULT_PLAN = "starter"


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="FACEAPI_",
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- service identity -------------------------------------------------
    service_name: str = "Face API"
    public_base_url: str = "http://127.0.0.1:8000"
    docs_enabled: bool = True

    # -- auth -------------------------------------------------------------
    #: ``False`` turns this into a private/personal service: no API key needed
    #: at all, and requests get the unlimited ``personal`` plan.
    auth_enabled: bool = True
    #: Required to call ``/admin/*``. If unset it is generated and persisted to
    #: ``<data_dir>/admin_token.txt`` on first start.
    admin_token: str | None = None

    # -- storage ----------------------------------------------------------
    data_dir: Path = BASE_DIR / "data"
    models_dir: Path = BASE_DIR / "models"
    db_filename: str = "faceapi.db"

    # -- models -----------------------------------------------------------
    detect_model: str = "face_detection_yunet_2023mar.onnx"
    recog_model: str = "face_recognition_sface_2021dec.onnx"

    # -- detection tuning -------------------------------------------------
    #: Initial detector input size (the real size is set per image).
    detect_input_size: int = 320
    detect_score_threshold: float = 0.85
    detect_nms_threshold: float = 0.3
    detect_top_k: int = 5000
    #: Faces smaller than this (px, either side) are ignored.
    min_face_size: int = 16
    #: Images are downscaled so the longest side is at most this many pixels.
    max_image_side: int = 1600
    max_upload_mb: int = 10

    # -- recognition tuning ----------------------------------------------
    #: OpenCV's recommended cosine threshold for SFace is 0.363.
    verify_threshold: float = 0.363
    identify_threshold: float = 0.363
    identify_max_candidates: int = 5

    # -- limits -----------------------------------------------------------
    default_max_faces: int = 20
    max_embeddings_per_request: int = 20
    cors_origins: str = "*"

    # -- ops --------------------------------------------------------------
    log_level: str = "INFO"
    trust_proxy_headers: bool = False

    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return v.strip()

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def detect_model_path(self) -> Path:
        return self.models_dir / self.detect_model

    @property
    def recog_model_path(self) -> Path:
        return self.models_dir / self.recog_model

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() in ("", "*"):
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def plan(self, name: str) -> PlanLimits:
        return PLANS.get(name, PLANS[DEFAULT_PLAN])

    def load_or_create_admin_token(self) -> str:
        """Return the admin token, generating and persisting one if needed."""
        if self.admin_token:
            return self.admin_token
        token_file = self.data_dir / "admin_token.txt"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
            if token:
                self.admin_token = token
                return token
        token = secrets.token_urlsafe(32)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        token_file.write_text(token + "\n", encoding="utf-8")
        token_file.chmod(0o600)
        self.admin_token = token
        return token


_settings: Settings | None = None


def get_settings(refresh: bool = False) -> Settings:
    """Process-wide settings singleton."""
    global _settings
    if _settings is None or refresh:
        _settings = Settings()
    return _settings
