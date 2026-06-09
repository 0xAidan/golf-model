"""
Canonical runtime paths for Golf Model production identity.

Env precedence:
  GOLF_APP_ROOT  — repository / deploy root
  GOLF_DATA_DIR  — shared data directory (snapshots, heartbeat, locks, default DB)
  GOLF_DB_PATH   — explicit SQLite path (wins over GOLF_DATA_DIR/golf.db)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent

CANONICAL_PRODUCTION_APP_ROOT = "/opt/golf-model"
HEARTBEAT_FILENAME = "live_refresh_heartbeat.json"
SNAPSHOT_FILENAME = "live_refresh_snapshot.json"
CYCLE_LOCK_FILENAME = "live_refresh_cycle.lock"
MANUAL_TRIGGER_FILENAME = "live_refresh_manual_trigger.json"


def get_app_root() -> Path:
    override = os.environ.get("GOLF_APP_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _REPO_ROOT.resolve()


def get_data_dir() -> Path:
    override = os.environ.get("GOLF_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return get_app_root() / "data"


def get_db_path() -> Path:
    explicit = os.environ.get("GOLF_DB_PATH", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return get_data_dir() / "golf.db"


def get_snapshot_path() -> Path:
    return get_data_dir() / SNAPSHOT_FILENAME


def get_heartbeat_path() -> Path:
    return get_data_dir() / HEARTBEAT_FILENAME


def get_cycle_lock_path() -> Path:
    return get_data_dir() / CYCLE_LOCK_FILENAME


def get_manual_trigger_path() -> Path:
    return get_data_dir() / MANUAL_TRIGGER_FILENAME


def is_production_deployment() -> bool:
    app_root = str(get_app_root())
    if app_root == CANONICAL_PRODUCTION_APP_ROOT:
        return True
    flag = os.environ.get("GOLF_PRODUCTION", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def live_refresh_worker_owned() -> bool:
    """When true, manual refresh is delegated to the systemd worker via trigger file."""
    flag = os.environ.get("LIVE_REFRESH_WORKER_OWNED", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    return is_production_deployment()


def get_runtime_identity() -> dict[str, Any]:
    app_root = get_app_root()
    data_dir = get_data_dir()
    snapshot_path = get_snapshot_path()
    heartbeat_path = get_heartbeat_path()
    return {
        "app_root": str(app_root),
        "data_dir": str(data_dir),
        "db_path": str(get_db_path()),
        "snapshot_path": str(snapshot_path),
        "heartbeat_path": str(heartbeat_path),
        "production": is_production_deployment(),
        "worker_owned_refresh": live_refresh_worker_owned(),
        "pid": os.getpid(),
        "cwd": str(Path.cwd().resolve()),
    }


def read_heartbeat() -> dict[str, Any] | None:
    path = get_heartbeat_path()
    if not path.is_file():
        return None
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def heartbeat_age_seconds(payload: dict[str, Any] | None) -> int | None:
    if not payload:
        return None
    updated_at = payload.get("updated_at") or payload.get("generated_at")
    if not isinstance(updated_at, str) or not updated_at.strip():
        return None
    try:
        iso_value = updated_at.replace("Z", "+00:00")
        updated_dt = datetime.fromisoformat(iso_value)
        if updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - updated_dt).total_seconds()))
    except ValueError:
        return None


def detect_split_brain(
    *,
    heartbeat: dict[str, Any] | None = None,
    max_heartbeat_age_seconds: int = 900,
) -> dict[str, Any]:
    """Compare API process identity with worker heartbeat on disk."""
    identity = get_runtime_identity()
    hb = heartbeat if heartbeat is not None else read_heartbeat()
    reasons: list[str] = []
    split_brain_suspected = False

    if hb:
        hb_app = str(hb.get("app_root") or "").strip()
        hb_data = str(hb.get("data_dir") or "").strip()
        hb_snapshot = str(hb.get("snapshot_path") or "").strip()
        if hb_app and hb_app != identity["app_root"]:
            split_brain_suspected = True
            reasons.append(f"heartbeat app_root ({hb_app}) != API app_root ({identity['app_root']})")
        if hb_data and hb_data != identity["data_dir"]:
            split_brain_suspected = True
            reasons.append(f"heartbeat data_dir ({hb_data}) != API data_dir ({identity['data_dir']})")
        if hb_snapshot and hb_snapshot != identity["snapshot_path"]:
            split_brain_suspected = True
            reasons.append(
                f"heartbeat snapshot_path ({hb_snapshot}) != API snapshot_path ({identity['snapshot_path']})"
            )
        hb_age = heartbeat_age_seconds(hb)
        if hb_age is not None and hb_age > max_heartbeat_age_seconds:
            reasons.append(f"worker heartbeat stale ({hb_age}s > {max_heartbeat_age_seconds}s)")
    elif is_production_deployment():
        reasons.append("worker heartbeat file missing on production host")

    return {
        "split_brain_suspected": split_brain_suspected,
        "reasons": reasons,
        "identity": identity,
        "heartbeat": hb,
        "heartbeat_age_seconds": heartbeat_age_seconds(hb),
    }
