"""Single source of truth for the two model-track config slots.

The product runs two model tracks:
- ``dashboard`` (champion) — the operator `/` boards, driven by
  ``COCKPIT_SNAPSHOT_MODEL_VARIANT`` + the resolved runtime strategy.
- ``lab`` (challenger) — the `/lab` boards, driven by the promoted matchup-lab
  champion bundle (``config/lab_matchup_champion_trial327.json``).

Historically these were three disconnected "champion" concepts (rails ``CHAMPION``,
the live/research registry, and the lab JSON file). This module gives each track a
single queryable record with a stable ``config_hash`` for provenance and a
``GET /api/tracks`` surface.

Wave 1 scope is **read-only / provenance only**: the registry records the canonical
bundle + hash for each track and seeds itself from the *current* effective config, so
runtime behavior is unchanged. It does NOT swap strategy resolution — promotion (writing
a new bundle into the dashboard slot) is gated for a later wave. Runtime precedence
remains: env (``COCKPIT_SNAPSHOT_MODEL_VARIANT``) > registry seed > lab champion file >
default.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src import db

DASHBOARD = "dashboard"
LAB = "lab"
TRACKS = (DASHBOARD, LAB)

_HASH_LEN = 16


def compute_config_hash(model_variant: str | None, pipeline_cfg: dict | None) -> str:
    """Stable short hash of the behavior-determining config (variant + pipeline dict)."""
    payload = {
        "model_variant": str(model_variant or "").strip().lower(),
        "pipeline": pipeline_cfg or {},
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:_HASH_LEN]


def canonical_dashboard_bundle() -> dict[str, Any]:
    """Current effective dashboard (champion) config bundle."""
    from src import config
    from src.strategy_resolution import build_pipeline_strategy_config, resolve_runtime_strategy

    variant = str(getattr(config, "COCKPIT_SNAPSHOT_MODEL_VARIANT", "baseline")).strip().lower()
    strategy, meta = resolve_runtime_strategy("global")
    pipeline_cfg = build_pipeline_strategy_config(strategy)
    return {
        "track": DASHBOARD,
        "label": meta.get("strategy_name") or strategy.name or "dashboard",
        "model_variant": variant,
        "strategy_source": meta.get("strategy_source", "default"),
        "pipeline": pipeline_cfg,
        "config_hash": compute_config_hash(variant, pipeline_cfg),
    }


def canonical_lab_bundle() -> dict[str, Any]:
    """Current effective lab (challenger) config bundle from the promoted champion file."""
    from src import config
    from src.lab_champion import build_lab_pipeline_config, lab_champion_meta, load_lab_champion_strategy

    strategy = load_lab_champion_strategy()
    pipeline_cfg = build_lab_pipeline_config(strategy)
    variant = str(strategy.model_variant or "v5").strip().lower()
    if variant not in config.ALLOWED_MODEL_VARIANTS:
        variant = "v5"
    meta = lab_champion_meta()
    return {
        "track": LAB,
        "label": strategy.name or meta.get("lab_champion_id") or "lab_champion",
        "model_variant": variant,
        "strategy_source": "lab_champion",
        "lab_champion_id": meta.get("lab_champion_id"),
        "pipeline": pipeline_cfg,
        "config_hash": compute_config_hash(variant, pipeline_cfg),
    }


def _bundle_for(track: str) -> dict[str, Any]:
    if track == DASHBOARD:
        return canonical_dashboard_bundle()
    if track == LAB:
        return canonical_lab_bundle()
    raise ValueError(f"unknown track: {track!r}")


def seed_default_tracks() -> None:
    """Insert an active row for each track from the current effective config if absent.

    Idempotent: only seeds a track that has no active row. Never overwrites a row that an
    operator (or a future promotion flow) has already set.
    """
    db.ensure_initialized()
    conn = db.get_conn()
    try:
        for track in TRACKS:
            existing = conn.execute(
                "SELECT id FROM track_configs WHERE track = ? AND status = 'active' LIMIT 1",
                (track,),
            ).fetchone()
            if existing:
                continue
            try:
                bundle = _bundle_for(track)
            except Exception:
                # Lab champion file or strategy resolution unavailable in this environment;
                # skip seeding that slot rather than crashing init.
                continue
            conn.execute(
                """
                INSERT INTO track_configs
                    (track, strategy_bundle_json, model_variant, config_hash, label,
                     status, activated_by, activation_reason)
                VALUES (?, ?, ?, ?, ?, 'active', 'seed', 'initial seed from current effective config')
                """,
                (
                    track,
                    json.dumps(bundle, sort_keys=True, default=str),
                    bundle.get("model_variant"),
                    bundle.get("config_hash"),
                    bundle.get("label"),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_active_track(track: str) -> dict[str, Any] | None:
    """Active registry row for a track (seeds on first access), or None if unavailable."""
    if track not in TRACKS:
        raise ValueError(f"unknown track: {track!r}")
    db.ensure_initialized()
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM track_configs WHERE track = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (track,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        seed_default_tracks()
        conn = db.get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM track_configs WHERE track = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
                (track,),
            ).fetchone()
        finally:
            conn.close()
    return _row_to_dict(row) if row else None


def list_tracks(history_limit: int = 10) -> dict[str, Any]:
    """Both active slots plus recent activation history (for GET /api/tracks)."""
    seed_default_tracks()
    conn = db.get_conn()
    try:
        active_rows = {
            r["track"]: _row_to_dict(r)
            for r in conn.execute(
                "SELECT * FROM track_configs WHERE status = 'active' ORDER BY id DESC"
            ).fetchall()
        }
        history = [
            _row_to_dict(r)
            for r in conn.execute(
                "SELECT * FROM track_configs ORDER BY id DESC LIMIT ?",
                (int(history_limit),),
            ).fetchall()
        ]
    finally:
        conn.close()
    # Always reflect the live effective config hash so drift between the seeded row and
    # the current effective config is visible (e.g. if the lab champion file changed).
    effective: dict[str, Any] = {}
    for track in TRACKS:
        try:
            effective[track] = _bundle_for(track).get("config_hash")
        except Exception:
            effective[track] = None
    return {
        "tracks": active_rows,
        "effective_config_hash": effective,
        "history": history,
    }


def evaluate_promotion_readiness(scope: str = "global") -> dict[str, Any]:
    """Gate-by-gate promotion readiness (charter live-promotion gates + lab graded sample).

    Returns ``{passed, gates: [...], metrics, lab_graded_positive_ev}``. Human approval is
    always still required to actually promote.
    """
    from backtester.model_registry import evaluate_live_promotion_gates

    result = evaluate_live_promotion_gates(scope)
    passed = getattr(result, "passed", False)
    reasons = getattr(result, "reasons", []) or []
    metrics = getattr(result, "metrics", {}) or {}

    # Lab-lane graded sample size (pick_source=lab) — promotion needs lab evidence, not just
    # the global charter gates which are dominated by the live/cockpit lane.
    lab_graded = 0
    try:
        conn = db.get_conn()
        lab_graded = conn.execute(
            """
            SELECT COUNT(*) FROM picks p
            JOIN pick_outcomes po ON po.pick_id = p.id
            WHERE p.source IN ('lab_sandbox', 'lab_sandbox_candidate') AND p.ev > 0
            """
        ).fetchone()[0]
        conn.close()
    except Exception:
        lab_graded = 0

    gates = [
        {"id": "charter_live_gates", "passed": bool(passed), "detail": "; ".join(reasons) or "all charter gates pass"},
        {
            "id": "lab_graded_sample",
            "passed": lab_graded > 0,
            "detail": f"{lab_graded} graded +EV lab picks (need > 0 for lab evidence)",
        },
    ]
    return {
        "passed": bool(passed) and lab_graded > 0,
        "gates": gates,
        "metrics": metrics,
        "lab_graded_positive_ev": lab_graded,
    }


def promote_track(
    *,
    from_track: str = LAB,
    reason: str,
    activated_by: str = "operator",
    require_gates: bool = True,
) -> dict[str, Any]:
    """Promote a track's bundle into the dashboard slot (auditable, reversible).

    Records the new active dashboard row with ``parent_id`` pointing at the prior active
    dashboard row (the rollback target) and ``evidence_json`` capturing gate results. This
    establishes the *config of record*; making it the live runtime still requires the
    documented env/profile change (precedence is unchanged here) — by design, to keep the
    promotion auditable without a silent production swap.
    """
    if from_track not in TRACKS:
        raise ValueError(f"unknown source track: {from_track!r}")
    seed_default_tracks()
    readiness = evaluate_promotion_readiness()
    if require_gates and not readiness["passed"]:
        return {"ok": False, "reason": "gates_not_met", "readiness": readiness}

    source = get_active_track(from_track)
    if not source:
        return {"ok": False, "reason": "source_track_unavailable", "readiness": readiness}

    import json as _json

    conn = db.get_conn()
    try:
        prior = conn.execute(
            "SELECT id FROM track_configs WHERE track = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (DASHBOARD,),
        ).fetchone()
        prior_id = prior["id"] if prior else None
        if prior_id is not None:
            conn.execute("UPDATE track_configs SET status = 'retired' WHERE id = ?", (prior_id,))
        bundle = dict(source.get("strategy_bundle") or {})
        bundle["promoted_from"] = from_track
        cursor = conn.execute(
            """
            INSERT INTO track_configs
                (track, strategy_bundle_json, model_variant, config_hash, label, status,
                 parent_id, evidence_json, activated_by, activation_reason)
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                DASHBOARD,
                _json.dumps(bundle, sort_keys=True, default=str),
                source.get("model_variant"),
                source.get("config_hash"),
                source.get("label"),
                prior_id,
                _json.dumps(readiness, default=str),
                activated_by,
                reason,
            ),
        )
        conn.commit()
        new_id = cursor.lastrowid
    finally:
        conn.close()
    return {"ok": True, "new_dashboard_id": new_id, "rolled_back_to_id_on_revert": prior_id, "readiness": readiness}


def rollback_track(track: str = DASHBOARD) -> dict[str, Any]:
    """Revert the dashboard slot to its parent (the config it replaced). One action."""
    if track != DASHBOARD:
        raise ValueError("only the dashboard slot supports rollback")
    conn = db.get_conn()
    try:
        current = conn.execute(
            "SELECT id, parent_id FROM track_configs WHERE track = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (DASHBOARD,),
        ).fetchone()
        if not current:
            return {"ok": False, "reason": "no_active_dashboard_row"}
        parent_id = current["parent_id"]
        if parent_id is None:
            return {"ok": False, "reason": "no_parent_to_roll_back_to"}
        conn.execute("UPDATE track_configs SET status = 'retired' WHERE id = ?", (current["id"],))
        conn.execute("UPDATE track_configs SET status = 'active' WHERE id = ?", (parent_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "restored_id": parent_id, "retired_id": current["id"]}


def _row_to_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    bundle_raw = d.get("strategy_bundle_json")
    if isinstance(bundle_raw, str) and bundle_raw:
        try:
            d["strategy_bundle"] = json.loads(bundle_raw)
        except Exception:
            d["strategy_bundle"] = None
    d.pop("strategy_bundle_json", None)
    return d
