#!/usr/bin/env python3
"""External dead-man's switch: page ntfy if the public site or ops health is down."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.telegram_alerts import send_ops_alert  # noqa: E402

DEFAULT_SITE = "https://golf.shermandavison.com/"


def _get(url: str, timeout_seconds: float) -> dict:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            body = response.read(4096)
            return {
                "ok": int(response.status) == 200,
                "status": int(response.status),
                "error": None,
                "body_prefix": body[:200].decode("utf-8", errors="replace"),
            }
    except Exception as exc:
        return {"ok": False, "status": None, "error": str(exc), "body_prefix": ""}


def evaluate(*, site_url: str, timeout_seconds: float) -> dict:
    site = _get(site_url, timeout_seconds)
    health_url = site_url.rstrip("/") + "/api/ops/health"
    health = _get(health_url, timeout_seconds)
    ok = bool(site.get("ok") and health.get("ok"))
    return {
        "ok": ok,
        "site": site,
        "health": health,
        "site_url": site_url,
        "health_url": health_url,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Page ntfy if the public site is down")
    parser.add_argument(
        "--url",
        default=os.environ.get("PUBLIC_SITE_URL") or DEFAULT_SITE,
    )
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--alert", action="store_true", default=True)
    parser.add_argument("--no-alert", dest="alert", action="store_false")
    args = parser.parse_args()

    result = evaluate(site_url=args.url, timeout_seconds=args.timeout_seconds)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"ok={result['ok']} site={result['site'].get('status')} "
            f"health={result['health'].get('status')}"
        )

    if result["ok"]:
        return 0
    if args.alert:
        send_ops_alert(
            f"Public site uptime check failed: site={result['site']} health={result['health']}",
            severity="critical",
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
