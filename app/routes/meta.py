"""Public metadata endpoints: service discovery, health and metrics."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from .. import __version__
from ..config import PLANS
from ..schemas import PlanInfo, ServiceInfo

router = APIRouter(tags=["meta"])


@router.get("/", response_model=ServiceInfo, summary="Service discovery / landing payload")
def service_info(request: Request) -> ServiceInfo:
    settings = request.app.state.settings
    engine = request.app.state.engine
    docs_url = "/docs" if settings.docs_enabled else None
    return ServiceInfo(
        service=settings.service_name,
        version=__version__,
        auth_mode="api_key" if settings.auth_enabled else "personal",
        endpoints=[
            "POST /v1/detect",
            "POST /v1/embed",
            "POST /v1/verify",
            "POST /v1/compare",
            "POST /v1/identify",
            "POST /v1/collections",
            "GET  /v1/collections",
            "POST /v1/collections/{name}/faces",
            "GET  /v1/collections/{name}/faces",
            "GET  /v1/me",
            "GET  /healthz",
            "GET  /readyz",
            "GET  /metrics",
        ],
        models=engine.model_names,
        plans=[
            PlanInfo(
                name=plan.name,
                rate_limit_per_minute=None if plan.unlimited_rate else plan.rate_per_minute,
                monthly_quota=None if plan.unlimited_quota else plan.monthly_quota,
                max_upload_mb=plan.max_upload_mb,
                max_faces_per_image=plan.max_faces_per_image,
                collections=plan.allow_collections,
                price_usd_month=plan.price_usd_month,
                overage_per_1000_usd=plan.overage_per_1000_usd,
            )
            for plan in PLANS.values()
        ],
        docs_url=docs_url,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )


@router.get("/healthz", summary="Liveness probe (never billed, no auth)")
def healthz(request: Request) -> dict:
    return {"status": "ok", "uptime_seconds": round(request.app.state.metrics.uptime_seconds, 1)}


@router.get("/readyz", summary="Readiness probe: models loaded and database reachable")
def readyz(request: Request, response: Response) -> dict:
    engine = request.app.state.engine
    storage = request.app.state.storage
    checks = {"models": "ok", "database": "ok"}
    healthy = True
    try:
        engine.model_names
    except Exception:  # pragma: no cover - defensive
        checks["models"] = "error"
        healthy = False
    try:
        storage.global_stats(days=1)
    except Exception:  # pragma: no cover - defensive
        checks["database"] = "error"
        healthy = False
    if not healthy:
        response.status_code = 503
    return {"status": "ready" if healthy else "degraded", "checks": checks, "models": engine.model_names}


@router.get("/metrics", summary="Prometheus metrics")
def metrics(request: Request) -> Response:
    return Response(content=request.app.state.metrics.render_prometheus(), media_type="text/plain; version=0.0.4")
