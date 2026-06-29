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
        help="Run ensure_completed_event_grading after watchdog check",
    )
    parser.add_argument("--grading-year", type=int, default=None, help="Year for --ensure-grading")
    args = parser.parse_args()

    if args.ensure_grading:
        from src.event_pick_freeze import ensure_all_completed_pga_events_graded
        from src.grading_reconciliation import reconcile_grading

        grading_report = ensure_all_completed_pga_events_graded(year=args.grading_year)
        reconciliation = reconcile_grading(limit_events=10)
        grading_payload = {"grading": grading_report, "reconciliation": reconciliation}
        if args.json:
            print(json.dumps(grading_payload, indent=2, default=str))
        elif not grading_report.get("ok"):
            print("grading ensure reported failures", file=sys.stderr)
            return 1
        if reconciliation.get("status") == "discrepancies":
            print("grading reconciliation reported discrepancies", file=sys.stderr)
            return 1

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

    print(f"watchdog restarting golf-live-refresh: {message}", file=sys.stderr)
    proc = subprocess.run(
        ["systemctl", "restart", "golf-live-refresh.service"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
