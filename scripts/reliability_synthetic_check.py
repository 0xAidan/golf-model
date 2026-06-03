#!/usr/bin/env python3
"""Synthetic reliability check for dashboard availability and freshness."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib import error, request


@dataclass
class CheckResult:
    name: str
    url: str
    status_code: int | None
    elapsed_ms: int
    ok: bool
    message: str
    payload: dict[str, Any] | None = None


def _http_get_json(url: str, timeout_seconds: float) -> tuple[int, int, dict[str, Any]]:
    started = time.perf_counter()
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8")
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        parsed = json.loads(body)
        return int(response.status), elapsed_ms, parsed


def _http_get_status(url: str, timeout_seconds: float) -> tuple[int, int]:
    started = time.perf_counter()
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=timeout_seconds) as response:
        _ = response.read(1024)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return int(response.status), elapsed_ms


def _parse_generated_age_seconds(snapshot: dict[str, Any]) -> int | None:
    generated_at = snapshot.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        return None
    iso_value = generated_at.replace("Z", "+00:00")
    generated_dt = datetime.fromisoformat(iso_value)
    if generated_dt.tzinfo is None:
        generated_dt = generated_dt.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - generated_dt).total_seconds())


def run_checks(
    base_url: str,
    timeout_seconds: float,
    max_root_ms: int,
    max_api_ms: int,
    max_snapshot_age_seconds: int,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    root_url = f"{base_url.rstrip('/')}/"
    status_url = f"{base_url.rstrip('/')}/api/live-refresh/status"
    snapshot_url = f"{base_url.rstrip('/')}/api/live-refresh/snapshot"

    try:
        status_code, elapsed_ms = _http_get_status(root_url, timeout_seconds)
        ok = status_code == 200 and elapsed_ms <= max_root_ms
        message = (
            f"root returned {status_code} in {elapsed_ms}ms"
            if ok
            else f"root unhealthy: status={status_code} elapsed_ms={elapsed_ms} threshold_ms={max_root_ms}"
        )
        results.append(
            CheckResult(
                name="root",
                url=root_url,
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                ok=ok,
                message=message,
            )
        )
    except (error.URLError, TimeoutError, ValueError) as exc:
        results.append(
            CheckResult(
                name="root",
                url=root_url,
                status_code=None,
                elapsed_ms=int(timeout_seconds * 1000),
                ok=False,
                message=f"root request failed: {exc}",
            )
        )

    try:
        status_code, elapsed_ms, payload = _http_get_json(status_url, timeout_seconds)
        status_payload = payload.get("status") if isinstance(payload.get("status"), dict) else payload
        running_present = isinstance(status_payload, dict) and "running" in status_payload
        running_flag = bool(status_payload.get("running")) if running_present else None
        ok = status_code == 200 and elapsed_ms <= max_api_ms and running_present
        message = (
            f"status returned {status_code} in {elapsed_ms}ms (running={running_flag})"
            if ok
            else (
                "status unhealthy: "
                f"status={status_code} elapsed_ms={elapsed_ms} threshold_ms={max_api_ms} payload_has_running={running_present}"
            )
        )
        results.append(
            CheckResult(
                name="live_refresh_status",
                url=status_url,
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                ok=ok,
                message=message,
                payload=payload,
            )
        )
    except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        results.append(
            CheckResult(
                name="live_refresh_status",
                url=status_url,
                status_code=None,
                elapsed_ms=int(timeout_seconds * 1000),
                ok=False,
                message=f"status request failed: {exc}",
            )
        )

    try:
        status_code, elapsed_ms, payload = _http_get_json(snapshot_url, timeout_seconds)
        age_seconds = _parse_generated_age_seconds(payload)
        age_ok = age_seconds is not None and age_seconds <= max_snapshot_age_seconds
        stale_reason = payload.get("stale_reason")
        ok = status_code == 200 and elapsed_ms <= max_api_ms and age_ok
        message = (
            f"snapshot returned {status_code} in {elapsed_ms}ms (age_seconds={age_seconds})"
            if ok
            else (
                "snapshot unhealthy: "
                f"status={status_code} elapsed_ms={elapsed_ms} threshold_ms={max_api_ms} "
                f"age_seconds={age_seconds} max_age_seconds={max_snapshot_age_seconds} stale_reason={stale_reason}"
            )
        )
        results.append(
            CheckResult(
                name="live_refresh_snapshot",
                url=snapshot_url,
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                ok=ok,
                message=message,
                payload={"generated_at": payload.get("generated_at"), "stale_reason": stale_reason},
            )
        )
    except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        results.append(
            CheckResult(
                name="live_refresh_snapshot",
                url=snapshot_url,
                status_code=None,
                elapsed_ms=int(timeout_seconds * 1000),
                ok=False,
                message=f"snapshot request failed: {exc}",
            )
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run synthetic reliability checks.")
    parser.add_argument("--base-url", default="https://golf.ancc.blog", help="Base URL to probe.")
    parser.add_argument("--timeout-seconds", type=float, default=8.0, help="Per-request timeout.")
    parser.add_argument("--max-root-ms", type=int, default=5000, help="Max root response latency.")
    parser.add_argument("--max-api-ms", type=int, default=8000, help="Max API response latency.")
    parser.add_argument(
        "--max-snapshot-age-seconds",
        type=int,
        default=2700,
        help="Max allowed snapshot staleness.",
    )
    parser.add_argument("--output-json", default="", help="Optional path to write machine-readable results.")
    args = parser.parse_args()

    results = run_checks(
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
        max_root_ms=args.max_root_ms,
        max_api_ms=args.max_api_ms,
        max_snapshot_age_seconds=args.max_snapshot_age_seconds,
    )
    failures = [r for r in results if not r.ok]
    for result in results:
        marker = "OK" if result.ok else "FAIL"
        print(f"[{marker}] {result.name}: {result.message}")

    structured = {
        "base_url": args.base_url,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "ok": len(failures) == 0,
        "failures": [f.name for f in failures],
        "results": [
            {
                "name": r.name,
                "url": r.url,
                "status_code": r.status_code,
                "elapsed_ms": r.elapsed_ms,
                "ok": r.ok,
                "message": r.message,
                "payload": r.payload,
            }
            for r in results
        ],
    }

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as fh:
            json.dump(structured, fh, indent=2, sort_keys=True)
            fh.write("\n")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
