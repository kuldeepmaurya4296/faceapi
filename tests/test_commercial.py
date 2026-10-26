"""API tests in COMMERCIAL mode — this is what your paying customers see."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def _file(data: bytes, name: str = "face.jpg", mime: str = "image/jpeg"):
    return {"image": (name, data, mime)}


# ------------------------------------------------------------------ auth gate
def test_missing_api_key_is_rejected(commercial_client: TestClient, assets):
    response = commercial_client.post("/v1/detect", files=_file(assets["person_a_1"]))
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "missing_api_key"
    assert "X-API-Key" in body["error"]["message"]


def test_invalid_api_key_is_rejected(commercial_client: TestClient, assets):
    response = commercial_client.post(
        "/v1/detect", files=_file(assets["person_a_1"]), headers={"X-API-Key": "fk_live_nope"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"


def test_openapi_endpoints_do_not_need_a_key(commercial_client: TestClient):
    assert commercial_client.get("/healthz").status_code == 200
    assert commercial_client.get("/").status_code == 200


def test_valid_key_allows_access(commercial_client: TestClient, assets, make_key, key_headers):
    created = make_key(name="acme", plan="starter")
    response = commercial_client.post(
        "/v1/detect", files=_file(assets["person_a_1"]), headers=key_headers(created["api_key"])
    )
    assert response.status_code == 200, response.text
    assert response.json()["usage"]["plan"] == "starter"
    assert response.headers["X-RateLimit-Limit"] == "60"
    assert int(response.headers["X-RateLimit-Remaining"]) <= 60


def test_bearer_authorization_header_works(commercial_client: TestClient, assets, make_key):
    created = make_key(name="bearer-user")
    response = commercial_client.post(
        "/v1/detect",
        files=_file(assets["person_a_1"]),
        headers={"Authorization": f"Bearer {created['api_key']}"},
    )
    assert response.status_code == 200


def test_revoked_key_stops_working(commercial_client: TestClient, assets, make_key, key_headers, admin_headers):
    created = make_key(name="to-be-revoked")
    headers = key_headers(created["api_key"])
    assert commercial_client.post("/v1/detect", files=_file(assets["person_a_1"]), headers=headers).status_code == 200

    commercial_client.post(f"/admin/keys/{created['key_id']}/revoke", headers=admin_headers)
    response = commercial_client.post("/v1/detect", files=_file(assets["person_a_1"]), headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "key_revoked"


def test_expired_key_is_rejected(commercial_client: TestClient, assets, make_key, key_headers):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    created = make_key(name="expired", expires_at=past)
    response = commercial_client.post(
        "/v1/detect", files=_file(assets["person_a_1"]), headers=key_headers(created["api_key"])
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "key_expired"


# -------------------------------------------------------------------- quotas
def test_monthly_quota_is_enforced(commercial_client: TestClient, assets, make_key, key_headers):
    created = make_key(name="tiny-quota", plan="trial", monthly_quota=2)
    headers = key_headers(created["api_key"])

    first = commercial_client.post("/v1/detect", files=_file(assets["person_a_1"]), headers=headers)
    second = commercial_client.post("/v1/detect", files=_file(assets["person_a_1"]), headers=headers)
    third = commercial_client.post("/v1/detect", files=_file(assets["person_a_1"]), headers=headers)

    assert first.status_code == 200 and second.status_code == 200
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "quota_exceeded"
    assert third.headers["X-Quota-Limit"] == "2"


def test_rate_limit_is_enforced(commercial_client: TestClient, assets, make_key, key_headers):
    created = make_key(name="fast-caller", plan="trial", rate_per_minute=3, monthly_quota=1000)
    headers = key_headers(created["api_key"])

    statuses = [
        commercial_client.post("/v1/detect", files=_file(assets["person_a_1"]), headers=headers).status_code
        for _ in range(4)
    ]
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3] == 429

    blocked = commercial_client.post("/v1/detect", files=_file(assets["person_a_1"]), headers=headers)
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["Retry-After"]) >= 1


def test_unlimited_personal_plan_key_has_no_rate_headers(commercial_client: TestClient, assets, make_key, key_headers):
    created = make_key(name="self", plan="personal")
    response = commercial_client.post(
        "/v1/detect", files=_file(assets["person_a_1"]), headers=key_headers(created["api_key"])
    )
    assert response.status_code == 200
    assert "X-RateLimit-Limit" not in response.headers
    assert response.json()["usage"]["monthly_quota"] is None


def test_trial_plan_cannot_use_collections(commercial_client: TestClient, make_key, key_headers):
    created = make_key(name="trial-user", plan="trial")
    response = commercial_client.post(
        "/v1/collections", json={"name": "gallery"}, headers=key_headers(created["api_key"])
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "plan_feature_locked"


# ------------------------------------------------------------------ accounting
def test_usage_is_metered_per_key(commercial_client: TestClient, assets, make_key, key_headers, admin_headers):
    created = make_key(name="metered-customer")
    headers = key_headers(created["api_key"])

    for _ in range(3):
        commercial_client.post("/v1/detect", files=_file(assets["person_a_1"]), headers=headers)

    usage = commercial_client.get(f"/admin/usage/{created['key_id']}", headers=admin_headers).json()
    assert usage["requests"] == 3
    assert usage["faces"] == 3
    assert usage["by_endpoint"][0]["endpoint"] == "/v1/detect"

    mine = commercial_client.get("/v1/me", headers=headers).json()
    assert mine["usage"]["requests"] == 3
    assert mine["key"]["month_usage"] == 3


def test_admin_calls_are_not_billed(commercial_client: TestClient, admin_headers):
    before = commercial_client.get("/admin/stats", headers=admin_headers).json()["requests"]
    for _ in range(3):
        commercial_client.get("/admin/keys", headers=admin_headers)
    after = commercial_client.get("/admin/stats", headers=admin_headers).json()["requests"]
    assert after == before


def test_invoices_summarise_billable_usage(commercial_client: TestClient, assets, make_key, key_headers, admin_headers):
    created = make_key(name="invoice-customer", plan="starter", monthly_quota=5)
    headers = key_headers(created["api_key"])
    for _ in range(2):
        commercial_client.post("/v1/detect", files=_file(assets["person_a_1"]), headers=headers)

    # The operator later lowers the allowance (plan correction / downgrade), so the
    # month's billable usage now exceeds what the plan included.
    commercial_client.patch(
        f"/admin/keys/{created['key_id']}", json={"monthly_quota": 1}, headers=admin_headers
    )

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    report = commercial_client.get("/admin/invoices", params={"month": month}, headers=admin_headers).json()
    assert report["month"] == month
    line = next(item for item in report["lines"] if item["key_id"] == created["key_id"])
    assert line["requests"] == 2
    assert line["included_requests"] == 1
    assert line["overage_requests"] == 1
    assert line["base_usd"] == 19.0
    # Overage is priced per 1,000 extra requests, so one extra request is a rounding error.
    assert line["overage_usd"] == round(1 / 1000 * 0.6, 2)
    assert line["total_usd"] == round(19.0 + 1 / 1000 * 0.6, 2)
    assert report["totals"]["customers"] >= 1


# ----------------------------------------------------------------------- admin
def test_admin_requires_the_admin_token(commercial_client: TestClient):
    assert commercial_client.get("/admin/keys").status_code == 401
    assert commercial_client.get("/admin/keys", headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert commercial_client.get("/admin/stats").status_code == 401


def test_admin_key_lifecycle(commercial_client: TestClient, admin_headers):
    created = commercial_client.post(
        "/admin/keys",
        json={"name": "lifecycle", "plan": "starter", "email": "ops@example.com", "note": "trial pilot"},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    key_id = body["key_id"]
    assert body["api_key"].startswith("fk_live_")
    assert "cannot be recovered" in body["warning"]

    fetched = commercial_client.get(f"/admin/keys/{key_id}", headers=admin_headers).json()
    assert fetched["name"] == "lifecycle"
    assert fetched["active"] is True
    assert fetched["key_prefix"] == body["api_key"][:18]

    listed = commercial_client.get("/admin/keys", headers=admin_headers).json()
    assert any(item["key_id"] == key_id for item in listed["keys"])

    upgraded = commercial_client.patch(
        f"/admin/keys/{key_id}", json={"plan": "pro", "rate_per_minute": 999}, headers=admin_headers
    ).json()
    assert upgraded["plan"] == "pro"
    assert upgraded["rate_per_minute"] == 999

    revoked = commercial_client.post(f"/admin/keys/{key_id}/revoke", headers=admin_headers).json()
    assert revoked["active"] is False
    assert revoked["revoked_at"]

    # Revoked keys disappear from the default listing but stay visible with --all.
    assert not any(
        item["key_id"] == key_id
        for item in commercial_client.get("/admin/keys", headers=admin_headers).json()["keys"]
    )
    assert any(
        item["key_id"] == key_id
        for item in commercial_client.get(
            "/admin/keys", params={"include_revoked": True}, headers=admin_headers
        ).json()["keys"]
    )

    assert commercial_client.delete(f"/admin/keys/{key_id}", headers=admin_headers).status_code == 200
    assert commercial_client.get(f"/admin/keys/{key_id}", headers=admin_headers).status_code == 404


def test_admin_rejects_unknown_plan(commercial_client: TestClient, admin_headers):
    response = commercial_client.post(
        "/admin/keys", json={"name": "bad-plan", "plan": "platinum"}, headers=admin_headers
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_plan"


def test_admin_rejects_bad_expiry(commercial_client: TestClient, admin_headers):
    response = commercial_client.post(
        "/admin/keys", json={"name": "bad-expiry", "expires_at": "next tuesday"}, headers=admin_headers
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_expiry"


def test_admin_stats_shape(commercial_client: TestClient, admin_headers):
    stats = commercial_client.get("/admin/stats", params={"days": 7}, headers=admin_headers).json()
    assert stats["window_days"] == 7
    assert {"requests", "faces", "keys_total", "keys_active", "by_day"} <= set(stats)


def test_missing_key_id_returns_404(commercial_client: TestClient, admin_headers):
    assert commercial_client.get("/admin/keys/key_does_not_exist", headers=admin_headers).status_code == 404
