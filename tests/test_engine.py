"""Engine-level tests: detection accuracy, embeddings, thresholds, thread safety."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

from app.engine import EMBEDDING_SIZE, FaceEngine
from app.errors import InvalidImage
from app.imaging import decode_image

THRESHOLD = 0.363


def _image(path: Path) -> np.ndarray:
    return decode_image(path.read_bytes(), max_side=1600, max_bytes=32 * 1024 * 1024)


@pytest.fixture(scope="module")
def images() -> dict[str, np.ndarray]:
    assets = Path(__file__).resolve().parent / "assets"
    return {
        "a1": _image(assets / "person_a_1.jpg"),
        "a2": _image(assets / "person_a_2.jpg"),
        "b1": _image(assets / "person_b_1.jpg"),
        "none": _image(assets / "no_face.png"),
    }


# ------------------------------------------------------------------ detection
def test_detects_exactly_one_face_in_portrait(engine: FaceEngine, images):
    faces = engine.detect(images["a1"])
    assert len(faces) == 1
    face = faces[0]
    assert 0.8 <= face.score <= 1.0
    assert face.width > 40 and face.height > 40


def test_box_is_inside_the_image(engine: FaceEngine, images):
    image = images["a1"]
    height, width = image.shape[:2]
    for face in engine.detect(image):
        assert 0 <= face.x < width
        assert 0 <= face.y < height
        assert face.x + face.width <= width
        assert face.y + face.height <= height


def test_landmarks_have_five_points(engine: FaceEngine, images):
    face = engine.detect(images["a1"])[0]
    assert face.landmarks.shape == (5, 2)
    # Eyes sit above the mouth.
    eye_y = face.landmarks[:2, 1].mean()
    mouth_y = face.landmarks[3:, 1].mean()
    assert eye_y < mouth_y


def test_no_faces_in_non_portrait_image(engine: FaceEngine, images):
    assert engine.detect(images["none"]) == []


def test_max_faces_limits_and_indexes(engine: FaceEngine, images):
    faces = engine.detect(images["a1"], max_faces=1)
    assert len(faces) == 1
    assert faces[0].index == 0


def test_faces_are_sorted_largest_first(engine: FaceEngine, images):
    faces = engine.detect(images["a1"])
    areas = [face.area for face in faces]
    assert areas == sorted(areas, reverse=True)


# ---------------------------------------------------------------- recognition
def test_embedding_is_normalised_128d(engine: FaceEngine, images):
    face = engine.detect(images["a1"])[0]
    vector = engine.embed(images["a1"], face)
    assert vector.shape == (EMBEDDING_SIZE,)
    assert vector.dtype == np.float32
    assert np.isclose(np.linalg.norm(vector), 1.0, atol=1e-5)


def test_identity_similarity_is_one(engine: FaceEngine, images):
    face = engine.detect(images["a1"])[0]
    vector = engine.embed(images["a1"], face)
    assert np.isclose(engine.similarity(vector, vector), 1.0, atol=1e-6)


def test_same_person_different_photo_matches(engine: FaceEngine, images):
    similarity = _similarity(engine, images["a1"], images["a2"])
    assert similarity > THRESHOLD, f"expected a match, got {similarity:.4f}"


def test_different_people_do_not_match(engine: FaceEngine, images):
    similarity = _similarity(engine, images["a1"], images["b1"])
    assert similarity < THRESHOLD, f"expected no match, got {similarity:.4f}"


def test_similarity_rejects_shape_mismatch(engine: FaceEngine):
    with pytest.raises(ValueError):
        engine.similarity(np.zeros(128, dtype=np.float32), np.zeros(64, dtype=np.float32))


def test_detect_and_embed_largest_only(engine: FaceEngine, images):
    pairs = engine.detect_and_embed(images["a1"], largest_only=True)
    assert len(pairs) == 1
    face, vector = pairs[0]
    assert face.index == 0
    assert vector.shape == (128,)


# --------------------------------------------------------------- robustness
def test_detector_is_thread_safe(engine: FaceEngine, images):
    """The OpenCV detector is not thread-safe; the engine serialises access."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: len(engine.detect(images["a1"])), range(16)))
    assert results == [1] * 16


def test_engine_reports_its_models(engine: FaceEngine):
    names = engine.model_names
    assert names["detector"].endswith(".onnx")
    assert names["recognizer"].endswith(".onnx")
    assert engine.backend["device"] == "cpu"


# ------------------------------------------------------------------- imaging
def test_decode_rejects_garbage():
    with pytest.raises(InvalidImage):
        decode_image(b"this is definitely not an image", max_side=1600, max_bytes=1024 * 1024)


def test_decode_rejects_empty():
    with pytest.raises(InvalidImage):
        decode_image(b"", max_side=1600, max_bytes=1024 * 1024)


def test_decode_enforces_size_limit(assets):
    with pytest.raises(InvalidImage) as excinfo:
        decode_image(assets["person_a_1"], max_side=1600, max_bytes=128)
    assert "too large" in str(excinfo.value).lower()


def test_decode_downscales_large_images(assets):
    image = decode_image(assets["person_a_1"], max_side=200, max_bytes=32 * 1024 * 1024)
    assert max(image.shape[:2]) <= 200


def _similarity(engine: FaceEngine, first: np.ndarray, second: np.ndarray) -> float:
    face_a = engine.detect(first)[0]
    face_b = engine.detect(second)[0]
    return engine.similarity(engine.embed(first, face_a), engine.embed(second, face_b))
