"""Authentication, authorization and rate limiting.

Three modes are supported by design:

1. **Commercial** (``FACEAPI_AUTH_ENABLED=true``, the default) — every ``/v1/*``
   call must carry an API key. Keys carry a plan, and the plan decides the rate
   limit, the monthly quota and the feature set. ``/admin/*`` is protected by a
   separate admin token so customers can never mint their own keys.
2. **Personal / private** (``FACEAPI_AUTH_ENABLED=false``) — no key needed, no
   quota, every request runs on the unlimited ``personal`` plan. Use this when
   you are the only consumer or the service sits behind your own gateway.
3. **Hybrid** — keep auth on, but issue yourself a key with the ``personal``
   plan via ``python cli.py keys create --plan personal``.
"""

from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Request

from .config import PlanLimits, Settings
from .errors import AuthError, PlanError, QuotaExceeded, RateLimited

PERSONAL_OWNER = "local"


@dataclass(slots=True)
class KeyContext:
    """Everything the request needs to know about who is calling."""

    key_id: str
    owner: str
    name: str
    plan: PlanLimits
    is_personal: bool = False
    monthly_quota: int | None = None
    rate_per_minute: int | None = None
    authenticated: bool = True

    @property
    def effective_quota(self) -> int:
        if self.monthly_quota is not None:
            return self.monthly_quota
        return self.plan.monthly_quota

    @property
    def effective_rate(self) -> int:
        if self.rate_per_minute is not None:
            return self.rate_per_minute
        return self.plan.rate_per_minute

    @property
    def quota_unlimited(self) -> bool:
        return self.effective_quota < 0

    @property
    def rate_unlimited(self) -> bool:
        return self.effective_rate < 0

    def to_public(self, *, month_usage: int | None = None) -> dict:
        return {
            "key_id": self.key_id,
            "name": self.name,
            "plan": self.plan.name,
            "authenticated": self.authenticated,
            "personal_mode": self.is_personal,
            "rate_limit_per_minute": None if self.rate_unlimited else self.effective_rate,
            "monthly_quota": None if self.quota_unlimited else self.effective_quota,
            "collections_enabled": self.plan.allow_collections,
            "max_faces_per_image": self.plan.max_faces_per_image,
            "month_usage": month_usage,
        }


def personal_context(settings: Settings) -> KeyContext:
    """Context used when auth is disabled — personal, unlimited."""
    return KeyContext(
        key_id="personal",
        owner=PERSONAL_OWNER,
        name="personal",
        plan=settings.plan("personal"),
        is_personal=True,
        authenticated=False,
    )


def extract_api_key(request: Request) -> str | None:
    """Read the key from ``X-API-Key`` or ``Authorization: Bearer``."""
    for header in ("x-api-key", "api-key"):
        value = request.headers.get(header)
        if value:
            return value.strip()
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


class RateLimiter:
    """In-process sliding-window limiter.

    Deliberately dependency-free so the service stays portable: one process,
    one file, no Redis. Behind multiple workers/replicas this becomes a
    per-worker limit — multiply by worker count, or front the service with
    nginx/Cloudflare rate limiting if you need a global cap.
    """

    def __init__(self, *, window_seconds: float = 60.0, max_tracked: int = 50_000) -> None:
        self.window = float(window_seconds)
        self.max_tracked = max_tracked
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, identity: str, limit: int) -> tuple[bool, int, int]:
        """Register a hit.

        Returns ``(allowed, remaining, retry_after_seconds)``.
        """
        if limit < 0:
            return True, -1, 0

        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            bucket = self._hits[identity]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = max(1, int(self.window - (now - bucket[0])) + 1)
                return False, 0, retry_after

            bucket.append(now)
            remaining = max(0, limit - len(bucket))

            if len(self._hits) > self.max_tracked:
                self._prune(cutoff)
            return True, remaining, 0

    def _prune(self, cutoff: float) -> None:
        """Drop identities whose window has fully expired (called under lock)."""
        stale = [key for key, bucket in self._hits.items() if not bucket or bucket[-1] <= cutoff]
        for key in stale:
            self._hits.pop(key, None)

    def reset(self, identity: str | None = None) -> None:
        with self._lock:
            if identity is None:
                self._hits.clear()
            else:
                self._hits.pop(identity, None)


def parse_api_key(settings: Settings, storage, secret: str) -> KeyContext:
    """Validate a plaintext key and build its context.

    Raises :class:`AuthError` for unknown/revoked/expired keys.
    """
    record = storage.find_api_key_by_secret(secret)
    if record is None:
        raise AuthError("Invalid API key.", code="invalid_api_key")
    if not record["active"]:
        raise AuthError("This API key has been revoked.", code="key_revoked")

    expires_at = record.get("expires_at")
    if expires_at:
        from datetime import datetime, timezone

        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry < datetime.now(timezone.utc):
                raise AuthError("This API key has expired.", code="key_expired")
        except ValueError:
            pass  # Unparseable expiry is treated as "no expiry".

    plan = settings.plan(record["plan"])
    return KeyContext(
        key_id=record["key_id"],
        owner=record["key_id"],
        name=record["name"],
        plan=plan,
        monthly_quota=record.get("monthly_quota"),
        rate_per_minute=record.get("rate_per_minute"),
    )


def enforce_quota(context: KeyContext, storage) -> int:
    """Raise :class:`QuotaExceeded` when the monthly allowance is used up."""
    used = storage.month_usage(context.key_id)
    if not context.quota_unlimited and used >= context.effective_quota:
        error = QuotaExceeded(
            f"Monthly quota of {context.effective_quota} requests is exhausted. "
            "Upgrade the plan or wait for the next billing month.",
            code="quota_exceeded",
        )
        error.headers = {"X-Quota-Limit": str(context.effective_quota), "X-Quota-Used": str(used)}
        raise error
    return used


def enforce_rate_limit(limiter: RateLimiter, context: KeyContext) -> tuple[int, dict[str, str]]:
    """Apply the per-minute limit and return ``(remaining, headers)``."""
    if context.rate_unlimited:
        return -1, {}

    allowed, remaining, retry_after = limiter.check(context.key_id, context.effective_rate)
    headers = {
        "X-RateLimit-Limit": str(context.effective_rate),
        "X-RateLimit-Remaining": str(remaining),
    }
    if not allowed:
        error = RateLimited(
            f"Rate limit of {context.effective_rate} requests/minute exceeded. "
            f"Retry in {retry_after}s.",
            code="rate_limited",
        )
        error.headers = {**headers, "Retry-After": str(retry_after)}
        raise error
    return remaining, headers


def require_collections(context: KeyContext) -> None:
    if not context.plan.allow_collections:
        raise PlanError(
            f"Face collections are not included in the '{context.plan.name}' plan.",
            code="plan_feature_locked",
        )


def verify_admin_token(settings: Settings, provided: str | None) -> None:
    """Constant-time comparison of the admin token."""
    expected = settings.admin_token or ""
    if not provided or not hmac.compare_digest(provided, expected):
        raise AuthError("Invalid or missing admin token.", code="invalid_admin_token")


def admin_token_from_request(request: Request) -> str | None:
    header = request.headers.get("x-admin-token")
    if header:
        return header.strip()
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None
