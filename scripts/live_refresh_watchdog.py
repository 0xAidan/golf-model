#!/usr/bin/env python3
"""Restart live-refresh worker when heartbeat or snapshot indicates a hung cycle."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root without install
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backtester.dashboard_runtime import read_snapshot  # noqa: E402
from src.live_refresh_health import detect_worker_wedged, restart_live_refresh_worker, snapshot_stale_after_seconds  # noqa: E402
from src.runtime_paths import get_data_dir, heartbeat_age_seconds, read_heartbeat  # noqa: E402

_WATCHDOG_LOG = get_data_dir() / "live_refresh_watchdog.log"
_LAST_RESTART_FILE = get_data_dir() / "live_refresh_watchdog_last_restart.json"


def _snapshot_age_seconds() -> int | None:
    snapshot = read_snapshot()
    generated_at = snapshot.get("generated_at") if isinstance(snapshot, dict) else None
    if not isinstance(generated_at, str) or not generated_at.strip():
        return None
    iso_value = generated_at.replace("Z", "+00:00")
    generated_dt = datetime.fromisoformat(iso_value)
    if generated_dt.tzinfo is None:
        generated_dt = generated_dt.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - generated_dt).total_seconds())


def _stale_after_seconds() -> int:
    return snapshot_stale_after_seconds()


def _append_watchdog_log(message: str) -> None:
    try:
        _WATCHDOG_LOG.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat()
        with _WATCHDOG_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {message}\n")
    except OSError:
        pass


def _read_last_restart_epoch() -> float | None:
    if not _LAST_RESTART_FILE.is_file():
        return None
    try:
        payload = json.loads(_LAST_RESTART_FILE.read_text(encoding="utf-8"))
        value = payload.get("epoch")
        return float(value) if value is not None else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _write_last_restart_epoch() -> None:
    try:
        atomic_payload = {"epoch": time.time(), "at": datetime.now(timezone.utc).isoformat()}
        _LAST_RESTART_FILE.write_text(json.dumps(atomic_payload), encoding="utf-8")
    except OSError:
        pass


def evaluate(*, heartbeat_stale_seconds: int, snapshot_stale_seconds: int) -> dict:
    heartbeat = read_heartbeat() or {}
    hb_age = heartbeat_age_seconds(heartbeat)
    snap_age = _snapshot_age_seconds()
    stale_after = _stale_after_seconds()
    wedged = detect_worker_wedged(
        snapshot_age_seconds=snap_age,
        stale_after_seconds=stale_after,
        heartbeat=heartbeat,
    )

    reasons: list[str] = []
    restart = False

    if wedged.get("wedged"):
        restart = True
        reasons.extend(wedged.get("reasons") or ["worker wedged"])

    if (
        bool(heartbeat.get("running"))
        and hb_age is not None
        and hb_age > heartbeat_stale_seconds
        and (
            str(heartbeat.get("refresh_state") or "") == "running"
            or bool(heartbeat.get("phase"))
        )
    ):
        restart = True
        reasons.append(
            f"worker heartbeat stale ({hb_age}s > {heartbeat_stale_seconds}s) while running phase={heartbeat.get('phase')!r}"
        )
    if snap_age is not None and snap_age > snapshot_stale_seconds:
        restart = True
        reasons.append(f"snapshot stale ({snap_age}s > {snapshot_stale_seconds}s)")

    last_restart = _read_last_restart_epoch()
    escalate_kill = False
    if restart and last_restart is not None and (time.time() - last_restart) < 600:
        if snap_age is not None and snap_age > snapshot_stale_seconds:
            escalate_kill = True
            reasons.append("escalate SIGKILL: restart did not refresh snapshot within 10 minutes")

    return {
        "restart": restart,
        "escalate_kill": escalate_kill,
        "reasons": reasons,
        "heartbeat_age_seconds": hb_age,
        "snapshot_age_seconds": snap_age,
        "stale_after_seconds": stale_after,
        "heartbeat_running": bool(heartbeat.get("running")),
        "heartbeat_phase": heartbeat.get("phase"),
        "worker_wedged": wedged,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Live-refresh worker watchdog")
    parser.add_argument(
        "--heartbeat-stale-seconds",
        type=int,
        default=1800,
        help="Restart when running worker heartbeat exceeds this age (default 1800)",
    )
    parser.add_argument(
        "--snapshot-stale-seconds",
        type=int,
        default=2700,
        help="Restart when snapshot age exceeds this threshold (default 2700)",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Actually restart golf-live-refresh.service when unhealthy",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON result on stdout")
    args = parser.parse_args()

    result = evaluate(
        heartbeat_stale_seconds=max(900, args.heartbeat_stale_seconds),
        snapshot_stale_seconds=max(900, args.snapshot_stale_seconds),
    )
    if args.json:
        print(json.dumps(result, indent=2))

    if not result["restart"]:
        return 0

    message = "; ".join(result["reasons"])
    if not args.restart:
        print(f"watchdog would restart worker: {message}", file=sys.stderr)
        return 2

    _append_watchdog_log(f"restart: {message}")
    if result.get("escalate_kill"):
        print(f"watchdog escalating SIGKILL golf-live-refresh: {message}", file=sys.stderr)
        proc = subprocess.run(
            ["systemctl", "kill", "-s", "SIGKILL", "golf-live-refresh.service"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout, file=sys.stderr)
        subprocess.run(["systemctl", "start", "golf-live-refresh.service"], check=False)
        _write_last_restart_epoch()
        return proc.returncode

    restart_result = restart_live_refresh_worker(reason=message)
    if not restart_result.get("ok"):
        print(restart_result.get("stderr") or "restart failed", file=sys.stderr)
        return int(restart_result.get("returncode") or 1)
    _write_last_restart_epoch()
    print(f"watchdog restarted golf-live-refresh: {message}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
