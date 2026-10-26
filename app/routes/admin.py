"""Admin endpoints — issue, meter and revoke customer API keys.

Protected by the **admin token** (``X-Admin-Token`` header), never by a
customer API key, so a customer can never mint keys or read another
customer's usage.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from ..config import PLANS, DEFAULT_PLAN
from ..deps import AdminGuard, get_settings_dep, get_storage
from ..errors import FaceAPIError, NotFound
from ..schemas import (
    AdminKeyCreate,
    AdminKeyCreated,
    AdminKeyInfo,
    AdminKeyListResponse,
    AdminKeyUpdate,
    InvoiceSummaryResponse,
)
from ..storage import Storage

#: Every /admin/* route is gated by the admin token, never by a customer API key.
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[AdminGuard])


def _validate_plan(plan: str) -> str:
    if plan not in PLANS:
        raise FaceAPIError(
            f"Unknown plan '{plan}'. Valid plans: {', '.join(sorted(PLANS))}.",
            code="unknown_plan",
            status_code=400,
        )
    return plan


@router.post(
    "/keys",
    response_model=AdminKeyCreated,
    summary="Issue a new API key (the secret is shown only once)",
)
def create_key(
    payload: AdminKeyCreate,
    storage: Storage = Depends(get_storage),
    settings=Depends(get_settings_dep),
) -> AdminKeyCreated:
    plan_name = _validate_plan(payload.plan or DEFAULT_PLAN)
    if payload.expires_at:
        try:
            datetime.fromisoformat(payload.expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise FaceAPIError(
                "expires_at must be an ISO-8601 timestamp, e.g. 2027-01-31T00:00:00Z.",
                code="invalid_expiry",
                status_code=400,
            ) from exc

    record, secret = storage.create_api_key(
        name=payload.name,
        plan=plan_name,
        email=payload.email,
        expires_at=payload.expires_at,
        monthly_quota=payload.monthly_quota,
        rate_per_minute=payload.rate_per_minute,
        note=payload.note,
    )
    plan = settings.plan(plan_name)
    quota = record["monthly_quota"] if record["monthly_quota"] is not None else plan.monthly_quota
    rate = record["rate_per_minute"] if record["rate_per_minute"] is not None else plan.rate_per_minute
    return AdminKeyCreated(
        key_id=record["key_id"],
        api_key=secret,
        name=record["name"],
        plan=record["plan"],
        monthly_quota=None if quota < 0 else quota,
        rate_limit_per_minute=None if rate < 0 else rate,
        created_at=record["created_at"],
    )


@router.get(
    "/keys",
    response_model=AdminKeyListResponse,
    summary="List issued keys with this month's usage",
)
def list_keys(
    storage: Storage = Depends(get_storage),
    settings=Depends(get_settings_dep),
    include_revoked: bool = Query(False),
) -> AdminKeyListResponse:
    keys = []
    for record in storage.list_api_keys(include_revoked=include_revoked):
        plan = settings.plan(record["plan"])
        quota = record["monthly_quota"] if record["monthly_quota"] is not None else plan.monthly_quota
        rate = record["rate_per_minute"] if record["rate_per_minute"] is not None else plan.rate_per_minute
        keys.append(
            AdminKeyInfo(
                key_id=record["key_id"],
                key_prefix=record["key_prefix"],
                name=record["name"],
                email=record.get("email"),
                plan=record["plan"],
                active=bool(record["active"]),
                monthly_quota=None if quota < 0 else quota,
                rate_per_minute=None if rate < 0 else rate,
                created_at=record["created_at"],
                expires_at=record.get("expires_at"),
                last_used_at=record.get("last_used_at"),
                revoked_at=record.get("revoked_at"),
                note=record.get("note"),
                month_usage=storage.month_usage(record["key_id"]),
            )
        )
    return AdminKeyListResponse(keys=keys, count=len(keys))


@router.get("/keys/{key_id}", response_model=AdminKeyInfo, summary="Get one key")
def get_key(key_id: str, storage: Storage = Depends(get_storage), settings=Depends(get_settings_dep)) -> AdminKeyInfo:
    record = storage.get_api_key(key_id)
    if record is None:
        raise NotFound(f"API key '{key_id}' not found.")
    plan = settings.plan(record["plan"])
    quota = record["monthly_quota"] if record["monthly_quota"] is not None else plan.monthly_quota
    rate = record["rate_per_minute"] if record["rate_per_minute"] is not None else plan.rate_per_minute
    return AdminKeyInfo(
        key_id=record["key_id"],
        key_prefix=record["key_prefix"],
        name=record["name"],
        email=record.get("email"),
        plan=record["plan"],
        active=bool(record["active"]),
        monthly_quota=None if quota < 0 else quota,
        rate_per_minute=None if rate < 0 else rate,
        created_at=record["created_at"],
        expires_at=record.get("expires_at"),
        last_used_at=record.get("last_used_at"),
        revoked_at=record.get("revoked_at"),
        note=record.get("note"),
        month_usage=storage.month_usage(record["key_id"]),
    )


@router.patch("/keys/{key_id}", response_model=AdminKeyInfo, summary="Change plan / limits")
def update_key(
    key_id: str,
    payload: AdminKeyUpdate,
    storage: Storage = Depends(get_storage),
    settings=Depends(get_settings_dep),
) -> AdminKeyInfo:
    fields = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "plan" in fields:
        _validate_plan(fields["plan"])
    if "active" in fields:
        fields["active"] = 1 if fields["active"] else 0
    storage.update_api_key(key_id, **fields)
    return get_key(key_id, storage=storage, settings=settings)


@router.post("/keys/{key_id}/revoke", response_model=AdminKeyInfo, summary="Revoke a key")
def revoke_key(key_id: str, storage: Storage = Depends(get_storage), settings=Depends(get_settings_dep)) -> AdminKeyInfo:
    record = storage.revoke_api_key(key_id)
    return get_key(record["key_id"], storage=storage, settings=settings)


@router.delete("/keys/{key_id}", summary="Delete a key (usage history is kept)")
def delete_key(key_id: str, storage: Storage = Depends(get_storage)) -> dict:
    storage.delete_api_key(key_id)
    return {"deleted": True, "key_id": key_id}


@router.get("/usage/{key_id}", summary="Usage breakdown for one key")
def key_usage(
    key_id: str,
    storage: Storage = Depends(get_storage),
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
) -> dict:
    if storage.get_api_key(key_id) is None:
        raise NotFound(f"API key '{key_id}' not found.")
    return storage.usage_summary(key_id, month=month)


@router.get("/stats", summary="Service-wide traffic summary")
def stats(storage: Storage = Depends(get_storage), days: int = Query(30, ge=1, le=366)) -> dict:
    return storage.global_stats(days=days)


@router.get(
    "/invoices",
    response_model=InvoiceSummaryResponse,
    summary="Per-customer billable usage for a month (your invoicing input)",
)
def invoices(
    storage: Storage = Depends(get_storage),
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
) -> InvoiceSummaryResponse:
    resolved_month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    lines = storage.invoice_lines(month=resolved_month, plans=PLANS)
    return InvoiceSummaryResponse(
        month=resolved_month,
        lines=lines,
        totals={
            "customers": len(lines),
            "requests": sum(line["requests"] for line in lines),
            "base_usd": round(sum(line["base_usd"] for line in lines), 2),
            "overage_usd": round(sum(line["overage_usd"] for line in lines), 2),
            "total_usd": round(sum(line["total_usd"] for line in lines), 2),
        },
    )
