#!/usr/bin/env python3
"""Restart golf-dashboard if :8000 does not answer GET / within a few seconds."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.telegram_alerts import send_ops_alert  # noqa: E402


def probe(url: str, timeout_seconds: float) -> dict:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            status = int(response.status)
            return {"ok": status == 200, "status": status, "error": None}
    except Exception as exc:
        return {"ok": False, "status": None, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Dashboard HTTP watchdog")
    parser.add_argument("--url", default="http://127.0.0.1:8000/")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = probe(args.url, args.timeout_seconds)
    if args.json:
        print(json.dumps(result))
    else:
        print(f"ok={result['ok']} status={result['status']} error={result['error']}")

    if result["ok"]:
        return 0
    if args.restart:
        send_ops_alert(
            f"Dashboard watchdog restart: {args.url} failed ({result.get('error') or result.get('status')})",
            severity="warn",
        )
        subprocess.run(["systemctl", "reset-failed", "golf-dashboard"], check=False)
        subprocess.run(["systemctl", "restart", "golf-dashboard"], check=False)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
