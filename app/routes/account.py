"""Customer self-service: plan, quota and usage for the calling key."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..deps import CurrentCall
from ..schemas import MeResponse

router = APIRouter(prefix="/v1", tags=["account"])


@router.get("/me", response_model=MeResponse, summary="Your plan, limits and usage this month")
def me(call: CurrentCall, month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$")) -> MeResponse:
    usage = call.storage.usage_summary(call.key.key_id, month=month)
    return MeResponse(
        key=call.key.to_public(month_usage=usage["requests"]),
        usage=usage,
    )
