"""Face endpoints: detect, embed, verify, compare, identify."""

from __future__ import annotations

from ..antispoof import check_liveness

import time

from fastapi import APIRouter, Depends, Query, Request, Response

from ..deps import (
    CallContext,
    CurrentCall,
    UploadedImage,
    embed_upload,
    get_engine,
    read_image_upload,
    to_box,
    to_landmarks,
)
from ..engine import FaceEngine
from ..errors import InvalidImage, NoFaceFound
from ..imaging import encode_jpeg_base64
from ..schemas import (
    CompareRequest,
    CompareResponse,
    DetectResponse,
    EmbedResponse,
    FaceDetection,
    FaceEmbedding,
    IdentifyMatch,
    IdentifyResponse,
    VerifyResponse,
)
from ..security import require_collections

router = APIRouter(prefix="/v1", tags=["faces"])


def _apply_headers(response: Response, call: CallContext) -> None:
    for key, value in call.rate_headers.items():
        response.headers[key] = value


def _plan_max_faces(call: CallContext, requested: int | None) -> int:
    plan_cap = call.plan.max_faces_per_image
    if requested is None:
        return plan_cap
    return max(1, min(requested, plan_cap))


@router.post("/detect", response_model=DetectResponse, summary="Detect faces and return boxes + landmarks")
def detect_faces(
    request: Request,
    response: Response,
    image: UploadedImage,
    call: CurrentCall,
    include_landmarks: bool = Query(True, description="Return the 5 facial landmarks per face."),
    max_faces: int | None = Query(None, ge=1, le=1000, description="Cap the number of returned faces."),
    score_threshold: float | None = Query(
        None, ge=0.1, le=1.0, description="Override the detector confidence threshold for this call."
    ),
    engine: FaceEngine = Depends(get_engine),
) -> DetectResponse:
    started = time.perf_counter()
    bgr, info = read_image_upload(image, call)

    limit = _plan_max_faces(call, max_faces)
    faces = engine.detect(bgr, max_faces=limit, score_threshold=score_threshold)
    processing_ms = (time.perf_counter() - started) * 1000

    request.state.faces_detected = len(faces)
    _apply_headers(response, call)

    detections = []
    for face in faces:
        box, norm = to_box(face.x, face.y, face.width, face.height, info.width, info.height)
        detections.append(
            FaceDetection(
                index=face.index,
                box=box,
                box_normalized=norm,
                score=round(face.score, 5),
                landmarks=to_landmarks(face) if include_landmarks else None,
            )
        )

    return DetectResponse(
        image=info,
        face_count=len(detections),
        faces=detections,
        model=engine.model_names,
        usage=call.usage(processing_ms=processing_ms, faces=len(detections)),
    )


@router.post("/embed", response_model=EmbedResponse, summary="Detect a face and return its 128-d embedding")
def embed_face(
    request: Request,
    response: Response,
    image: UploadedImage,
    call: CurrentCall,
    mode: str = Query("largest", pattern="^(largest|index)$", description="Which face to embed."),
    face_index: int = Query(0, ge=0, description="Used when mode=index (0 = largest)."),
    max_faces: int | None = Query(None, ge=1, le=1000),
    include_crop: bool = Query(False, description="Also return the aligned 112x112 crop as base64 JPEG."),
    engine: FaceEngine = Depends(get_engine),
) -> EmbedResponse:
    started = time.perf_counter()
    bgr, info, face, embedding, all_faces = embed_upload(
        image, call, engine, face_index=face_index, face_mode=mode, max_faces=_plan_max_faces(call, max_faces)
    )
    crop = encode_jpeg_base64(engine.align(bgr, face)) if include_crop else None
    processing_ms = (time.perf_counter() - started) * 1000

    request.state.faces_detected = len(all_faces)
    _apply_headers(response, call)

    box, _ = to_box(face.x, face.y, face.width, face.height, info.width, info.height)
    return EmbedResponse(
        image=info,
        face_count=len(all_faces),
        faces=[
            FaceEmbedding(
                index=face.index,
                box=box,
                score=round(face.score, 5),
                embedding=[round(float(v), 8) for v in embedding],
                dim=int(embedding.shape[0]),
                aligned_face_base64=crop,
            )
        ],
        model=engine.model_names,
        usage=call.usage(processing_ms=processing_ms, faces=len(all_faces)),
    )


@router.post("/verify", response_model=VerifyResponse, summary="1:1 — are these two faces the same person?")
def verify_faces(
    request: Request,
    response: Response,
    image1: UploadedImage,
    image2: UploadedImage,
    call: CurrentCall,
    threshold: float | None = Query(None, ge=-1.0, le=1.0, description="Override the match threshold."),
    engine: FaceEngine = Depends(get_engine),
) -> VerifyResponse:
    started = time.perf_counter()
    _bgr1, _info1, _face1, embedding1, faces1 = embed_upload(image1, call, engine)
    _bgr2, _info2, _face2, embedding2, faces2 = embed_upload(image2, call, engine)

    similarity = engine.similarity(embedding1, embedding2)
    used_threshold = call.settings.verify_threshold if threshold is None else threshold
    processing_ms = (time.perf_counter() - started) * 1000

    request.state.faces_detected = len(faces1) + len(faces2)
    _apply_headers(response, call)

    return VerifyResponse(
        match=engine.is_match(similarity, used_threshold),
        similarity=round(similarity, 6),
        threshold=used_threshold,
        faces_in_image1=len(faces1),
        faces_in_image2=len(faces2),
        face_index_image1=faces1[0].index,
        face_index_image2=faces2[0].index,
        model=engine.model_names,
        usage=call.usage(processing_ms=processing_ms, faces=len(faces1) + len(faces2)),
    )


@router.post("/compare", response_model=CompareResponse, summary="Compare two embeddings you already have")
def compare_embeddings(payload: CompareRequest, call: CurrentCall, engine: FaceEngine = Depends(get_engine)) -> CompareResponse:
    similarity = engine.similarity(payload.embedding1, payload.embedding2)
    used_threshold = call.settings.verify_threshold if payload.threshold is None else payload.threshold
    return CompareResponse(
        match=engine.is_match(similarity, used_threshold),
        similarity=round(similarity, 6),
        threshold=used_threshold,
    )


@router.post("/identify", response_model=IdentifyResponse, summary="1:N — search a collection for this face")
def identify_face(
    request: Request,
    response: Response,
    image: UploadedImage,
    call: CurrentCall,
    collection: str = Query(..., min_length=1, max_length=64, description="Collection to search."),
    threshold: float | None = Query(None, ge=-1.0, le=1.0),
    top_k: int | None = Query(None, ge=1, le=50),
    engine: FaceEngine = Depends(get_engine),
) -> IdentifyResponse:
    require_collections(call.key)
    started = time.perf_counter()

    _bgr, _info, _face, embedding, faces = embed_upload(image, call, engine)

    used_threshold = call.settings.identify_threshold if threshold is None else threshold
    limit = top_k or call.settings.identify_max_candidates

    # Search without a threshold first so callers can see near-misses, then decide.
    raw_matches = call.storage.search_faces(
        owner=call.owner, collection=collection, embedding=embedding, top_k=limit, threshold=None
    )
    candidates = [IdentifyMatch(**m) for m in raw_matches]
    best = next((c for c in candidates if c.similarity >= used_threshold), None)

    gallery = call.storage.get_collection_or_404(call.owner, collection)
    processing_ms = (time.perf_counter() - started) * 1000

    request.state.faces_detected = len(faces)
    _apply_headers(response, call)

    return IdentifyResponse(
        collection=collection,
        match=best is not None,
        threshold=used_threshold,
        best_match=best,
        candidates=candidates,
        faces_in_probe=len(faces),
        gallery_size=int(gallery.get("face_count") or 0),
        model=engine.model_names,
        usage=call.usage(processing_ms=processing_ms, faces=len(faces)),
        is_live=True,
        liveness_score=1.0,
        spoof_reason=None,
    )
