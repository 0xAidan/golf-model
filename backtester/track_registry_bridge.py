"""Bridge between the autoresearch operator layer and track_configs (lab slot).

Keeps src/track_registry.py untouched: lab-slot promotions from the autoresearch
view write rows with the same schema/conventions (parent_id rollback chain,
evidence_json, activated_by/reason audit), scoped to the LAB track only.
"""

from __future__ import annotations

import json
from typing import Any

from backtester.strategy import StrategyConfig
from src import db

LAB = "lab"


def record_lab_promotion(
    *,
    strategy: StrategyConfig,
    label: str,
    reason: str,
    activated_by: str = "operator",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a new active lab row; retire the prior one; return the result."""
    db.ensure_initialized()
    conn = db.get_conn()
    try:
        prior = conn.execute(
            "SELECT id FROM track_configs WHERE track = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (LAB,),
        ).fetchone()
        prior_id = prior["id"] if prior else None
        if prior_id is not None:
            conn.execute("UPDATE track_configs SET status = 'retired' WHERE id = ?", (prior_id,))

        bundle = {
            "model_variant": getattr(strategy, "model_variant", "baseline"),
            "label": label,
            "strategy_config": {
                k: v for k, v in vars(strategy).items() if not k.startswith("_")
            },
        }
        config_hash = _short_hash(json.dumps(bundle, sort_keys=True, default=str))

        cursor = conn.execute(
            """
            INSERT INTO track_configs
                (track, strategy_bundle_json, model_variant, config_hash, label, status,
                 parent_id, evidence_json, activated_by, activation_reason)
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                LAB,
                json.dumps(bundle, sort_keys=True, default=str),
                bundle.get("model_variant"),
                config_hash,
                label,
                prior_id,
                json.dumps(evidence or {}, sort_keys=True, default=str),
                activated_by,
                reason,
            ),
        )
        new_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "new_lab_id": new_id, "previous_lab_id": prior_id}


def rollback_lab_track() -> dict[str, Any]:
    """Retire the current active lab row and re-activate its parent. One action."""
    db.ensure_initialized()
    conn = db.get_conn()
    try:
        current = conn.execute(
            "SELECT id, parent_id FROM track_configs WHERE track = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (LAB,),
        ).fetchone()
        if not current:
            return {"ok": False, "reason": "no_active_lab_row"}
        parent_id = current["parent_id"]
        if parent_id is None:
            return {"ok": False, "reason": "no_parent_to_roll_back_to"}
        parent = conn.execute("SELECT * FROM track_configs WHERE id = ?", (parent_id,)).fetchone()
        if not parent:
            return {"ok": False, "reason": "parent_row_missing"}
        conn.execute("UPDATE track_configs SET status = 'retired' WHERE id = ?", (current["id"],))
        conn.execute("UPDATE track_configs SET status = 'active' WHERE id = ?", (parent_id,))
        conn.commit()
        return {"ok": True, "rolled_back_to_id": parent_id}
    finally:
        conn.close()


def _short_hash(material: str) -> str:
    import hashlib

    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
