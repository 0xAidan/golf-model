"""Autoresearch orchestrator: nightly fast-tier cycles + weekly deep cycles.

Karpathy-loop runner per docs/research/PROGRAM.md:
- Nightly: bounded mutation/evaluation cycle (fast tier) under the effort preset
  persisted in data/autoresearch_settings.json (autoresearch_effort).
- Weekly: ingestion first (resume-safe DG backfill -> derived backtest ledger ->
  incremental PIT rebuild), then search.
- Cross-process fcntl lock prevents overlap with manual Optuna studies.
- Heartbeat JSON mirrors live-refresh conventions for watchdogging.
- High-signal Telegram alerts only (promotable find / crash / stall / ingestion
  failure) plus a weekly digest. NOTHING is ever promoted automatically.

Run directly for a single cycle, or via deploy/systemd/golf-autoresearch.timer.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("GOLF_DATA_DIR", ROOT / "data"))
LOCK_PATH = DATA_DIR / "autoresearch_cycle.lock"
HEARTBEAT_PATH = DATA_DIR / "autoresearch_heartbeat.json"

logger = logging.getLogger("golf.autoresearch_orchestrator")

_SHUTDOWN = False


def _handle_signal(signum, _frame) -> None:
    global _SHUTDOWN
    _SHUTDOWN = True


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_heartbeat(stage: str, status: str, detail: dict | None = None) -> None:
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": _utc_now_iso(),
        "stage": stage,
        "status": status,
        **(detail or {}),
    }
    tmp = HEARTBEAT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(HEARTBEAT_PATH)


class CycleLock:
    """fcntl lock mirroring the live-refresh cross-process pattern."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or LOCK_PATH
        self._fd: int | None = None

    def acquire(self, *, blocking: bool = False) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR)
        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_exc):
        self.release()
        return False


def get_effort_setting() -> str:
    """Read the operator's effort dial from autoresearch settings (default standard)."""
    try:
        from src.autoresearch_settings import get_settings

        value = str(get_settings().get("autoresearch_effort") or "").strip().lower()
    except Exception:
        value = ""
    if not value:
        env_value = (os.environ.get("AUTORESEARCH_EFFORT") or "").strip().lower()
        value = env_value
    from backtester.fast_tier import DEFAULT_EFFORT, EFFORT_PRESETS

    return value if value in EFFORT_PRESETS else DEFAULT_EFFORT


def set_effort_setting(name: str) -> bool:
    """Persist the effort dial; returns whether it was accepted."""
    from backtester.fast_tier import EFFORT_PRESETS

    key = str(name or "").strip().lower()
    if key not in EFFORT_PRESETS:
        return False
    try:
        from src.autoresearch_settings import set_settings

        set_settings({"autoresearch_effort": key})
        return True
    except Exception:
        logger.warning("Could not persist effort setting", exc_info=True)
        return False


def send_high_signal_alert(text: str) -> bool:
    """Telegram high-signal alert; no-op when unconfigured."""
    try:
        from src.telegram_alerts import send_telegram_message

        return send_telegram_message(text)
    except Exception:
        logger.warning("Alert dispatch failed", exc_info=True)
        return False


def run_cycle(*, weekly: bool = False, dry_run: bool = False) -> dict:
    """Run one orchestrator cycle; returns a summary payload (also ledgered)."""
    from backtester.fast_tier import EffortBudget
    from src.db import ensure_initialized

    ensure_initialized()
    effort = get_effort_setting()
    budget = EffortBudget.for_effort(effort)
    started = time.perf_counter()

    summary: dict = {
        "kind": "orchestrator_cycle",
        "cycle_type": "weekly_deep" if weekly else "nightly_fast",
        "effort": effort,
        "started_at": _utc_now_iso(),
        "dry_run": dry_run,
    }
    write_heartbeat("cycle_start", "running", {"effort": effort, "weekly": weekly})

    if weekly and not dry_run:
        # Weekly deep cycle: refresh data before searching.
        from scripts.run_weekly_research_refresh import run_sequence

        run_sequence()

    if not dry_run:
        from backtester.tier1_loop import run_tier1_cycle

        result = run_tier1_cycle(budget=budget)
        summary.update(result)

    summary["elapsed_seconds"] = round(time.perf_counter() - started, 1)
    summary["finished_at"] = _utc_now_iso()
    summary["budget"] = {
        "max_wall_seconds": budget.max_wall_seconds,
        "trials_used": budget.trials_used,
        "exhausted": budget.exhausted(),
    }
    write_heartbeat("cycle_end", "ok", {"elapsed_seconds": summary["elapsed_seconds"]})

    from backtester.research_lab.ledger import append_ledger_row

    append_ledger_row({"source": "agent", **summary})
    return summary


def build_weekly_digest() -> str:
    """Summarize the trailing week of ledger rows into a digest message."""
    from backtester.research_lab.ledger import LEDGER_PATH

    cutoff = time.time() - 7 * 86400
    trials = keeps = 0
    promotable = 0
    if LEDGER_PATH.exists():
        with LEDGER_PATH.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = row.get("ts") or ""
                try:
                    row_time = datetime.fromisoformat(ts).timestamp() if ts else 0
                except ValueError:
                    continue
                if row_time < cutoff:
                    continue
                kind = row.get("kind")
                if kind == "orchestrator_cycle":
                    continue
                if kind == "promotion_ready":
                    promotable += 1
                    continue
                trials += 1
                if row.get("decision") == "keep":
                    keeps += 1
    return (
        "Autoresearch weekly digest:\n"
        f"Trials logged: {trials}\n"
        f"Keeps: {keeps}\n"
        f"Promotion-ready candidates: {promotable}"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Autoresearch orchestrator")
    parser.add_argument("--weekly", action="store_true", help="Run the weekly deep cycle")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--digest", action="store_true", help="Send the weekly digest and exit")
    parser.add_argument("--loop", action="store_true", help="Daemon mode (systemd service)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if args.digest:
        sent = send_high_signal_alert(build_weekly_digest())
        print(f"Digest sent: {sent}")
        return 0

    lock = CycleLock()
    if not lock.acquire(blocking=False):
        logger.warning("Another autoresearch cycle holds the lock; skipping.")
        return 0

    try:
        if args.loop:
            while not _SHUTDOWN:
                run_cycle(weekly=False, dry_run=args.dry_run)
                # Sleep ~23h or until shutdown signal.
                for _ in range(23 * 120):
                    if _SHUTDOWN:
                        break
                    time.sleep(30)
            return 0
        summary = run_cycle(weekly=args.weekly, dry_run=args.dry_run)
        print(json.dumps(summary, indent=2, default=str))
        return 0
    except Exception as exc:
        logger.exception("Cycle failed")
        write_heartbeat("cycle_error", "error", {"error": str(exc)})
        send_high_signal_alert(f"Autoresearch cycle FAILED: {exc}")
        return 1
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
