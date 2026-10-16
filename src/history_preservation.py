"""Fail-closed policy for automatic removal of prediction history.

Pure and cheap enough to check before initialization or maintenance imports.
Disabling preservation is an explicit operator opt-in, never archive proof.
"""
from __future__ import annotations

import os
import hashlib
import json
from typing import Any

PRESERVATION_ENV = "PRESERVE_PREDICTION_HISTORY"
_EXPLICIT_DISABLED = frozenset({"0", "false", "no", "off"})


def prediction_history_preservation_enabled() -> bool:
    """Default to preserving everything; unknown/empty values also preserve."""
    return os.environ.get(PRESERVATION_ENV, "1").strip().lower() not in _EXPLICIT_DISABLED


def preservation_skip(**details: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "skipped": True,
        "preservation_enabled": True,
        "reason": f"{PRESERVATION_ENV} is enabled (default); historical prediction data is preserved",
        **details,
    }


def preserve_pick_outcome_versions(conn, tournament_id: int, *, reason: str) -> int:
    """Retain before-images when legitimate grading updates an existing outcome.

    The journal is append-only by distinct row payload. It does not block new
    forecasts, ordinary grading, or derived cache updates.
    """
    if not prediction_history_preservation_enabled():
        return 0
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    else:
        # A caller may have opened a deferred read transaction. Reserve its
        # write lock before reading before-images, without changing any row.
        _ensure_version_table(conn)
        conn.execute("UPDATE prediction_history_versions SET id = id WHERE 0")
    cursor = conn.execute(
        "SELECT po.* FROM pick_outcomes po JOIN picks p ON p.id = po.pick_id WHERE p.tournament_id = ?",
        (int(tournament_id),),
    )
    columns = [column[0] for column in cursor.description]
    originals = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return preserve_prediction_row_versions(conn, "pick_outcomes", originals, reason=reason)


def _ensure_version_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prediction_history_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_table TEXT NOT NULL,
            source_row_id TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            reason TEXT NOT NULL,
            preserved_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            UNIQUE(source_table, source_row_id, payload_sha256)
        )
    """)


def preserve_prediction_row_versions(conn, source_table: str, originals: list[dict], *, reason: str) -> int:
    """Journal exact rows; the caller must reserve its write lock before reading."""
    if source_table not in {"picks", "results", "pick_outcomes", "metrics", "prediction_log"}:
        raise ValueError("Unsupported historical prediction table")
    if not prediction_history_preservation_enabled():
        return 0
    if not originals:
        return 0
    _ensure_version_table(conn)
    inserted = 0
    for row in originals:
        payload = json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False)
        cursor = conn.execute("""
            INSERT OR IGNORE INTO prediction_history_versions
                (source_table, source_row_id, payload_sha256, payload_json, reason)
            VALUES (?, ?, ?, ?, ?)
        """, (source_table, str(row["id"]), hashlib.sha256(payload.encode()).hexdigest(), payload, reason))
        inserted += cursor.rowcount
    return inserted
