"""Image decoding / encoding helpers."""

from __future__ import annotations

import base64

import cv2
import numpy as np

from .errors import InvalidImage

#: Accepted by ``cv2.imdecode``. Rejecting everything else keeps the API safe
#: from exotic decoders.
_IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"BM", "bmp"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
)


def sniff_format(data: bytes) -> str:
    """Best-effort format detection (WebP needs a RIFF/WEBP check)."""
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    for magic, name in _IMAGE_MAGIC:
        if data.startswith(magic):
            return name
    return "unknown"


def decode_image(data: bytes, *, max_side: int, max_bytes: int) -> np.ndarray:
    """Decode raw upload bytes into a BGR ``uint8`` array.

    Raises :class:`InvalidImage` for empty/oversized/undecodable payloads.
    """
    if not data:
        raise InvalidImage("Uploaded file is empty.")
    if max_bytes and len(data) > max_bytes:
        raise InvalidImage(
            f"Image is too large ({len(data) / 1_048_576:.1f} MB). "
            f"Limit is {max_bytes / 1_048_576:.0f} MB."
        )

    buf = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if image is None:
        fmt = sniff_format(data)
        hint = f" Detected format: {fmt}." if fmt != "unknown" else ""
        raise InvalidImage("Could not decode image. Send a JPEG, PNG, WebP, BMP or TIFF file." + hint)

    height, width = image.shape[:2]
    if min(height, width) < 16:
        raise InvalidImage(f"Image is too small ({width}x{height}); minimum side is 16 px.")

    if max_side and max(height, width) > max_side:
        scale = max_side / float(max(height, width))
        image = cv2.resize(
            image,
            (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
            interpolation=cv2.INTER_AREA,
        )
    return np.ascontiguousarray(image)


def encode_jpeg_base64(image: np.ndarray, *, quality: int = 90) -> str:
    """Encode a BGR image as a base64 JPEG (used for aligned face crops)."""
    ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:  # pragma: no cover - cv2 only fails on absurd input
        raise InvalidImage("Could not encode face crop.")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def decode_base64_image(value: str) -> bytes:
    """Accept either raw base64 or a ``data:image/...;base64,`` URL."""
    payload = value.strip()
    if payload.startswith("data:"):
        _, _, payload = payload.partition(",")
    try:
        return base64.b64decode(payload, validate=True)
    except Exception as exc:  # noqa: BLE001 - surfaced as a client error
        raise InvalidImage("Value is not valid base64 image data.") from exc
