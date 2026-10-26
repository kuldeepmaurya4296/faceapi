#!/usr/bin/env python3
"""Face API admin CLI — everything you need without touching the database.

Examples
--------
    python cli.py doctor
    python cli.py serve --port 8000
    python cli.py keys create --name "acme-corp" --plan starter --email ops@acme.com
    python cli.py keys list
    python cli.py keys update key_1a2b3c --plan pro
    python cli.py keys revoke key_1a2b3c
    python cli.py usage key_1a2b3c --month 2026-10
    python cli.py invoices --month 2026-10
    python cli.py stats --days 30
    python cli.py models download
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from app import __version__
from app.config import PLANS, Settings, get_settings
from app.storage import Storage

# --------------------------------------------------------------------- output
GREEN, YELLOW, RED, DIM, BOLD, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def _enable_colour() -> bool:
    return sys.stdout.isatty()


def c(text: str, colour: str) -> str:
    return f"{colour}{text}{RESET}" if _enable_colour() else text


def ok(message: str) -> None:
    print(f"{c('✓', GREEN)} {message}")


def warn(message: str) -> None:
    print(f"{c('!', YELLOW)} {message}")


def fail(message: str) -> None:
    print(f"{c('✗', RED)} {message}", file=sys.stderr)


def table(headers: list[str], rows: list[list[str]]) -> None:
    if not rows:
        print(c("  (nothing here yet)", DIM))
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join(c(h.ljust(widths[i]), BOLD) for i, h in enumerate(headers))
    print(line)
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


def _fmt_quota(value: int | None) -> str:
    if value is None:
        return "unlimited"
    return f"{value:,}" if value >= 0 else "unlimited"


def open_storage(settings: Settings) -> Storage:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return Storage(settings.db_path)


# ------------------------------------------------------------------ commands
def cmd_doctor(args: argparse.Namespace, settings: Settings) -> int:
    print(c(f"Face API v{__version__} — environment check", BOLD))
    print(f"  data dir     : {settings.data_dir}")
    print(f"  models dir   : {settings.models_dir}")

    problems = 0
    try:
        import cv2
        import numpy

        ok(f"OpenCV {cv2.__version__} / numpy {numpy.__version__}")
        for attr in ("FaceDetectorYN", "FaceRecognizerSF"):
            if hasattr(cv2, attr):
                ok(f"cv2.{attr} available")
            else:
                fail(f"cv2.{attr} missing — install opencv-python-headless >= 4.7")
                problems += 1
    except Exception as exc:  # noqa: BLE001
        fail(f"OpenCV import failed: {exc}")
        problems += 1

    for name, path in (
        ("detector", settings.detect_model_path),
        ("recognizer", settings.recog_model_path),
    ):
        if path.exists():
            ok(f"{name} model found: {path.name} ({path.stat().st_size / 1_048_576:.1f} MB)")
        else:
            fail(f"{name} model missing: {path}")
            problems += 1

    try:
        storage = open_storage(settings)
        stats = storage.global_stats(days=30)
        ok(f"database OK: {settings.db_path}")
        print(
            f"    keys: {stats['keys_active']} active / {stats['keys_total']} total, "
            f"requests in last {stats['window_days']}d: {stats['requests']:,}"
        )
        storage.close()
    except Exception as exc:  # noqa: BLE001
        fail(f"database error: {exc}")
        problems += 1

    if settings.auth_enabled:
        warn("auth mode: API key REQUIRED (commercial mode)")
    else:
        ok("auth mode: PERSONAL — no API key needed, unlimited")
    print(f"  admin token  : {settings.load_or_create_admin_token()}")
    print(f"  docs         : {settings.public_base_url.rstrip('/')}/docs")

    if problems:
        fail(f"{problems} problem(s) found — run `python cli.py models download` if models are missing")
        return 1
    ok("everything looks good")
    return 0


def cmd_serve(args: argparse.Namespace, settings: Settings) -> int:
    import uvicorn

    if not settings.detect_model_path.exists() or not settings.recog_model_path.exists():
        warn("models are missing — downloading them first")
        cmd_models(argparse.Namespace(action="download"), settings)

    print(c(f"Face API v{__version__}", BOLD))
    print(f"  auth mode  : {'API key required' if settings.auth_enabled else 'PERSONAL (no key)'}")
    print(f"  admin token: {settings.load_or_create_admin_token()}")
    print(f"  docs       : http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{args.port}/docs")
    print(f"  listening  : http://{args.host}:{args.port}")
    print(c("  Ctrl+C to stop", DIM))

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=None if args.reload else args.workers,
        log_level=settings.log_level.lower(),
    )
    return 0


def cmd_models(args: argparse.Namespace, settings: Settings) -> int:
    from scripts.download_models import download_all

    if args.action != "download":
        fail("usage: python cli.py models download")
        return 2
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    results = download_all(settings.models_dir, force=args.force)
    problems = 0
    for name, path, status in results:
        if status == "ok":
            ok(f"{name}: {path.name} ({path.stat().st_size / 1_048_576:.1f} MB)")
        elif status == "exists":
            ok(f"{name}: already present ({path.name})")
        else:
            fail(f"{name}: {status}")
            problems += 1
    return 1 if problems else 0


def cmd_keys(args: argparse.Namespace, settings: Settings) -> int:
    storage = open_storage(settings)
    try:
        if args.action == "create":
            plan_name = args.plan
            if plan_name not in PLANS:
                fail(f"unknown plan '{plan_name}'. valid: {', '.join(sorted(PLANS))}")
                return 2
            record, secret = storage.create_api_key(
                name=args.name,
                plan=plan_name,
                email=args.email,
                expires_at=args.expires_at,
                monthly_quota=args.quota,
                rate_per_minute=args.rate,
                note=args.note,
            )
            plan = settings.plan(plan_name)
            quota = record["monthly_quota"] if record["monthly_quota"] is not None else plan.monthly_quota
            rate = record["rate_per_minute"] if record["rate_per_minute"] is not None else plan.rate_per_minute
            print(c("API key created — copy it now, it will never be shown again", BOLD))
            print(f"  name        : {record['name']}")
            print(f"  key_id      : {record['key_id']}")
            print(f"  plan        : {plan_name}")
            print(f"  quota/month : {_fmt_quota(quota)}")
            print(f"  rate/minute : {_fmt_quota(rate)}")
            print(f"  expires_at  : {record['expires_at'] or 'never'}")
            print()
            print(f"  {c('API KEY', BOLD)}: {c(secret, GREEN)}")
            print()
            print(c("  Test it:", DIM))
            print(
                f'  curl -H "X-API-Key: {secret}" -F "image=@face.jpg" '
                f"{settings.public_base_url.rstrip('/')}/v1/detect"
            )
            return 0

        if args.action == "list":
            rows = []
            for record in storage.list_api_keys(include_revoked=args.all):
                plan = settings.plan(record["plan"])
                quota = record["monthly_quota"] if record["monthly_quota"] is not None else plan.monthly_quota
                rows.append(
                    [
                        record["key_id"],
                        record["name"][:24],
                        record["plan"],
                        "yes" if record["active"] else c("revoked", RED),
                        _fmt_quota(quota),
                        f"{storage.month_usage(record['key_id']):,}",
                        (record["last_used_at"] or "never")[:16],
                        record["key_prefix"] + "…",
                    ]
                )
            table(
                ["key_id", "name", "plan", "active", "quota/month", "used", "last used", "prefix"],
                rows,
            )
            return 0

        if args.action == "show":
            record = storage.get_api_key(args.key_id)
            if record is None:
                fail(f"key '{args.key_id}' not found")
                return 1
            record = {**record, "month_usage": storage.month_usage(args.key_id)}
            print(json.dumps(record, indent=2))
            return 0

        if args.action == "update":
            fields = {}
            for name in ("name", "email", "plan", "note", "expires_at"):
                value = getattr(args, name, None)
                if value is not None:
                    fields[name] = value
            if args.quota is not None:
                fields["monthly_quota"] = args.quota
            if args.rate is not None:
                fields["rate_per_minute"] = args.rate
            if args.active is not None:
                fields["active"] = 1 if args.active else 0
            if "plan" in fields and fields["plan"] not in PLANS:
                fail(f"unknown plan '{fields['plan']}'")
                return 2
            if not fields:
                warn("nothing to update")
                return 2
            record = storage.update_api_key(args.key_id, **fields)
            ok(f"updated {record['key_id']}: {', '.join(fields)}")
            return 0

        if args.action == "revoke":
            record = storage.revoke_api_key(args.key_id)
            ok(f"revoked {record['key_id']} ({record['name']})")
            return 0

        if args.action == "delete":
            storage.delete_api_key(args.key_id)
            ok(f"deleted {args.key_id} (usage history kept for accounting)")
            return 0

    finally:
        storage.close()

    fail("unknown keys action")
    return 2


def cmd_usage(args: argparse.Namespace, settings: Settings) -> int:
    storage = open_storage(settings)
    try:
        if args.key_id:
            summary = storage.usage_summary(args.key_id, month=args.month)
            if args.json:
                print(json.dumps(summary, indent=2))
                return 0
            print(c(f"Usage for {args.key_id} — {summary['month']}", BOLD))
            print(f"  requests: {summary['requests']:,}   faces: {summary['faces']:,}   errors: {summary['errors']:,}")
            print()
            table(
                ["endpoint", "requests", "faces", "avg ms", "errors"],
                [
                    [
                        row["endpoint"],
                        f"{row['requests']:,}",
                        f"{row['faces'] or 0:,}",
                        f"{row['avg_latency_ms'] or 0:.1f}",
                        f"{row['errors'] or 0:,}",
                    ]
                    for row in summary["by_endpoint"]
                ],
            )
            print()
            table(
                ["day", "requests", "faces"],
                [[row["day"], f"{row['requests']:,}", f"{row['faces'] or 0:,}"] for row in summary["by_day"]],
            )
            return 0

        stats = storage.global_stats(days=args.days)
        if args.json:
            print(json.dumps(stats, indent=2))
            return 0
        print(c(f"Service usage — last {stats['window_days']} days", BOLD))
        print(
            f"  requests: {stats['requests']:,}   faces: {stats['faces']:,}   "
            f"active keys: {stats['active_keys_in_window']}   "
            f"({stats['keys_active']} active / {stats['keys_total']} total)"
        )
        print()
        table(
            ["day", "requests", "faces"],
            [[row["day"], f"{row['requests']:,}", f"{row['faces'] or 0:,}"] for row in stats["by_day"]],
        )
        return 0
    finally:
        storage.close()


def cmd_invoices(args: argparse.Namespace, settings: Settings) -> int:
    storage = open_storage(settings)
    try:
        month = args.month or datetime.now(timezone.utc).strftime("%Y-%m")
        lines = storage.invoice_lines(month=month, plans=PLANS)
        if args.json:
            print(json.dumps({"month": month, "lines": lines}, indent=2))
            return 0
        print(c(f"Billable usage — {month}", BOLD))
        table(
            ["customer", "plan", "requests", "included", "overage", "base $", "overage $", "total $"],
            [
                [
                    (line["customer"] or "")[:20],
                    line["plan"],
                    f"{line['requests']:,}",
                    _fmt_quota(line["included_requests"]),
                    f"{line['overage_requests']:,}",
                    f"{line['base_usd']:.2f}",
                    f"{line['overage_usd']:.2f}",
                    c(f"{line['total_usd']:.2f}", GREEN),
                ]
                for line in lines
            ],
        )
        total_usd = sum(line["total_usd"] for line in lines)
        total_requests = sum(line["requests"] for line in lines)
        print()
        print(
            f"  {c('TOTAL', BOLD)}: {len(lines)} customers, "
            f"{total_requests:,} requests, {c(f'${total_usd:.2f}', GREEN)}"
        )
        return 0
    finally:
        storage.close()


def cmd_token(args: argparse.Namespace, settings: Settings) -> int:
    print(settings.load_or_create_admin_token())
    return 0


# ---------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Face API — admin CLI (keys, usage, invoices, serving)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--version", action="version", version=f"Face API {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser("doctor", help="verify models, database and dependencies")
    p_doctor.set_defaults(func=cmd_doctor)

    p_serve = sub.add_parser("serve", help="run the API server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--workers", type=int, default=1)
    p_serve.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")
    p_serve.set_defaults(func=cmd_serve)

    p_models = sub.add_parser("models", help="manage ONNX models")
    p_models.add_argument("action", choices=["download"])
    p_models.add_argument("--force", action="store_true")
    p_models.set_defaults(func=cmd_models)

    p_keys = sub.add_parser("keys", help="issue and manage customer API keys")
    keys_sub = p_keys.add_subparsers(dest="action", required=True)

    k_create = keys_sub.add_parser("create", help="create a key (secret shown once)")
    k_create.add_argument("--name", required=True)
    k_create.add_argument("--plan", default="starter", choices=sorted(PLANS))
    k_create.add_argument("--email")
    k_create.add_argument("--expires-at", dest="expires_at", help="ISO-8601, e.g. 2027-01-31T00:00:00Z")
    k_create.add_argument("--quota", type=int, help="override monthly request quota (-1 = unlimited)")
    k_create.add_argument("--rate", type=int, help="override per-minute rate limit (-1 = unlimited)")
    k_create.add_argument("--note")

    k_list = keys_sub.add_parser("list", help="list keys")
    k_list.add_argument("--all", action="store_true", help="include revoked keys")

    k_show = keys_sub.add_parser("show", help="show one key as JSON")
    k_show.add_argument("key_id")

    k_update = keys_sub.add_parser("update", help="change plan, limits or status")
    k_update.add_argument("key_id")
    k_update.add_argument("--name")
    k_update.add_argument("--email")
    k_update.add_argument("--plan", choices=sorted(PLANS))
    k_update.add_argument("--quota", type=int)
    k_update.add_argument("--rate", type=int)
    k_update.add_argument("--note")
    k_update.add_argument("--expires-at", dest="expires_at")
    k_update.add_argument("--active", dest="active", action="store_true", default=None)
    k_update.add_argument("--inactive", dest="active", action="store_false")

    k_revoke = keys_sub.add_parser("revoke", help="revoke a key immediately")
    k_revoke.add_argument("key_id")

    k_delete = keys_sub.add_parser("delete", help="delete a key (usage history kept)")
    k_delete.add_argument("key_id")

    p_keys.set_defaults(func=cmd_keys)

    p_usage = sub.add_parser("usage", help="usage report (per key or service-wide)")
    p_usage.add_argument("key_id", nargs="?")
    p_usage.add_argument("--month", help="YYYY-MM")
    p_usage.add_argument("--days", type=int, default=30, help="window for the service-wide report")
    p_usage.add_argument("--json", action="store_true")
    p_usage.set_defaults(func=cmd_usage)

    p_inv = sub.add_parser("invoices", help="billable usage per customer for a month")
    p_inv.add_argument("--month", help="YYYY-MM")
    p_inv.add_argument("--json", action="store_true")
    p_inv.set_defaults(func=cmd_invoices)

    p_token = sub.add_parser("admin-token", help="print the admin token")
    p_token.set_defaults(func=cmd_token)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()
    try:
        return int(args.func(args, settings) or 0)
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
