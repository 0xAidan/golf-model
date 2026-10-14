#!/usr/bin/env python3
"""Serve read-only reports and snapshot projections without importing the app."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
from threading import BoundedSemaphore
from urllib.parse import parse_qs, urlsplit

# Deployed beside a minimal src/ package, or run from this repo's scripts/.
# No .env loading, application imports, database initialization, or bytecode writes.
sys.dont_write_bytecode = True
_root = Path(__file__).resolve().parent
if not (_root / "src").is_dir():
    _root = _root.parent
sys.path.insert(0, str(_root))

from src.market_evidence import build_market_evidence  # noqa: E402
from src.operator_read_model import build_board  # noqa: E402


@dataclass(frozen=True)
class Settings:
    database_path: Path
    snapshot_path: Path
    stale_after_seconds: int = 3720

    def __post_init__(self):
        if not self.database_path.is_absolute() or not self.snapshot_path.is_absolute():
            raise ValueError("Source paths must be absolute.")
        if self.stale_after_seconds <= 0:
            raise ValueError("Snapshot freshness window must be positive.")


class InvalidQuery(ValueError):
    """Request validation failure, distinct from malformed source data."""


class ReportServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, settings: Settings, port: int):
        self.settings = settings
        self.report_slots = BoundedSemaphore(4)
        super().__init__(("127.0.0.1", port), ReportHandler)

    def handle_error(self, request, client_address):
        # Socket failures must not dump a request, file path, or traceback.
        print("Read-only report request failed.", file=sys.stderr)


class ReportHandler(BaseHTTPRequestHandler):
    server: ReportServer
    server_version = "GolfEvidence/1"
    sys_version = ""
    timeout = 15

    def log_message(self, format, *args):
        # Standard access logs echo arbitrary query strings. Deliberately omit.
        pass

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if status == 405:
            self.send_header("Allow", "GET, HEAD")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _query(self, allowed: set[str]) -> dict[str, str]:
        try:
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True, max_num_fields=8)
        except ValueError:
            raise InvalidQuery("Invalid query parameters.") from None
        if set(query) - allowed or any(len(values) != 1 or not values[0] for values in query.values()):
            raise InvalidQuery("Invalid query parameters.")
        return {key: values[0] for key, values in query.items()}

    def _board(self) -> dict:
        query = self._query({"track", "mode", "event_id"})
        track, mode = query.get("track", "champion"), query.get("mode", "upcoming")
        if track not in {"champion", "challenger"} or mode not in {"live", "upcoming"}:
            raise InvalidQuery("This endpoint supports champion/challenger and live/upcoming only.")
        event_id = query.get("event_id")
        if event_id is not None and (not event_id.strip() or len(event_id) > 128):
            raise InvalidQuery("Invalid event identity.")
        snapshot = None
        try:
            # A bounded read tolerates the worker's atomic replacement and
            # fails closed on missing, incomplete, oversized, or malformed JSON.
            with self.server.settings.snapshot_path.open("rb") as handle:
                raw = handle.read(16 * 1024 * 1024 + 1)
            if len(raw) <= 16 * 1024 * 1024:
                candidate = json.loads(raw)
                if isinstance(candidate, dict):
                    snapshot = candidate
        except (OSError, ValueError, UnicodeError):
            pass
        return build_board(
            snapshot, track=track, mode=mode, event_id=event_id,
            stale_after_seconds=self.server.settings.stale_after_seconds,
        )

    def _evidence(self) -> dict:
        query = self._query({"lane", "season"})
        lane = query.get("lane", "dashboard")
        if lane not in {"dashboard", "lab", "all"}:
            raise InvalidQuery("Invalid report lane.")
        season = None
        if "season" in query:
            if len(query["season"]) != 4 or not query["season"].isdigit() or not 2000 <= int(query["season"]) <= 2100:
                raise InvalidQuery("Invalid report season.")
            season = int(query["season"])
        return build_market_evidence(self.server.settings.database_path, lane=lane, season=season)

    def _serve(self):
        try:
            path = urlsplit(self.path).path
            if path == "/health":
                self._query(set())
                self._json(200, {"ok": True, "service": "golf-evidence", "read_only": True})
                return
            if path not in {"/api/market-evidence", "/api/desk/board"}:
                self._json(404, {"error": "Not found."})
                return
            if not self.server.report_slots.acquire(blocking=False):
                self._json(503, {"state": "unavailable", "reason": "Reports are busy. Retry shortly."})
                return
            try:
                payload = self._board() if path == "/api/desk/board" else self._evidence()
                self._json(200, payload)
            finally:
                self.server.report_slots.release()
        except InvalidQuery:
            self._json(400, {"error": "Invalid request. Check the supported parameters."})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            # Do not expose raw exception text, SQLite paths, or provider URLs.
            self._json(503, {"state": "unavailable", "reason": "The read-only report is unavailable."})

    do_GET = _serve
    do_HEAD = _serve

    def _method_not_allowed(self):
        self._json(405, {"error": "Only GET and HEAD are supported."})

    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_OPTIONS = _method_not_allowed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--db-path", type=Path, default=os.environ.get("GOLF_DB_PATH", "/opt/golf-model/data/golf.db"))
    parser.add_argument("--snapshot-path", type=Path, default=os.environ.get("GOLF_SNAPSHOT_PATH", "/opt/golf-model/data/live_refresh_snapshot.json"))
    parser.add_argument("--stale-after-seconds", type=int, default=os.environ.get("GOLF_SNAPSHOT_STALE_SECONDS", "3720"))
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    try:
        settings = Settings(args.db_path, args.snapshot_path, args.stale_after_seconds)
    except ValueError:
        parser.error("Source paths must be absolute and the freshness window must be positive.")
    with ReportServer(settings, args.port) as server:
        print(f"Read-only report service listening on 127.0.0.1:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
