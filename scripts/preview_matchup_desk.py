#!/usr/bin/env python3
"""Serve the built desk against read-only evidence and published GET endpoints.

Never imports app.py, initializes a database, starts a worker, or forwards writes.
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import certifi
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.market_evidence import build_market_evidence  # noqa: E402
from src.operator_read_model import build_board  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--port", type=int, default=5398)
    parser.add_argument("--fixture-board", type=Path, help="Local UI test board; never used by the production service")
    parser.add_argument("--snapshot", type=Path, help="Read-only captured production snapshot for local verification")
    args = parser.parse_args()
    static = ROOT / "frontend" / "dist"

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(static), **kw)

        def do_GET(self):
            route = urlsplit(self.path)
            if route.path == "/api/desk/board" and args.snapshot:
                query = parse_qs(route.query)
                payload = build_board(json.loads(args.snapshot.read_text()), track=query.get("track", ["champion"])[0], mode=query.get("mode", ["upcoming"])[0])
                body = json.dumps(payload, allow_nan=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if route.path == "/api/desk/board" and args.fixture_board:
                payload = json.loads(args.fixture_board.read_text())
                payload["event"]["event_name"] = "UI verification fixture — not live market"
                payload["event"]["course_name"] = "Local test data"
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if route.path == "/api/market-evidence":
                params = parse_qs(route.query)
                payload = build_market_evidence(database_path=args.db, lane=params.get("lane", ["dashboard"])[0])
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if route.path.startswith(("/api/", "/static/")):
                try:
                    upstream_path = self.path.replace("/api/desk/board", "/api/operator/board", 1)
                    request = Request("https://golf.shermandavison.com" + upstream_path, method="GET")
                    with urlopen(request, timeout=25, context=ssl.create_default_context(cafile=certifi.where())) as response:
                        body = response.read()
                        self.send_response(response.status)
                        self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                        self.send_header("Content-Length", str(len(body)))
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        self.wfile.write(body)
                except HTTPError as exc:
                    self.send_error(exc.code, "Published data unavailable")
                except Exception:
                    self.send_error(502, "Published data unavailable")
                return
            if not (static / route.path.lstrip("/")).is_file():
                self.path = "/index.html"
            super().do_GET()

        def do_POST(self):
            self.send_error(405, "Preview is read-only")

    print(f"Read-only preview: http://127.0.0.1:{args.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
