"""Face collections — per-customer galleries for 1:N identification."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Request, Response, UploadFile
from fastapi import File as FileParam
from fastapi import Form

from ..deps import CallContext, CurrentCall, get_engine, read_image_upload, to_box
from ..engine import FaceEngine
from ..errors import InvalidImage, NoFaceFound
from ..schemas import (
    Box,
    CollectionCreate,
    CollectionInfo,
    CollectionListResponse,
    FaceCreateResponse,
    FaceListResponse,
)
from ..security import require_collections

router = APIRouter(prefix="/v1/collections", tags=["collections"])


def _guard(call: CallContext) -> None:
    require_collections(call.key)


@router.post("", response_model=CollectionInfo, summary="Create a collection (gallery)")
def create_collection(payload: CollectionCreate, call: CurrentCall) -> CollectionInfo:
    _guard(call)
    record = call.storage.create_collection(call.owner, payload.name, payload.description)
    return CollectionInfo(
        name=record["name"],
        description=record.get("description"),
        face_count=int(record.get("face_count") or 0),
        created_at=record["created_at"],
    )


@router.get("", response_model=CollectionListResponse, summary="List your collections")
def list_collections(call: CurrentCall) -> CollectionListResponse:
    _guard(call)
    items = [
        CollectionInfo(
            name=row["name"],
            description=row.get("description"),
            face_count=int(row.get("face_count") or 0),
            created_at=row["created_at"],
        )
        for row in call.storage.list_collections(call.owner)
    ]
    return CollectionListResponse(collections=items, count=len(items))


@router.get("/{name}", response_model=CollectionInfo, summary="Get one collection")
def get_collection(name: str, call: CurrentCall) -> CollectionInfo:
    _guard(call)
    row = call.storage.get_collection_or_404(call.owner, name)
    return CollectionInfo(
        name=row["name"],
        description=row.get("description"),
        face_count=int(row.get("face_count") or 0),
        created_at=row["created_at"],
    )


@router.delete("/{name}", summary="Delete a collection and every face inside it")
def delete_collection(name: str, call: CurrentCall) -> dict:
    _guard(call)
    call.storage.delete_collection(call.owner, name)
    return {"deleted": True, "collection": name}


@router.post("/{name}/faces", response_model=FaceCreateResponse, summary="Enrol a face into a collection")
def add_face(
    name: str,
    call: CurrentCall,
    image: UploadFile = FileParam(..., description="Image containing the face to enrol"),
    external_id: str | None = Form(None, description="Your own identifier for this person"),
    metadata: str | None = Form(None, description="Arbitrary JSON object stored alongside the face"),
    mode: str = Query("largest", pattern="^(largest|index)$"),
    face_index: int = Query(0, ge=0),
    engine: FaceEngine = Depends(get_engine),
) -> FaceCreateResponse:
    _guard(call)
    bgr, info = read_image_upload(image, call)
    faces = engine.detect(bgr, max_faces=call.plan.max_faces_per_image)
    if not faces:
        raise NoFaceFound("No face detected in the uploaded image.", code="no_face_found")

    if mode == "index":
        if face_index < 0 or face_index >= len(faces):
            raise NoFaceFound(
                f"face_index {face_index} is out of range; {len(faces)} face(s) detected.",
                code="face_index_out_of_range",
            )
        face = faces[face_index]
    else:
        face = faces[0]

    parsed_metadata = None
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
            if not isinstance(parsed_metadata, dict):
                raise ValueError("metadata must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            raise InvalidImage(f"Invalid 'metadata' form field: {exc}", code="invalid_metadata") from exc

    embedding = engine.embed(bgr, face)
    record = call.storage.add_face(
        owner=call.owner,
        collection=name,
        embedding=embedding,
        external_id=external_id,
        det_score=float(face.score),
        box=face.box,
        metadata=parsed_metadata,
    )
    box, _ = to_box(face.x, face.y, face.width, face.height, info.width, info.height)
    return FaceCreateResponse(
        collection=name,
        face_id=record["face_id"],
        external_id=record["external_id"],
        det_score=record["det_score"],
        box=box,
        metadata=record["metadata"],
        created_at=record["created_at"],
    )


@router.get("/{name}/faces", response_model=FaceListResponse, summary="List enrolled faces")
def list_faces(
    name: str,
    call: CurrentCall,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> FaceListResponse:
    _guard(call)
    rows = call.storage.list_faces(call.owner, name, limit=limit, offset=offset)
    faces = [
        FaceCreateResponse(
            collection=name,
            face_id=row["face_id"],
            external_id=row.get("external_id"),
            det_score=row.get("det_score"),
            box=Box(**dict(zip(("x", "y", "width", "height"), row["box"]))) if row.get("box") else None,
            metadata=row.get("metadata"),
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return FaceListResponse(
        collection=name, faces=faces, count=len(faces), limit=limit, offset=offset
    )


@router.delete("/{name}/faces/{face_id}", summary="Remove one enrolled face")
def delete_face(name: str, face_id: str, call: CurrentCall) -> dict:
    _guard(call)
    call.storage.delete_face(call.owner, name, face_id)
    return {"deleted": True, "collection": name, "face_id": face_id}
