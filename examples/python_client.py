#!/usr/bin/env python3
"""Minimal Face API client / SDK — copy this into your own project.

    export FACEAPI_URL=http://127.0.0.1:8000
    export FACEAPI_KEY=fk_live_...          # omit entirely in personal mode

    python examples/python_client.py info
    python examples/python_client.py detect photo.jpg
    python examples/python_client.py embed photo.jpg --crop out_face.jpg
    python examples/python_client.py verify id.jpg selfie.jpg
    python examples/python_client.py enrol customers CUST-001 photo.jpg
    python examples/python_client.py identify customers probe.jpg

Only needs `httpx` (or swap in `requests` — one call site).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import httpx

BASE_URL = os.environ.get("FACEAPI_URL", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.environ.get("FACEAPI_KEY") or os.environ.get("FACEAPI_API_KEY")
TIMEOUT = float(os.environ.get("FACEAPI_TIMEOUT", "60"))


class FaceAPIClient:
    """Tiny typed wrapper around the REST API."""

    def __init__(self, base_url: str = BASE_URL, api_key: str | None = API_KEY, timeout: float = TIMEOUT):
        self.base_url = base_url.rstrip("/")
        headers = {"X-API-Key": api_key} if api_key else {}
        self._client = httpx.Client(base_url=self.base_url, headers=headers, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "FaceAPIClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- internals ---------------------------------------------------------
    @staticmethod
    def _raise(response: httpx.Response) -> None:
        if response.status_code >= 400:
            try:
                error = response.json()["error"]
                raise RuntimeError(f"{response.status_code} {error['code']}: {error['message']}")
            except (KeyError, json.JSONDecodeError):
                response.raise_for_status()

    @staticmethod
    def _image(path: str | Path) -> tuple[str, bytes, str]:
        path = Path(path)
        suffix = path.suffix.lower()
        mime = {
            ".png": "image/png",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".gif": "image/gif",
        }.get(suffix, "image/jpeg")
        return (path.name, path.read_bytes(), mime)

    # -- endpoints ---------------------------------------------------------
    def info(self) -> dict:
        return self._client.get("/").json()

    def health(self) -> dict:
        return self._client.get("/healthz").json()

    def me(self) -> dict:
        response = self._client.get("/v1/me")
        self._raise(response)
        return response.json()

    def detect(self, image: str | Path, *, max_faces: int | None = None, landmarks: bool = True) -> dict:
        params = {"include_landmarks": landmarks}
        if max_faces:
            params["max_faces"] = max_faces
        response = self._client.post("/v1/detect", files={"image": self._image(image)}, params=params)
        self._raise(response)
        return response.json()

    def embed(self, image: str | Path, *, crop: bool = False) -> dict:
        response = self._client.post(
            "/v1/embed", files={"image": self._image(image)}, params={"include_crop": crop}
        )
        self._raise(response)
        return response.json()

    def verify(self, image1: str | Path, image2: str | Path, *, threshold: float | None = None) -> dict:
        params = {} if threshold is None else {"threshold": threshold}
        response = self._client.post(
            "/v1/verify",
            files={"image1": self._image(image1), "image2": self._image(image2)},
            params=params,
        )
        self._raise(response)
        return response.json()

    def compare(self, embedding1: list[float], embedding2: list[float], *, threshold: float | None = None) -> dict:
        payload: dict = {"embedding1": embedding1, "embedding2": embedding2}
        if threshold is not None:
            payload["threshold"] = threshold
        response = self._client.post("/v1/compare", json=payload)
        self._raise(response)
        return response.json()

    def create_collection(self, name: str, description: str | None = None) -> dict:
        response = self._client.post("/v1/collections", json={"name": name, "description": description})
        if response.status_code == 409:
            return {"name": name, "already_existed": True}
        self._raise(response)
        return response.json()

    def enrol(
        self,
        collection: str,
        image: str | Path,
        *,
        external_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        data = {}
        if external_id:
            data["external_id"] = external_id
        if metadata:
            data["metadata"] = json.dumps(metadata)
        response = self._client.post(
            f"/v1/collections/{collection}/faces", files={"image": self._image(image)}, data=data
        )
        self._raise(response)
        return response.json()

    def identify(self, collection: str, image: str | Path, *, threshold: float | None = None, top_k: int = 5) -> dict:
        params: dict = {"collection": collection, "top_k": top_k}
        if threshold is not None:
            params["threshold"] = threshold
        response = self._client.post("/v1/identify", files={"image": self._image(image)}, params=params)
        self._raise(response)
        return response.json()


# ------------------------------------------------------------------- CLI
def main() -> int:
    parser = argparse.ArgumentParser(description="Face API example client")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="service + plan discovery")
    sub.add_parser("me", help="your plan and usage")

    p_detect = sub.add_parser("detect", help="find faces")
    p_detect.add_argument("image")

    p_embed = sub.add_parser("embed", help="get the 128-d embedding")
    p_embed.add_argument("image")
    p_embed.add_argument("--crop", help="also write the aligned face to this path")

    p_verify = sub.add_parser("verify", help="same person?")
    p_verify.add_argument("image1")
    p_verify.add_argument("image2")
    p_verify.add_argument("--threshold", type=float)

    p_enrol = sub.add_parser("enrol", help="add a face to a collection")
    p_enrol.add_argument("collection")
    p_enrol.add_argument("image")
    p_enrol.add_argument("--external-id")
    p_enrol.add_argument("--metadata", help="JSON object")

    p_identify = sub.add_parser("identify", help="search a collection")
    p_identify.add_argument("collection")
    p_identify.add_argument("image")
    p_identify.add_argument("--threshold", type=float)

    args = parser.parse_args()

    with FaceAPIClient() as client:
        if args.command == "info":
            info = client.info()
            print(f"{info['service']} v{info['version']} — auth mode: {info['auth_mode']}")
            for plan in info["plans"]:
                quota = "unlimited" if plan["monthly_quota"] is None else f"{plan['monthly_quota']:,} req/mo"
                print(f"  {plan['name']:<11} ${plan['price_usd_month']:>6.2f}  {quota}")

        elif args.command == "me":
            body = client.me()
            print(json.dumps(body, indent=2))

        elif args.command == "detect":
            body = client.detect(args.image)
            print(f"{body['face_count']} face(s), {body['usage']['processing_ms']} ms")
            for face in body["faces"]:
                box = face["box"]
                print(f"  #{face['index']} score={face['score']:.3f} box=({box['x']},{box['y']},{box['width']}x{box['height']})")

        elif args.command == "embed":
            body = client.embed(args.image, crop=bool(args.crop))
            face = body["faces"][0]
            print(f"dim={face['dim']} score={face['score']:.3f} first5={[round(v, 4) for v in face['embedding'][:5]]}")
            if args.crop and face.get("aligned_face_base64"):
                Path(args.crop).write_bytes(base64.b64decode(face["aligned_face_base64"]))
                print(f"aligned crop written to {args.crop}")

        elif args.command == "verify":
            body = client.verify(args.image1, args.image2, threshold=args.threshold)
            verdict = "MATCH" if body["match"] else "NO MATCH"
            print(f"{verdict}  similarity={body['similarity']:.4f}  threshold={body['threshold']}")

        elif args.command == "enrol":
            client.create_collection(args.collection, "created by python_client.py")
            metadata = json.loads(args.metadata) if args.metadata else None
            body = client.enrol(args.collection, args.image, external_id=args.external_id, metadata=metadata)
            print(f"enrolled {body['face_id']} (external_id={body['external_id']}) into '{args.collection}'")

        elif args.command == "identify":
            body = client.identify(args.collection, args.image, threshold=args.threshold)
            print(f"match={body['match']} gallery={body['gallery_size']} threshold={body['threshold']}")
            for candidate in body["candidates"]:
                marker = "->" if body["best_match"] and candidate["face_id"] == body["best_match"]["face_id"] else "  "
                print(f"  {marker} {candidate['external_id'] or candidate['face_id']}: {candidate['similarity']:.4f}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"API error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except httpx.ConnectError:
        print(f"Cannot reach {BASE_URL}. Is the server running? (`python cli.py serve`)", file=sys.stderr)
        raise SystemExit(2) from None
