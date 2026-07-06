#!/usr/bin/env python3
"""Restart live-refresh worker when heartbeat or snapshot indicates a hung cycle."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root without install
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backtester.dashboard_runtime import read_snapshot  # noqa: E402
from src.live_refresh_policy import resolve_cadence  # noqa: E402
from src.autoresearch_settings import get_settings  # noqa: E402
from src.runtime_paths import heartbeat_age_seconds, read_heartbeat  # noqa: E402


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
    settings = get_settings().get("live_refresh") or {}
    cadence = resolve_cadence(settings)
    return max(900, int(cadence.recompute_seconds) + 120)


def evaluate(*, heartbeat_stale_seconds: int, snapshot_stale_seconds: int) -> dict:
    heartbeat = read_heartbeat() or {}
    hb_age = heartbeat_age_seconds(heartbeat)
    snap_age = _snapshot_age_seconds()
    stale_after = _stale_after_seconds()
    hb_running = bool(heartbeat.get("running"))
    hb_phase = heartbeat.get("phase")
    hb_refresh = str(heartbeat.get("refresh_state") or "")

    reasons: list[str] = []
    restart = False

    if hb_running and hb_age is not None and hb_age > heartbeat_stale_seconds:
        restart = True
        if hb_refresh == "running" or hb_phase:
            reasons.append(
                f"worker heartbeat stale ({hb_age}s > {heartbeat_stale_seconds}s) while running phase={hb_phase!r}"
            )
        else:
            reasons.append(
                f"worker heartbeat stale ({hb_age}s > {heartbeat_stale_seconds}s) while idle"
            )
    if snap_age is not None and snap_age > snapshot_stale_seconds:
        restart = True
        reasons.append(f"snapshot stale ({snap_age}s > {snapshot_stale_seconds}s)")

    return {
        "restart": restart,
        "reasons": reasons,
        "heartbeat_age_seconds": hb_age,
        "snapshot_age_seconds": snap_age,
        "stale_after_seconds": stale_after,
        "heartbeat_running": hb_running,
        "heartbeat_phase": hb_phase,
    }


def _run_grading_sweep(*, year: int | None, emit_json: bool) -> tuple[dict, int]:
    from scripts.grading_sweep import run_grading_sweep

    payload = run_grading_sweep(year=year)
    if emit_json:
        print(json.dumps({"grading_sweep": payload}, indent=2, default=str))
    elif not payload.get("ok"):
        reconciliation = payload.get("reconciliation") or {}
        print(
            "grading sweep reported issues "
            f"(reconciliation={reconciliation.get('status')})",
            file=sys.stderr,
        )
    return payload, 0 if payload.get("ok") else 1


def _restart_worker() -> int:
    reset = subprocess.run(
        ["systemctl", "reset-failed", "golf-live-refresh.service"],
        capture_output=True,
        text=True,
        check=False,
    )
    if reset.returncode != 0:
        print(reset.stderr or reset.stdout, file=sys.stderr)
        return reset.returncode

    proc = subprocess.run(
        ["systemctl", "restart", "golf-live-refresh.service"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
    return proc.returncode


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
    parser.add_argument(
        "--ensure-grading",
        action="store_true",
        help="After watchdog check, run grading sweep (advisory; does not block restart)",
    )
    parser.add_argument("--grading-year", type=int, default=None, help="Year for --ensure-grading")
    args = parser.parse_args()

    from src.worker_restart import acknowledge_worker_restart_request, read_worker_restart_request

    restart_request = read_worker_restart_request()
    result = evaluate(
        heartbeat_stale_seconds=max(900, args.heartbeat_stale_seconds),
        snapshot_stale_seconds=max(900, args.snapshot_stale_seconds),
    )
    if restart_request:
        result["restart"] = True
        result["reasons"].insert(
            0,
            f"operator worker restart requested ({restart_request.get('requested_at')})",
        )
    if args.json and not args.ensure_grading:
        print(json.dumps(result, indent=2))

    exit_code = 0
    if result["restart"]:
        message = "; ".join(result["reasons"])
        if not args.restart:
            print(f"watchdog would restart worker: {message}", file=sys.stderr)
            exit_code = 2
        else:
            print(f"watchdog restarting golf-live-refresh: {message}", file=sys.stderr)
            exit_code = _restart_worker()
            if exit_code == 0 and restart_request:
                acknowledge_worker_restart_request(restart_request.get("request_id"))
    elif args.json:
        print(json.dumps(result, indent=2))

    if args.ensure_grading:
        _, grading_exit = _run_grading_sweep(year=args.grading_year, emit_json=args.json)
        if exit_code == 0 and not (result["restart"] and args.restart):
            exit_code = grading_exit

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
