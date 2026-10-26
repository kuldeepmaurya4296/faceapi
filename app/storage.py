"""SQLite persistence: API keys, usage events and face collections.

SQLite keeps the whole service in **one file**, which is what makes it portable:
copy ``data/faceapi.db`` and you have moved every customer, key and gallery.
All writes go through one lock (SQLite is fast for this workload) and WAL mode
keeps readers unblocked.

Embedding search is a numpy brute-force cosine scan over the gallery. That is
comfortably fast into the tens of thousands of faces per collection; above that,
swop this one method for ``sqlite-vec``/FAISS/Qdrant — the REST contract does
not change.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .errors import Conflict, NotFound

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS api_keys (
    key_id          TEXT PRIMARY KEY,
    key_hash        TEXT NOT NULL UNIQUE,
    key_prefix      TEXT NOT NULL,
    name            TEXT NOT NULL,
    email           TEXT,
    plan            TEXT NOT NULL,
    active          INTEGER NOT NULL DEFAULT 1,
    monthly_quota   INTEGER,
    rate_per_minute INTEGER,
    created_at      TEXT NOT NULL,
    expires_at      TEXT,
    last_used_at    TEXT,
    revoked_at      TEXT,
    note            TEXT
);

CREATE TABLE IF NOT EXISTS usage_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id      TEXT NOT NULL,
    ts          TEXT NOT NULL,
    day         TEXT NOT NULL,
    month       TEXT NOT NULL,
    endpoint    TEXT NOT NULL,
    method      TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    faces       INTEGER NOT NULL DEFAULT 0,
    latency_ms  REAL NOT NULL DEFAULT 0,
    client_ip   TEXT,
    billable    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_usage_key_month ON usage_events(key_id, month);
CREATE INDEX IF NOT EXISTS idx_usage_key_day   ON usage_events(key_id, day);
CREATE INDEX IF NOT EXISTS idx_usage_ts        ON usage_events(ts);

CREATE TABLE IF NOT EXISTS collections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner       TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE(owner, name)
);

CREATE TABLE IF NOT EXISTS collection_faces (
    id            TEXT PRIMARY KEY,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    external_id   TEXT,
    embedding     BLOB NOT NULL,
    det_score     REAL,
    box           TEXT,
    metadata      TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_faces_collection ON collection_faces(collection_id);
CREATE INDEX IF NOT EXISTS idx_faces_external   ON collection_faces(collection_id, external_id);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


class Storage:
    """Everything that touches the database."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------- internals
    def _execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cursor

    def _query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, tuple(params)).fetchall())

    def _query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    # ------------------------------------------------------------- API keys
    @staticmethod
    def hash_key(secret: str) -> str:
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    def create_api_key(
        self,
        *,
        name: str,
        plan: str,
        email: str | None = None,
        expires_at: str | None = None,
        monthly_quota: int | None = None,
        rate_per_minute: int | None = None,
        note: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Create a key. The plaintext secret is returned **once** and never stored."""
        key_id = "key_" + secrets.token_hex(8)
        secret = "fk_live_" + secrets.token_urlsafe(24)
        now = iso(utcnow())
        self._execute(
            """
            INSERT INTO api_keys (key_id, key_hash, key_prefix, name, email, plan, active,
                                  monthly_quota, rate_per_minute, created_at, expires_at, note)
            VALUES (?,?,?,?,?,?,1,?,?,?,?,?)
            """,
            (
                key_id,
                self.hash_key(secret),
                secret[:18],
                name,
                email,
                plan,
                monthly_quota,
                rate_per_minute,
                now,
                expires_at,
                note,
            ),
        )
        record = self.get_api_key(key_id)
        assert record is not None
        return record, secret

    def get_api_key(self, key_id: str) -> dict[str, Any] | None:
        row = self._query_one("SELECT * FROM api_keys WHERE key_id = ?", (key_id,))
        return dict(row) if row else None

    def find_api_key_by_secret(self, secret: str) -> dict[str, Any] | None:
        digest = self.hash_key(secret)
        row = self._query_one("SELECT * FROM api_keys WHERE key_hash = ?", (digest,))
        if row is None:
            # Constant-time-ish guard against timing oracles on the id lookup.
            hmac.compare_digest(digest, digest)
            return None
        if not hmac.compare_digest(row["key_hash"], digest):  # pragma: no cover
            return None
        return dict(row)

    def list_api_keys(self, *, include_revoked: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM api_keys"
        if not include_revoked:
            sql += " WHERE active = 1"
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in self._query(sql)]

    def update_api_key(self, key_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {"name", "email", "plan", "active", "monthly_quota", "rate_per_minute", "note", "expires_at"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if updates:
            assignments = ", ".join(f"{k} = ?" for k in updates)
            self._execute(
                f"UPDATE api_keys SET {assignments} WHERE key_id = ?",
                (*updates.values(), key_id),
            )
        record = self.get_api_key(key_id)
        if record is None:
            raise NotFound(f"API key '{key_id}' not found.")
        return record

    def revoke_api_key(self, key_id: str) -> dict[str, Any]:
        now = iso(utcnow())
        cursor = self._execute(
            "UPDATE api_keys SET active = 0, revoked_at = ? WHERE key_id = ?", (now, key_id)
        )
        if cursor.rowcount == 0:
            raise NotFound(f"API key '{key_id}' not found.")
        record = self.get_api_key(key_id)
        assert record is not None
        return record

    def delete_api_key(self, key_id: str) -> None:
        """Hard-delete a key. Usage history is kept for accounting."""
        cursor = self._execute("DELETE FROM api_keys WHERE key_id = ?", (key_id,))
        if cursor.rowcount == 0:
            raise NotFound(f"API key '{key_id}' not found.")

    def touch_api_key(self, key_id: str) -> None:
        self._execute("UPDATE api_keys SET last_used_at = ? WHERE key_id = ?", (iso(utcnow()), key_id))

    # --------------------------------------------------------------- usage
    def record_usage(
        self,
        *,
        key_id: str,
        endpoint: str,
        method: str,
        status_code: int,
        faces: int = 0,
        latency_ms: float = 0.0,
        client_ip: str | None = None,
        billable: bool = True,
    ) -> None:
        now = utcnow()
        self._execute(
            """
            INSERT INTO usage_events (key_id, ts, day, month, endpoint, method,
                                      status_code, faces, latency_ms, client_ip, billable)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                key_id,
                iso(now),
                now.strftime("%Y-%m-%d"),
                now.strftime("%Y-%m"),
                endpoint,
                method,
                int(status_code),
                int(faces),
                float(latency_ms),
                client_ip,
                1 if billable else 0,
            ),
        )

    def month_usage(self, key_id: str, month: str | None = None) -> int:
        month = month or utcnow().strftime("%Y-%m")
        row = self._query_one(
            "SELECT COUNT(*) AS n FROM usage_events WHERE key_id = ? AND month = ? AND billable = 1",
            (key_id, month),
        )
        return int(row["n"]) if row else 0

    def usage_summary(self, key_id: str, *, month: str | None = None) -> dict[str, Any]:
        month = month or utcnow().strftime("%Y-%m")
        by_endpoint = [
            dict(r)
            for r in self._query(
                """
                SELECT endpoint, COUNT(*) AS requests, SUM(faces) AS faces,
                       AVG(latency_ms) AS avg_latency_ms,
                       SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS errors
                FROM usage_events
                WHERE key_id = ? AND month = ?
                GROUP BY endpoint ORDER BY requests DESC
                """,
                (key_id, month),
            )
        ]
        by_day = [
            dict(r)
            for r in self._query(
                """
                SELECT day, COUNT(*) AS requests, SUM(faces) AS faces
                FROM usage_events WHERE key_id = ? AND month = ?
                GROUP BY day ORDER BY day
                """,
                (key_id, month),
            )
        ]
        totals = self._query_one(
            """
            SELECT COUNT(*) AS requests, COALESCE(SUM(faces),0) AS faces,
                   SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS errors
            FROM usage_events WHERE key_id = ? AND month = ?
            """,
            (key_id, month),
        )
        return {
            "key_id": key_id,
            "month": month,
            "requests": int(totals["requests"]) if totals else 0,
            "faces": int(totals["faces"]) if totals else 0,
            "errors": int(totals["errors"]) if totals else 0,
            "by_endpoint": by_endpoint,
            "by_day": by_day,
        }

    def global_stats(self, *, days: int = 30) -> dict[str, Any]:
        since = iso(utcnow() - timedelta(days=days))
        totals = self._query_one(
            """
            SELECT COUNT(*) AS requests, COALESCE(SUM(faces),0) AS faces,
                   COUNT(DISTINCT key_id) AS active_keys
            FROM usage_events WHERE ts >= ?
            """,
            (since,),
        )
        by_day = [
            dict(r)
            for r in self._query(
                """
                SELECT day, COUNT(*) AS requests, SUM(faces) AS faces
                FROM usage_events WHERE ts >= ?
                GROUP BY day ORDER BY day
                """,
                (since,),
            )
        ]
        keys = self._query_one(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN active = 1 THEN 1 ELSE 0 END) AS active FROM api_keys"
        )
        return {
            "window_days": days,
            "requests": int(totals["requests"]) if totals else 0,
            "faces": int(totals["faces"]) if totals else 0,
            "active_keys_in_window": int(totals["active_keys"]) if totals else 0,
            "keys_total": int(keys["total"]) if keys else 0,
            "keys_active": int(keys["active"] or 0) if keys else 0,
            "by_day": by_day,
        }

    def invoice_lines(self, *, month: str | None = None, plans: dict[str, Any]) -> list[dict[str, Any]]:
        """Per-customer usage for one month, ready to turn into invoices."""
        month = month or utcnow().strftime("%Y-%m")
        rows = self._query(
            """
            SELECT k.key_id, k.name, k.email, k.plan, k.monthly_quota, k.active,
                   COUNT(u.id) AS requests
            FROM api_keys k
            LEFT JOIN usage_events u
                   ON u.key_id = k.key_id AND u.month = ? AND u.billable = 1
            GROUP BY k.key_id
            ORDER BY requests DESC
            """,
            (month,),
        )
        lines: list[dict[str, Any]] = []
        for row in rows:
            plan = plans.get(row["plan"], plans.get("starter"))
            included = row["monthly_quota"]
            if included is None:
                included = plan.monthly_quota
            requests = int(row["requests"] or 0)
            overage = max(0, requests - included) if included is not None and included >= 0 else 0
            lines.append(
                {
                    "key_id": row["key_id"],
                    "customer": row["name"],
                    "email": row["email"],
                    "plan": row["plan"],
                    "active": bool(row["active"]),
                    "requests": requests,
                    "included_requests": included,
                    "overage_requests": overage,
                    "base_usd": round(plan.price_usd_month, 2),
                    "overage_usd": round(overage / 1000.0 * plan.overage_per_1000_usd, 2),
                    "total_usd": round(
                        plan.price_usd_month + overage / 1000.0 * plan.overage_per_1000_usd, 2
                    ),
                }
            )
        return lines

    def purge_usage_before(self, cutoff_iso: str) -> int:
        cursor = self._execute("DELETE FROM usage_events WHERE ts < ?", (cutoff_iso,))
        return cursor.rowcount or 0

    # --------------------------------------------------------- collections
    def create_collection(self, owner: str, name: str, description: str | None = None) -> dict[str, Any]:
        try:
            self._execute(
                "INSERT INTO collections (owner, name, description, created_at) VALUES (?,?,?,?)",
                (owner, name, description, iso(utcnow())),
            )
        except sqlite3.IntegrityError as exc:
            raise Conflict(f"Collection '{name}' already exists.") from exc
        record = self.get_collection(owner, name)
        assert record is not None
        return record

    def get_collection(self, owner: str, name: str) -> dict[str, Any] | None:
        row = self._query_one(
            """
            SELECT c.*, (SELECT COUNT(*) FROM collection_faces f WHERE f.collection_id = c.id) AS face_count
            FROM collections c WHERE c.owner = ? AND c.name = ?
            """,
            (owner, name),
        )
        return dict(row) if row else None

    def get_collection_or_404(self, owner: str, name: str) -> dict[str, Any]:
        record = self.get_collection(owner, name)
        if record is None:
            raise NotFound(f"Collection '{name}' not found.")
        return record

    def list_collections(self, owner: str) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self._query(
                """
                SELECT c.*, (SELECT COUNT(*) FROM collection_faces f WHERE f.collection_id = c.id) AS face_count
                FROM collections c WHERE c.owner = ? ORDER BY c.name
                """,
                (owner,),
            )
        ]

    def delete_collection(self, owner: str, name: str) -> None:
        record = self.get_collection(owner, name)
        if record is None:
            raise NotFound(f"Collection '{name}' not found.")
        self._execute("DELETE FROM collection_faces WHERE collection_id = ?", (record["id"],))
        self._execute("DELETE FROM collections WHERE id = ?", (record["id"],))

    def add_face(
        self,
        *,
        owner: str,
        collection: str,
        embedding: np.ndarray,
        external_id: str | None = None,
        det_score: float | None = None,
        box: tuple[int, int, int, int] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        coll = self.get_collection_or_404(owner, collection)
        face_id = uuid.uuid4().hex
        vector = np.asarray(embedding, dtype=np.float32).ravel()
        self._execute(
            """
            INSERT INTO collection_faces (id, collection_id, external_id, embedding, det_score, box, metadata, created_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                face_id,
                coll["id"],
                external_id,
                vector.tobytes(),
                det_score,
                json.dumps(box) if box else None,
                json.dumps(metadata) if metadata else None,
                iso(utcnow()),
            ),
        )
        record = self.get_face(owner, collection, face_id)
        assert record is not None
        return record

    def get_face(self, owner: str, collection: str, face_id: str) -> dict[str, Any] | None:
        coll = self.get_collection_or_404(owner, collection)
        row = self._query_one(
            "SELECT * FROM collection_faces WHERE id = ? AND collection_id = ?",
            (face_id, coll["id"]),
        )
        return self._face_row_to_dict(row) if row else None

    def list_faces(self, owner: str, collection: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        coll = self.get_collection_or_404(owner, collection)
        rows = self._query(
            """
            SELECT * FROM collection_faces WHERE collection_id = ?
            ORDER BY created_at DESC LIMIT ? OFFSET ?
            """,
            (coll["id"], limit, offset),
        )
        return [self._face_row_to_dict(r) for r in rows]

    def delete_face(self, owner: str, collection: str, face_id: str) -> None:
        coll = self.get_collection_or_404(owner, collection)
        cursor = self._execute(
            "DELETE FROM collection_faces WHERE id = ? AND collection_id = ?", (face_id, coll["id"])
        )
        if cursor.rowcount == 0:
            raise NotFound(f"Face '{face_id}' not found in collection '{collection}'.")

    def search_faces(
        self,
        *,
        owner: str,
        collection: str,
        embedding: np.ndarray,
        top_k: int = 5,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Brute-force cosine search inside one customer's gallery."""
        coll = self.get_collection_or_404(owner, collection)
        rows = self._query(
            "SELECT id, external_id, embedding, metadata, det_score, created_at FROM collection_faces WHERE collection_id = ?",
            (coll["id"],),
        )
        if not rows:
            return []

        query = np.asarray(embedding, dtype=np.float32).ravel()
        query_norm = float(np.linalg.norm(query)) or 1.0
        matrix = np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
        norms = np.linalg.norm(matrix, axis=1)
        norms[norms == 0] = 1.0
        scores = (matrix @ query) / (norms * query_norm)

        order = np.argsort(-scores)[: max(1, top_k)]
        results: list[dict[str, Any]] = []
        for idx in order:
            score = float(scores[idx])
            if threshold is not None and score < threshold:
                continue
            row = rows[int(idx)]
            results.append(
                {
                    "face_id": row["id"],
                    "external_id": row["external_id"],
                    "similarity": round(score, 6),
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                    "created_at": row["created_at"],
                }
            )
        return results

    @staticmethod
    def _face_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "face_id": row["id"],
            "external_id": row["external_id"],
            "det_score": row["det_score"],
            "box": json.loads(row["box"]) if row["box"] else None,
            "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
            "created_at": row["created_at"],
        }
