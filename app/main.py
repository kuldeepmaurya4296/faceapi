"""FastAPI application factory.

Run it with::

    uvicorn app.main:app --host 0.0.0.0 --port 8000

or, for a fully self-contained start (creates the venv, downloads models,
prints your admin token)::

    python cli.py serve
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .config import Settings, get_settings
from .engine import FaceEngine
from .errors import install_error_handlers
from .metrics import Metrics
from .routes import account, admin, collections, faces, meta
from .security import RateLimiter
from .storage import Storage

logger = logging.getLogger("faceapi")

#: Paths that are never billed and never written to the usage ledger.
_UNBILLED_PREFIXES = ("/healthz", "/readyz", "/metrics", "/docs", "/redoc", "/openapi.json", "/admin")


def _configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    app.state.storage = Storage(settings.db_path)
    app.state.limiter = RateLimiter(window_seconds=60.0)
    app.state.metrics = Metrics()

    engine = FaceEngine(
        models_dir=settings.models_dir,
        detect_model=settings.detect_model,
        recog_model=settings.recog_model,
        input_size=settings.detect_input_size,
        score_threshold=settings.detect_score_threshold,
        nms_threshold=settings.detect_nms_threshold,
        top_k=settings.detect_top_k,
        min_face_size=settings.min_face_size,
    )
    app.state.engine = engine

    admin_token = settings.load_or_create_admin_token()

    logger.info("=" * 64)
    logger.info("%s v%s starting", settings.service_name, __version__)
    logger.info("auth mode    : %s", "api key required" if settings.auth_enabled else "PERSONAL (no key needed)")
    logger.info("models       : %s + %s", *engine.model_names.values())
    logger.info("database     : %s", settings.db_path)
    logger.info("admin token  : %s", admin_token)
    if settings.auth_enabled:
        logger.info("next step    : python cli.py keys create --name 'me' --plan personal")
    logger.info("docs         : %s/docs", settings.public_base_url.rstrip("/"))
    logger.info("=" * 64)

    try:
        yield
    finally:
        app.state.storage.close()
        logger.info("shutdown complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    _configure_logging(settings)

    docs_enabled = settings.docs_enabled
    app = FastAPI(
        title=settings.service_name,
        version=__version__,
        description=(
            "Face detection and face recognition as a REST API.\n\n"
            "**Detection** finds faces and their landmarks. **Recognition** turns a face into a "
            "128-d embedding so you can verify (1:1) or identify (1:N) people.\n\n"
            "Authenticate with the `X-API-Key` header. `/admin/*` endpoints use `X-Admin-Token`."
        ),
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
        contact={"name": "Face API"},
        license_info={"name": "Proprietary"},
    )
    app.state.settings = settings
    app.state.logger = logger

    app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=[
                "X-Request-ID",
                "X-RateLimit-Limit",
                "X-RateLimit-Remaining",
                "Retry-After",
                "X-Quota-Limit",
                "X-Quota-Used",
            ],
        )

    install_error_handlers(app)

    @app.middleware("http")
    async def accounting(request: Request, call_next):
        """Attach a request id, then meter the call for billing and metrics."""
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        request.state.faces_detected = 0
        started = time.perf_counter()

        response = await call_next(request)

        latency_ms = (time.perf_counter() - started) * 1000
        path = request.url.path
        app.state.metrics.observe(
            endpoint=_metric_endpoint(path),
            method=request.method,
            status_code=response.status_code,
            latency_ms=latency_ms,
            faces=int(getattr(request.state, "faces_detected", 0) or 0),
        )

        key_context = getattr(request.state, "key_context", None)
        if key_context is not None and not path.startswith(_UNBILLED_PREFIXES):
            client_ip = request.client.host if request.client else None
            await run_in_threadpool(
                app.state.storage.record_usage,
                key_id=key_context.key_id,
                endpoint=_metric_endpoint(path),
                method=request.method,
                status_code=response.status_code,
                faces=int(getattr(request.state, "faces_detected", 0) or 0),
                latency_ms=latency_ms,
                client_ip=client_ip,
                billable=True,
            )
            await run_in_threadpool(app.state.storage.touch_api_key, key_context.key_id)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Processing-Time-Ms"] = f"{latency_ms:.2f}"
        return response

    app.include_router(meta.router)
    app.include_router(faces.router)
    app.include_router(collections.router)
    app.include_router(account.router)
    app.include_router(admin.router)

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        from fastapi import Response
        return Response(status_code=204)

    return app


def _metric_endpoint(path: str) -> str:
    """Collapse path parameters so metric cardinality stays bounded."""
    parts = path.split("/")
    if path.startswith("/v1/collections/") and len(parts) >= 5:
        parts[3] = "{name}"
        if len(parts) >= 7:
            parts[5] = "{face_id}"
        return "/".join(parts)
    if (path.startswith("/admin/keys/") or path.startswith("/admin/usage/")) and len(parts) >= 4:
        parts[3] = "{key_id}"
        return "/".join(parts)
    return path


app = create_app()
