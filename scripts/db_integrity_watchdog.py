#!/usr/bin/env python3
"""15-minute live-DB smoke probe. Triggers recover only on confirmed corruption."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.db_integrity import probe_live_database  # noqa: E402
from src.telegram_alerts import send_ops_alert  # noqa: E402


def evaluate() -> dict:
    probe = probe_live_database(timeout_seconds=8.0)
    state = str(probe.get("state") or "error")
    recover = state == "corrupt"
    alert = state in {"corrupt", "missing"}
    return {
        "recover": recover,
        "alert": alert,
        "probe": probe,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-probe live SQLite file")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--recover",
        action="store_true",
        help="Start golf-db-recover.service when probe reports corrupt",
    )
    parser.add_argument("--alert", action="store_true", default=True)
    parser.add_argument("--no-alert", dest="alert", action="store_false")
    args = parser.parse_args()

    result = evaluate()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        probe = result["probe"]
        print(f"state={probe.get('state')} ok={probe.get('ok')} error={probe.get('error')}")

    if result["alert"] and args.alert:
        probe = result["probe"]
        send_ops_alert(
            f"Live database probe {probe.get('state')}: {probe.get('error') or 'ok'}",
            severity="critical" if result["recover"] else "warn",
        )

    if result["recover"] and args.recover:
        subprocess.run(
            ["systemctl", "start", "golf-db-recover.service"],
            check=False,
        )
        return 2
    if result["alert"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
