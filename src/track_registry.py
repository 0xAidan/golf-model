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
