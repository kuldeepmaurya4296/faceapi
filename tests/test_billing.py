"""Billing correctness — the numbers you would actually invoice on.

These run against the storage layer directly so they can assert exact amounts
without generating thousands of HTTP calls.
"""

from __future__ import annotations

import pytest

from app.config import PLANS
from app.storage import Storage

STARTER = PLANS["starter"]  # $19/month, 25,000 requests, $0.60 per 1,000 over


@pytest.fixture
def storage(tmp_path) -> Storage:
    store = Storage(tmp_path / "billing.db")
    yield store
    store.close()


def _record(store: Storage, key_id: str, count: int, *, endpoint: str = "/v1/detect", faces: int = 1, billable: bool = True):
    for _ in range(count):
        store.record_usage(
            key_id=key_id,
            endpoint=endpoint,
            method="POST",
            status_code=200,
            faces=faces,
            latency_ms=12.5,
            client_ip="203.0.113.7",
            billable=billable,
        )


def _insert_for_month(store: Storage, key_id: str, month: str, count: int):
    """Backdate usage so month-boundary logic can be tested."""
    for _ in range(count):
        store._execute(
            """
            INSERT INTO usage_events (key_id, ts, day, month, endpoint, method,
                                      status_code, faces, latency_ms, client_ip, billable)
            VALUES (?,?,?,?,?,?,?,?,?,?,1)
            """,
            (key_id, f"{month}-05T10:00:00+00:00", f"{month}-05", month, "/v1/detect", "POST", 200, 1, 9.0, None),
        )


def test_overage_is_charged_per_thousand_requests(storage: Storage):
    record, _ = storage.create_api_key(name="acme", plan="starter", monthly_quota=1000)
    _record(storage, record["key_id"], 1250)

    line = next(line for line in storage.invoice_lines(plans=PLANS) if line["key_id"] == record["key_id"])
    assert line["requests"] == 1250
    assert line["included_requests"] == 1000
    assert line["overage_requests"] == 250
    assert line["base_usd"] == 19.0
    assert line["overage_usd"] == round(250 / 1000 * STARTER.overage_per_1000_usd, 2)  # 0.15
    assert line["total_usd"] == 19.15


def test_customer_within_allowance_pays_only_the_plan_price(storage: Storage):
    record, _ = storage.create_api_key(name="small", plan="starter", monthly_quota=1000)
    _record(storage, record["key_id"], 900)
    line = next(line for line in storage.invoice_lines(plans=PLANS) if line["key_id"] == record["key_id"])
    assert line["overage_requests"] == 0
    assert line["overage_usd"] == 0.0
    assert line["total_usd"] == 19.0


def test_unlimited_plan_never_shows_overage(storage: Storage):
    record, _ = storage.create_api_key(name="self", plan="personal")
    _record(storage, record["key_id"], 500)
    line = next(line for line in storage.invoice_lines(plans=PLANS) if line["key_id"] == record["key_id"])
    assert line["included_requests"] == -1
    assert line["overage_requests"] == 0
    assert line["total_usd"] == 0.0


def test_non_billable_events_are_excluded(storage: Storage):
    record, _ = storage.create_api_key(name="freebie", plan="starter", monthly_quota=100)
    _record(storage, record["key_id"], 40, billable=True)
    _record(storage, record["key_id"], 60, billable=False)
    assert storage.month_usage(record["key_id"]) == 40

    summary = storage.usage_summary(record["key_id"])
    assert summary["requests"] == 100  # the ledger still shows the traffic

    line = next(line for line in storage.invoice_lines(plans=PLANS) if line["key_id"] == record["key_id"])
    assert line["requests"] == 40


def test_usage_is_scoped_to_the_billing_month(storage: Storage):
    record, _ = storage.create_api_key(name="monthly", plan="starter", monthly_quota=100)
    _insert_for_month(storage, record["key_id"], "2026-08", 30)
    _insert_for_month(storage, record["key_id"], "2026-09", 7)

    assert storage.month_usage(record["key_id"], month="2026-08") == 30
    assert storage.month_usage(record["key_id"], month="2026-09") == 7

    august = storage.usage_summary(record["key_id"], month="2026-08")
    assert august["requests"] == 30
    assert august["faces"] == 30


def test_usage_summary_breaks_down_by_endpoint_and_day(storage: Storage):
    record, _ = storage.create_api_key(name="mixed", plan="pro")
    key_id = record["key_id"]
    _record(storage, key_id, 3, endpoint="/v1/detect", faces=2)
    _record(storage, key_id, 2, endpoint="/v1/verify", faces=4)

    summary = storage.usage_summary(key_id)
    assert summary["requests"] == 5
    assert summary["faces"] == 3 * 2 + 2 * 4

    by_endpoint = {row["endpoint"]: row for row in summary["by_endpoint"]}
    assert by_endpoint["/v1/detect"]["requests"] == 3
    assert by_endpoint["/v1/detect"]["faces"] == 6
    assert by_endpoint["/v1/verify"]["requests"] == 2
    assert len(summary["by_day"]) == 1


def test_errors_are_counted_but_still_billable(storage: Storage):
    record, _ = storage.create_api_key(name="error-prone", plan="starter")
    key_id = record["key_id"]
    storage.record_usage(key_id=key_id, endpoint="/v1/detect", method="POST", status_code=200, faces=1)
    storage.record_usage(key_id=key_id, endpoint="/v1/detect", method="POST", status_code=422, faces=0)

    summary = storage.usage_summary(key_id)
    assert summary["requests"] == 2
    assert summary["errors"] == 1


def test_purge_old_usage_keeps_recent_events(storage: Storage):
    record, _ = storage.create_api_key(name="cleanup", plan="starter")
    _insert_for_month(storage, record["key_id"], "2025-01", 5)
    _record(storage, record["key_id"], 4)

    removed = storage.purge_usage_before("2026-01-01T00:00:00+00:00")
    assert removed == 5
    assert storage.month_usage(record["key_id"]) == 4


def test_plans_are_priced_consistently():
    """Guard rails so a typo cannot publish a nonsensical price list."""
    for name, plan in PLANS.items():
        assert plan.price_usd_month >= 0
        assert plan.overage_per_1000_usd >= 0
        if plan.monthly_quota > 0 and name not in ("trial", "personal"):
            assert plan.rate_per_minute > 0
        assert plan.max_upload_mb > 0
        assert plan.max_faces_per_image > 0
