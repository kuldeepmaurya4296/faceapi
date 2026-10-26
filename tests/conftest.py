"""Shared pytest fixtures.

The suite needs the ONNX models (``python scripts/download_models.py``) and, for
the full-stack tests, the ``fastapi``/``httpx`` dev dependencies.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import cv2
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.engine import FaceEngine
from app.main import create_app

TESTS_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parent.parent
ASSETS = TESTS_DIR / "assets"
MODELS = ROOT / "models"

ADMIN_TOKEN = "test-admin-token"


def pytest_configure(config: pytest.Config) -> None:
    missing = [
        name
        for name in ("face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx")
        if not (MODELS / name).exists()
    ]
    if missing:
        pytest.exit(
            "ONNX models are missing: "
            + ", ".join(missing)
            + "\nRun: python scripts/download_models.py",
            returncode=2,
        )
    for asset in ("person_a_1.jpg", "person_b_1.jpg", "no_face.png"):
        if not (ASSETS / asset).exists():
            pytest.exit(f"test asset missing: {ASSETS / asset}", returncode=2)


@pytest.fixture(scope="session", autouse=True)
def variant_asset() -> Path:
    """Create `person_a_2.jpg` — the same person in a visibly different photo.

    Generated at test time so the repository only needs one source portrait.
    """
    destination = ASSETS / "person_a_2.jpg"
    if destination.exists():
        return destination
    source = ASSETS / "person_a_1.jpg"
    image = cv2.imread(str(source))
    assert image is not None, f"cannot read {source}"
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), 7, 0.93)
    variant = cv2.warpAffine(image, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)
    variant = cv2.convertScaleAbs(variant, alpha=1.10, beta=10)
    cv2.imwrite(str(destination), variant, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    return destination


@pytest.fixture(scope="session")
def assets() -> dict[str, bytes]:
    return {
        "person_a_1": (ASSETS / "person_a_1.jpg").read_bytes(),
        "person_a_2": (ASSETS / "person_a_2.jpg").read_bytes(),
        "person_b_1": (ASSETS / "person_b_1.jpg").read_bytes(),
        "no_face": (ASSETS / "no_face.png").read_bytes(),
    }


@pytest.fixture(scope="session")
def engine() -> FaceEngine:
    return FaceEngine(
        models_dir=MODELS,
        detect_model="face_detection_yunet_2023mar.onnx",
        recog_model="face_recognition_sface_2021dec.onnx",
    )


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "data_dir": tmp_path,
        "models_dir": MODELS,
        "admin_token": ADMIN_TOKEN,
        "log_level": "WARNING",
        "docs_enabled": True,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(scope="session")
def personal_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """Auth disabled — the 'personal use' deployment."""
    data = tmp_path_factory.mktemp("personal-data")
    return _settings(data, auth_enabled=False)


@pytest.fixture(scope="session")
def personal_client(personal_settings: Settings):
    app = create_app(personal_settings)
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session")
def commercial_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """Auth enabled — the 'sell it as an API' deployment."""
    data = tmp_path_factory.mktemp("commercial-data")
    return _settings(data, auth_enabled=True)


@pytest.fixture(scope="session")
def commercial_client(commercial_settings: Settings):
    app = create_app(commercial_settings)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": ADMIN_TOKEN}


@pytest.fixture
def make_key(commercial_client: TestClient, admin_headers: dict[str, str]):
    """Issue a fresh API key (with optional limit overrides) and return it."""

    def _make(name: str = "test-customer", plan: str = "starter", **overrides) -> dict:
        payload = {"name": name, "plan": plan, **overrides}
        response = commercial_client.post("/admin/keys", json=payload, headers=admin_headers)
        assert response.status_code == 200, response.text
        return response.json()

    return _make


@pytest.fixture
def key_headers():
    def _headers(secret: str) -> dict[str, str]:
        return {"X-API-Key": secret}

    return _headers


@pytest.fixture(scope="session")
def tmp_copy_of_assets(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A throwaway directory for tests that need to write files."""
    return tmp_path_factory.mktemp("scratch")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:  # pragma: no cover
    shutil.rmtree(ROOT / ".pytest_cache", ignore_errors=True)
