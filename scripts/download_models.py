#!/usr/bin/env python3
"""Download the two ONNX models the service needs (CPU-only, ~38 MB total).

    python scripts/download_models.py            # skip existing files
    python scripts/download_models.py --force    # re-download

Both models come from the OpenCV Zoo and are Apache-2.0 licensed, which means
you can ship and resell this service without touching anyone's proprietary
weights or paying per-call licence fees.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODELS_DIR = ROOT / "models"

BASE_URL = "https://github.com/opencv/opencv_zoo/raw/main/models"

#: (filename, url, minimum plausible size in bytes)
MODELS: list[tuple[str, str, int]] = [
    (
        "face_detection_yunet_2023mar.onnx",
        f"{BASE_URL}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        100_000,
    ),
    (
        "face_recognition_sface_2021dec.onnx",
        f"{BASE_URL}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        10_000_000,
    ),
]


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "faceapi-model-downloader/1.0"})
    tmp = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        seen = 0
        while True:
            chunk = response.read(1 << 16)
            if not chunk:
                break
            handle.write(chunk)
            seen += len(chunk)
            if total:
                pct = seen / total * 100
                sys.stdout.write(f"\r    {pct:5.1f}%  {seen / 1_048_576:6.1f} / {total / 1_048_576:.1f} MB")
                sys.stdout.flush()
    if total:
        sys.stdout.write("\n")
    tmp.replace(destination)


def _validate(path: Path, minimum_size: int) -> str | None:
    """Return an error string, or None when the file looks usable."""
    size = path.stat().st_size
    if size < minimum_size:
        return f"file looks truncated ({size} bytes)"
    try:
        import cv2
    except ImportError:  # pragma: no cover - only when run without deps
        return None
    try:
        if "yunet" in path.name:
            cv2.FaceDetectorYN.create(str(path), "", (320, 320))
        else:
            cv2.FaceRecognizerSF.create(str(path), "")
    except cv2.error as exc:
        return f"OpenCV refused the model: {exc}"
    return None


def download_all(models_dir: Path | str = DEFAULT_MODELS_DIR, *, force: bool = False) -> list[tuple[str, Path, str]]:
    """Download every model.

    Returns a list of ``(name, path, status)`` where status is ``ok``,
    ``exists`` or an error message.
    """
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[str, Path, str]] = []

    for filename, url, minimum_size in MODELS:
        destination = models_dir / filename
        name = "YuNet detector" if "yunet" in filename else "SFace recognizer"

        if destination.exists() and not force:
            error = _validate(destination, minimum_size)
            if error is None:
                results.append((name, destination, "exists"))
                continue
            print(f"  existing {filename} is unusable ({error}); re-downloading")

        try:
            print(f"  downloading {name} …")
            _download(url, destination)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            results.append((name, destination, f"download failed: {exc}"))
            continue

        error = _validate(destination, minimum_size)
        results.append((name, destination, "ok" if error is None else error))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the ONNX face models")
    parser.add_argument("--models-dir", default=str(DEFAULT_MODELS_DIR))
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    args = parser.parse_args()

    results = download_all(args.models_dir, force=args.force)
    problems = 0
    for name, path, status in results:
        if status in ("ok", "exists"):
            print(f"  ✓ {name}: {path.name} ({path.stat().st_size / 1_048_576:.1f} MB) [{status}]")
        else:
            print(f"  ✗ {name}: {status}", file=sys.stderr)
            problems += 1
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
