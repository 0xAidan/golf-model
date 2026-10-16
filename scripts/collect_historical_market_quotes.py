#!/usr/bin/env python3
"""Capture bounded real sportsbook archive evidence without touching golf.db."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.historical_market_quotes import (
    Capture, QuoteRequest, fetch, fetch_via_ssh, ingest_capture, quote_analyses,
    reconcile_forecasts, summarize,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True, help="Separate evidence directory, never the application DB")
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect")
    collect.add_argument("--tour", choices=["pga", "euro", "alt"], required=True)
    collect.add_argument("--event-id", action="append", required=True)
    collect.add_argument("--year", type=int, required=True, help="Calendar year, not season")
    collect.add_argument("--book", action="append", required=True)
    collect.add_argument("--market", action="append", default=[])
    collect.add_argument("--matchups", action="store_true")
    collect.add_argument("--ssh-host", help="Use existing VPS env without moving credentials")
    collect.add_argument("--max-requests", type=int, default=12)
    load = commands.add_parser("import-capture", help="Ingest an already preserved raw probe and safe request metadata")
    load.add_argument("--metadata", type=Path, required=True)
    commands.add_parser("summary")
    reconcile = commands.add_parser("reconcile")
    reconcile.add_argument("--forecasts", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "summary":
        print(json.dumps(summarize(args.vault), indent=2))
        return 0
    if args.command == "reconcile":
        forecasts = [json.loads(line) for line in args.forecasts.read_text().splitlines() if line.strip()]
        for result in reconcile_forecasts(forecasts, quote_analyses(args.vault)):
            print(json.dumps(result))
        return 0
    if args.command == "import-capture":
        meta = json.loads(args.metadata.read_text())
        params = meta["params"]
        request = QuoteRequest(params["tour"], params.get("event_id"), params.get("year"), params.get("book"), params.get("market"), meta["endpoint"].rsplit("/", 1)[-1])
        raw_path = Path(meta["raw_path"])
        raw = gzip.decompress(raw_path.read_bytes()) if raw_path.suffix == ".gz" else raw_path.read_bytes()
        from src.historical_market_quotes import digest
        if digest(raw) != meta["sha256"]:
            raise ValueError("Preserved probe hash does not match")
        print(json.dumps(ingest_capture(args.vault, request, Capture(raw, meta["status_code"], meta["acquired_at"], "preserved_probe", {}))))
        return 0
    if not args.market and not args.matchups:
        parser.error("Specify at least one market or --matchups")
    requests = [QuoteRequest(args.tour, kind="event-list")]
    for event in dict.fromkeys(args.event_id):
        for book in dict.fromkeys(args.book):
            requests.extend(QuoteRequest(args.tour, event, args.year, book, market) for market in dict.fromkeys(args.market))
            if args.matchups:
                requests.append(QuoteRequest(args.tour, event, args.year, book, kind="matchups"))
    if not 1 <= args.max_requests <= 45 or len(requests) > args.max_requests:
        parser.error(f"Bounded request limit exceeded: {len(requests)} requests")
    if not args.ssh_host:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    failed = False
    for ordinal, request in enumerate(requests):
        if ordinal:
            time.sleep(2.0)
        capture = fetch_via_ssh(request, host=args.ssh_host) if args.ssh_host else fetch(request)
        result = ingest_capture(args.vault, request, capture)
        print(json.dumps({"request": request.params, **result}), flush=True)
        failed |= result["state"] not in {"catalog", "observed_quotes", "empty_coverage"}
        if capture.status_code == 429:
            break
    print(json.dumps(summarize(args.vault), indent=2))
    return int(failed)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
