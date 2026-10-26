"""Face detection + recognition engine.

Two small ONNX models do the real work, both CPU-only and both from the
OpenCV Zoo (Apache-2.0), which makes the service cheap to host and safe to
resell:

* **YuNet** (``face_detection_yunet_2023mar.onnx``) — detects faces and returns
  a bounding box, five landmarks and a confidence score.
* **SFace** (``face_recognition_sface_2021dec.onnx``) — aligns a detected face
  and produces a 128-d embedding whose cosine distance decides identity.

``cv2.FaceDetectorYN`` / ``cv2.FaceRecognizerSF`` are **not** thread-safe, so
every call into them is serialised behind one lock. CPU inference on a
1600-px image is a few tens of milliseconds, so a single worker still serves
hundreds of requests per minute; scale out with more workers/replicas.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .errors import EngineUnavailable

EMBEDDING_SIZE = 128


@dataclass(slots=True)
class DetectedFace:
    """One detected face, in the coordinate space of the submitted image."""

    index: int
    x: int
    y: int
    width: int
    height: int
    score: float
    landmarks: np.ndarray = field(repr=False)  # shape (5, 2) float32

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    @property
    def area(self) -> int:
        return self.width * self.height

    def as_row(self, image_shape: tuple[int, ...]) -> np.ndarray:
        """Row layout expected by ``FaceRecognizerSF.alignCrop`` (1, 15)."""
        row = np.concatenate(
            [
                np.array([self.x, self.y, self.width, self.height], dtype=np.float32),
                self.landmarks.astype(np.float32).ravel(),
                np.array([self.score], dtype=np.float32),
            ]
        )
        return row.reshape(1, 15)


class FaceEngine:
    """Thin, thread-safe wrapper around the OpenCV face models."""

    def __init__(
        self,
        *,
        models_dir: Path,
        detect_model: str,
        recog_model: str,
        input_size: int = 320,
        score_threshold: float = 0.85,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
        min_face_size: int = 16,
    ) -> None:
        self.detect_model_path = Path(models_dir) / detect_model
        self.recog_model_path = Path(models_dir) / recog_model
        self.min_face_size = min_face_size

        missing = [p for p in (self.detect_model_path, self.recog_model_path) if not p.exists()]
        if missing:
            raise EngineUnavailable(
                "Model file(s) missing: "
                + ", ".join(str(p) for p in missing)
                + ". Run `python scripts/download_models.py` first.",
                status_code=503,
            )

        self._lock = threading.RLock()
        try:
            self._detector = cv2.FaceDetectorYN.create(
                str(self.detect_model_path),
                "",
                (input_size, input_size),
                score_threshold,
                nms_threshold,
                top_k,
            )
            self._recognizer = cv2.FaceRecognizerSF.create(str(self.recog_model_path), "")
        except cv2.error as exc:  # pragma: no cover - model/cv2 mismatch
            raise EngineUnavailable(f"Could not load ONNX models: {exc}", status_code=503) from exc

        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold

    # ------------------------------------------------------------------ info
    @property
    def model_names(self) -> dict[str, str]:
        return {
            "detector": self.detect_model_path.name,
            "recognizer": self.recog_model_path.name,
        }

    @property
    def backend(self) -> dict[str, str]:
        return {
            "detector": f"OpenCV YuNet ({cv2.__version__})",
            "recognizer": f"OpenCV SFace ({cv2.__version__})",
            "device": "cpu",
        }

    # -------------------------------------------------------------- detection
    def detect(
        self,
        image: np.ndarray,
        *,
        max_faces: int | None = None,
        score_threshold: float | None = None,
    ) -> list[DetectedFace]:
        """Detect faces, largest first."""
        height, width = image.shape[:2]
        with self._lock:
            self._detector.setInputSize((width, height))
            if score_threshold is not None and score_threshold != self.score_threshold:
                self._detector.setScoreThreshold(float(score_threshold))
                _, raw = self._detector.detect(image)
                self._detector.setScoreThreshold(float(self.score_threshold))
            else:
                _, raw = self._detector.detect(image)

        faces: list[DetectedFace] = []
        if raw is None:
            return faces

        for row in np.asarray(raw, dtype=np.float32):
            x, y, w, h = (int(round(float(v))) for v in row[:4])
            x2, y2 = x + w, y + h
            # Clamp to the image bounds.
            x, y = max(0, x), max(0, y)
            x2, y2 = min(width, x2), min(height, y2)
            w, h = x2 - x, y2 - y
            if w < self.min_face_size or h < self.min_face_size:
                continue
            faces.append(
                DetectedFace(
                    index=0,  # assigned after sorting
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                    score=float(row[14]),
                    landmarks=np.asarray(row[4:14], dtype=np.float32).reshape(5, 2),
                )
            )

        faces.sort(key=lambda f: f.area, reverse=True)
        if max_faces is not None and max_faces >= 0:
            faces = faces[:max_faces]
        for i, face in enumerate(faces):
            face.index = i
        return faces

    # ------------------------------------------------------------ recognition
    def align(self, image: np.ndarray, face: DetectedFace) -> np.ndarray:
        """Return the 112x112 aligned face crop used for recognition."""
        with self._lock:
            aligned = self._recognizer.alignCrop(image, face.as_row(image.shape))
        if aligned is None or aligned.size == 0:  # pragma: no cover - defensive
            raise EngineUnavailable("Face alignment failed.", status_code=500)
        return aligned

    def embed(self, image: np.ndarray, face: DetectedFace) -> np.ndarray:
        """Return an L2-normalised 128-d embedding for one detected face."""
        aligned = self.align(image, face)
        with self._lock:
            feature = self._recognizer.feature(aligned)
        vector = np.asarray(feature, dtype=np.float32).ravel()
        norm = float(np.linalg.norm(vector))
        if norm <= 0:  # pragma: no cover - defensive
            raise EngineUnavailable("Empty face embedding.", status_code=500)
        return vector / norm

    def detect_and_embed(
        self,
        image: np.ndarray,
        *,
        max_faces: int | None = None,
        largest_only: bool = False,
    ) -> list[tuple[DetectedFace, np.ndarray]]:
        faces = self.detect(image, max_faces=max_faces)
        if largest_only and faces:
            faces = faces[:1]
        return [(face, self.embed(image, face)) for face in faces]

    @staticmethod
    def similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity of two (already normalised) embeddings."""
        a = np.asarray(a, dtype=np.float32).ravel()
        b = np.asarray(b, dtype=np.float32).ravel()
        if a.shape != b.shape:
            raise ValueError(f"Embedding size mismatch: {a.shape} vs {b.shape}")
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom <= 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    def is_match(self, similarity: float, threshold: float) -> bool:
        return similarity >= threshold
