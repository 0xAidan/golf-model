"""Append-only DataGolf historical sportsbook evidence, separate from golf.db.

Raw response bytes are authoritative. Normalized rows retain exact source pointers;
unknown quote timing, settlement rules and publication evidence stay unknown.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
from typing import Any

PARSER_VERSION = "datagolf_historical_books_v3"
BASE_URL = "https://feeds.datagolf.com/"
BOOKS = {
    "5dimes", "bet365", "betcris", "betmgm", "betonline", "betway", "bovada",
    "caesars", "corale", "circa", "draftkings", "fanduel", "pinnacle", "skybet",
    "sportsbook", "unibet", "williamhill",
}
MARKETS = {"win", "top_5", "top_10", "top_20", "make_cut", "mc"}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def book_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def aware_time(value: Any) -> datetime | None:
    """Never assign a timezone to a naive vendor time."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.utcoffset() is not None else None
    except ValueError:
        return None


def decimal_price(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        price = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return price if math.isfinite(price) and price > 1 else None


def positive_id(value: Any) -> int | None:
    if isinstance(value, bool) or not str(value or "").isdigit():
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


@dataclass(frozen=True)
class QuoteRequest:
    tour: str
    event_id: str | None = None
    year: int | None = None
    book: str | None = None
    market: str | None = None
    kind: str = "outrights"

    def __post_init__(self):
        if self.tour not in {"pga", "euro", "alt"} or self.kind not in {"event-list", "outrights", "matchups"}:
            raise ValueError("Unsupported tour or historical endpoint")
        if self.kind == "event-list":
            if any(x is not None for x in (self.event_id, self.year, self.book, self.market)):
                raise ValueError("Event-list accepts an explicit tour only")
            return
        if not positive_id(self.event_id) or not isinstance(self.year, int) or isinstance(self.year, bool) or not 2019 <= self.year <= 2100:
            raise ValueError("An explicit numeric event ID and calendar year are required")
        if self.book not in BOOKS:
            raise ValueError("An explicit supported sportsbook is required; DG model prices are not books")
        if (self.kind == "outrights" and self.market not in MARKETS) or (self.kind == "matchups" and self.market is not None):
            raise ValueError("Outrights require an explicit market; matchups return vendor contract types")

    @property
    def endpoint(self) -> str:
        return "historical-odds/" + self.kind

    @property
    def params(self) -> dict:
        params: dict = {"tour": self.tour, "file_format": "json"}
        if self.kind != "event-list":
            params.update(event_id=str(self.event_id), year=self.year, book=self.book, odds_format="decimal")
            if self.market:
                params["market"] = self.market
        return params


@dataclass(frozen=True)
class Capture:
    body: bytes
    status_code: int
    acquired_at: str
    transport: str
    headers: dict


def fetch(request: QuoteRequest, *, api_key: str | None = None) -> Capture:
    """Read without URL/error logging: requests exceptions may contain credentials."""
    import requests
    key = (api_key or os.environ.get("DATAGOLF_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("DATAGOLF_API_KEY unavailable")
    try:
        response = requests.get(BASE_URL + request.endpoint, params={**request.params, "key": key}, timeout=40)
    except requests.RequestException as exc:
        raise RuntimeError("DataGolf transport failure: " + type(exc).__name__) from None
    if key.encode() in response.content:
        raise RuntimeError("Response echoed credential; raw persistence refused")
    if len(response.content) > 8_000_000:
        raise RuntimeError("Historical response exceeds bounded capture size")
    headers = {k: response.headers[k] for k in ("Date", "Content-Type", "ETag", "Last-Modified") if k in response.headers}
    return Capture(response.content, response.status_code, utc_now(), "local_https", headers)


def fetch_via_ssh(request: QuoteRequest, *, host: str = "golf-vps") -> Capture:
    """Use the existing remote env without moving its secret or installing code.

    The SSH channel returns only response bytes and an allowlist of metadata.
    No source database is opened and no remote files are changed.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", host):
        raise ValueError("Expected a configured SSH host alias")
    script = """
import base64,datetime,json,os,requests
from dotenv import load_dotenv
load_dotenv('/opt/golf-model/.env',override=False)
key=os.environ.get('DATAGOLF_API_KEY','').strip()
if not key:
 print(json.dumps({'error':'remote_credential_unavailable'}));raise SystemExit(0)
spec=json.loads(SPEC)
try:
 r=requests.get('https://feeds.datagolf.com/'+spec['endpoint'],params={**spec['params'],'key':key},timeout=40)
 if key.encode() in r.content:
  print(json.dumps({'error':'credential_echo_refused'}))
 elif len(r.content)>8000000:
  print(json.dumps({'error':'capture_size_limit'}))
 else:
  print(json.dumps({'body':base64.b64encode(r.content).decode(),'status_code':r.status_code,
   'acquired_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
   'headers':{k:r.headers[k] for k in ['Date','Content-Type','ETag','Last-Modified'] if k in r.headers}}))
except requests.RequestException as e:
 print(json.dumps({'error':'transport_'+type(e).__name__}))
""".replace("SPEC", repr(canonical({"endpoint": request.endpoint, "params": request.params})))
    try:
        result = subprocess.run(["ssh", host, "/opt/golf-model/venv/bin/python", "-"], input=script, text=True, capture_output=True, timeout=55, check=False)
        payload = json.loads(result.stdout)
    except (subprocess.SubprocessError, ValueError):
        raise RuntimeError("SSH historical capture failed; diagnostic output suppressed") from None
    if result.returncode or payload.get("error"):
        raise RuntimeError("SSH historical capture failed: " + str(payload.get("error", "remote_process_error")))
    return Capture(base64.b64decode(payload["body"], validate=True), payload["status_code"], payload["acquired_at"], "ssh:" + host, payload["headers"])


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
 source_id TEXT PRIMARY KEY, endpoint TEXT NOT NULL, request_json TEXT NOT NULL,
 raw_sha256 TEXT NOT NULL, raw_path TEXT NOT NULL, raw_bytes INTEGER NOT NULL,
 status_code INTEGER NOT NULL, parser_version TEXT NOT NULL, state TEXT NOT NULL,
 validation_json TEXT NOT NULL, metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS acquisitions (
 receipt_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
 acquired_at TEXT NOT NULL, transport TEXT NOT NULL, headers_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event_catalog (
 source_id TEXT NOT NULL REFERENCES sources(source_id), json_pointer TEXT NOT NULL,
 tour TEXT NOT NULL, event_id TEXT NOT NULL, year INTEGER NOT NULL,
 event_name TEXT, payload_json TEXT NOT NULL, PRIMARY KEY(source_id,json_pointer)
);
CREATE TABLE IF NOT EXISTS quote_rows (
 quote_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
 json_pointer TEXT NOT NULL, tour TEXT NOT NULL, event_id TEXT, year INTEGER,
 event_name TEXT, book TEXT, market TEXT, family TEXT NOT NULL,
 player_dg_id INTEGER, player_name TEXT, opponent_dg_id INTEGER, contract_players_json TEXT NOT NULL, side TEXT,
 open_decimal REAL, close_decimal REAL, open_time_raw TEXT, close_time_raw TEXT,
 settlement_rule TEXT, outcome_numeric REAL, outcome_text TEXT,
 identity_verified INTEGER NOT NULL, validation_json TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS quote_exact_key ON quote_rows(tour,event_id,year,book,market,player_dg_id,opponent_dg_id);
"""


def _raw_file(root: Path, body: bytes) -> tuple[str, str]:
    sha = digest(body)
    relative = "raw/" + sha + ".json.gz"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if digest(gzip.decompress(target.read_bytes())) != sha:
            raise ValueError("Existing raw response failed hash verification")
        return sha, relative
    fd, temporary = tempfile.mkstemp(prefix=".capture-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(gzip.compress(body, mtime=0))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)  # No overwrite, including concurrent capture.
        except FileExistsError:
            if digest(gzip.decompress(target.read_bytes())) != sha:
                raise ValueError("Concurrent raw response failed hash verification") from None
    finally:
        os.unlink(temporary)
    return sha, relative


def open_vault(root: Path | str, *, readonly: bool = False) -> sqlite3.Connection:
    root = Path(root)
    if readonly:
        conn = sqlite3.connect((root / "quotes.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
        conn.execute("PRAGMA query_only=ON")
    else:
        root.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(root / "quotes.sqlite", timeout=15)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA recursive_triggers=ON")
        conn.executescript(SCHEMA)
        for table in ("sources", "acquisitions", "event_catalog", "quote_rows"):
            for action in ("UPDATE", "DELETE"):
                conn.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'historical evidence is append-only'); END")
        conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


def _unpack(payload: Any) -> tuple[dict, list, str]:
    if isinstance(payload, dict):
        return {k: v for k, v in payload.items() if k != "odds"}, payload.get("odds", []), "/odds"
    # Also retain DataGolf's older [rows, metadata] representation.
    if isinstance(payload, list) and len(payload) == 2 and isinstance(payload[0], list) and isinstance(payload[1], dict):
        return payload[1], payload[0], "/0"
    return {}, [], ""


def _identity(request: QuoteRequest, metadata: dict) -> list[str]:
    reasons = []
    checks = {"event_id": str(request.event_id), "year": str(request.year), "book": request.book}
    if request.kind == "outrights":
        checks["market"] = request.market
    for key, expected in checks.items():
        value = metadata.get(key)
        actual = book_key(value) if key == "book" else str(value) if value is not None else None
        if actual != expected:
            reasons.append("response_" + key + ("_missing" if value is None else "_mismatch"))
    if metadata.get("tour") is not None and metadata["tour"] != request.tour:
        reasons.append("response_tour_mismatch")
    return reasons


def ingest_capture(root: Path | str, request: QuoteRequest, capture: Capture) -> dict:
    """Preserve success, empty, malformed and HTTP-error responses idempotently."""
    if aware_time(capture.acquired_at) is None:
        raise ValueError("Acquisition timestamp must include its timezone")
    root = Path(root)
    sha, raw_path = _raw_file(root, capture.body)
    source_id = digest(canonical({"endpoint": request.endpoint, "params": request.params, "raw_sha256": sha, "http_status": capture.status_code, "parser": PARSER_VERSION}).encode())
    reasons: list[str] = []
    try:
        payload = json.loads(capture.body, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, ValueError):
        payload = None
    metadata, raw_rows, prefix = _unpack(payload)
    if capture.status_code != 200:
        state = "http_error"
    elif payload is None:
        state = "invalid_json"
    elif request.kind == "event-list":
        state = "catalog" if isinstance(payload, list) else "unsupported_shape"
    elif not isinstance(raw_rows, list) or not prefix:
        state = "unsupported_shape"
    else:
        reasons = _identity(request, metadata)
        state = "identity_rejected" if reasons else "observed_quotes" if raw_rows else "empty_coverage"
    conn = open_vault(root)
    try:
        before = conn.total_changes
        conn.execute("INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?,?,?,?,?,?,?)", (source_id, request.endpoint, canonical(request.params), sha, raw_path, len(capture.body), capture.status_code, PARSER_VERSION, state, canonical(reasons), canonical(metadata)))
        new_source = conn.total_changes > before
        headers = {key: value for key, value in capture.headers.items() if key.lower() in {"date", "content-type", "etag", "last-modified"}}
        receipt_id = digest(canonical([source_id, capture.acquired_at, capture.transport, headers]).encode())
        conn.execute("INSERT OR IGNORE INTO acquisitions VALUES (?,?,?,?,?)", (receipt_id, source_id, capture.acquired_at, capture.transport, canonical(headers)))
        added = 0
        if state == "catalog":
            for ordinal, entry in enumerate(payload):
                if not isinstance(entry, dict) or not positive_id(entry.get("event_id")) or not isinstance(entry.get("calendar_year"), int):
                    continue
                conn.execute("INSERT OR IGNORE INTO event_catalog VALUES (?,?,?,?,?,?,?)", (source_id, "/" + str(ordinal), request.tour, str(entry["event_id"]), entry["calendar_year"], entry.get("event_name"), canonical(entry)))
        if state in {"observed_quotes", "identity_rejected"}:
            for ordinal, entry in enumerate(raw_rows):
                if not isinstance(entry, dict):
                    continue
                three_ball = request.kind == "matchups" and "3-ball" in str(entry.get("bet_type", "")).lower()
                # Some matchup rows offer a third categorical outcome (e.g.
                # vendor "Halve", ID 0). Retain it; do not invent a player ID
                # or collapse this contract into a two-way matchup.
                extra_outcome = request.kind == "matchups" and "p3_dg_id" in entry
                sides = ("p1", "p2", "p3") if three_ball or extra_outcome else ("p1", "p2") if request.kind == "matchups" else (None,)
                contract_ids = [positive_id(entry.get(s + "_dg_id" if s else "dg_id")) for s in sides]
                contract_players = sorted(value for value in contract_ids if value is not None)
                for side in sides:
                    pointer = prefix + "/" + str(ordinal)
                    quote_id = digest(canonical([source_id, pointer, side]).encode())
                    player_id = positive_id(entry.get(side + "_dg_id" if side else "dg_id"))
                    opponent_side = "p2" if side == "p1" else "p1"
                    opponent_id = positive_id(entry.get(opponent_side + "_dg_id")) if side and not three_ball else None
                    row_reasons = list(reasons)
                    if player_id is None or len(set(contract_players)) != len(sides):
                        row_reasons.append("missing_player_identity")
                    if extra_outcome and not three_ball:
                        row_reasons.append("categorical_extra_outcome_requires_contract_adapter")
                    market = entry.get("bet_type") if side else metadata.get("market")
                    if not market:
                        row_reasons.append("missing_market_contract")
                    opening = decimal_price(entry.get(side + "_open" if side else "open_odds"))
                    closing = decimal_price(entry.get(side + "_close" if side else "close_odds"))
                    numeric = entry.get(side + "_outcome" if side else "bet_outcome_numeric")
                    numeric = float(numeric) if isinstance(numeric, (int, float)) and not isinstance(numeric, bool) and math.isfinite(numeric) else None
                    family = "three_ball" if three_ball else "multi_outcome_matchup" if extra_outcome else "matchup" if side else "placement"
                    values = (quote_id, source_id, pointer, request.tour, str(metadata["event_id"]) if metadata.get("event_id") is not None else None, positive_id(metadata.get("year")), metadata.get("event_name"), book_key(metadata.get("book")) or None, market, family, player_id, entry.get(side + "_player_name" if side else "player_name"), opponent_id, canonical(contract_players), side, opening, closing, entry.get("open_time"), entry.get("close_time"), entry.get("tie_rule") or metadata.get("settlement_rule"), numeric, entry.get(side + "_outcome_text" if side else "bet_outcome_text"), int(not row_reasons), canonical(row_reasons), canonical(entry))
                    changed = conn.total_changes
                    conn.execute("INSERT OR IGNORE INTO quote_rows VALUES (" + ",".join("?" for _ in values) + ")", values)
                    added += int(conn.total_changes > changed)
        conn.commit()
        return {"source_id": source_id, "raw_sha256": sha, "state": state, "validation": reasons, "new_source": new_source, "new_quote_rows": added, "raw_path": raw_path}
    finally:
        conn.close()


def analyze_quote(row: dict, *, catalog_verified: bool, market_start_at: str | None = None, market_start_source: dict | None = None) -> dict:
    """A vendor price comparison becomes qualified only with complete evidence."""
    opening, closing = decimal_price(row.get("open_decimal")), decimal_price(row.get("close_decimal"))
    identity = bool(row.get("identity_verified")) and catalog_verified and row.get("book") in BOOKS
    ratio = 100 * (opening / closing - 1) if opening is not None and closing is not None else None
    if ratio is not None and not math.isfinite(ratio):
        ratio = None
    opened, closed = aware_time(row.get("open_time_raw")), aware_time(row.get("close_time_raw"))
    start_reference = (
        isinstance(market_start_source, dict)
        and re.fullmatch(r"[a-f0-9]{64}", str(market_start_source.get("source_sha256", "")))
        and str(market_start_source.get("json_pointer", "")).startswith("/")
    )
    start = aware_time(market_start_at) if start_reference else None
    reasons = []
    if not identity:
        reasons.append("event_player_book_market_identity_unverified")
    if ratio is None:
        reasons.append("missing_or_invalid_price_pair")
    if opened is None or closed is None:
        reasons.append("quote_time_timezone_unverified")
    if start is None:
        reasons.append("market_start_unverified")
    if opened and closed and opened > closed:
        reasons.append("opening_after_closing")
    if closed and start and closed >= start:
        reasons.append("closing_not_before_market_start")
    if not row.get("settlement_rule"):
        reasons.append("settlement_contract_unverified")
    return {"vendor_open_close_pct": ratio if identity else None, "qualified_clv_pct": ratio if not reasons else None, "close_verified": not reasons, "qualification_reasons": reasons, "market_start_source": market_start_source if start is not None else None, "fair_close_ev_pct": None, "devig_applied": False, "executed_bet": False}


def quote_analyses(root: Path | str) -> list[dict]:
    conn = open_vault(root, readonly=True)
    try:
        catalog = {(r["tour"], r["event_id"], r["year"], r["event_name"]) for r in conn.execute("SELECT * FROM event_catalog")}
        result = []
        for entry in conn.execute("SELECT * FROM quote_rows ORDER BY quote_id"):
            row = dict(entry)
            verified = (row["tour"], row["event_id"], row["year"], row["event_name"]) in catalog
            result.append({**row, **analyze_quote(row, catalog_verified=verified)})
        return result
    finally:
        conn.close()


def summarize(root: Path | str) -> dict:
    rows = quote_analyses(root)
    conn = open_vault(root, readonly=True)
    try:
        return {
            "parser_version": PARSER_VERSION,
            "sources": conn.execute("SELECT count(*) FROM sources").fetchone()[0],
            "acquisitions": conn.execute("SELECT count(*) FROM acquisitions").fetchone()[0],
            "source_states": {r[0]: r[1] for r in conn.execute("SELECT state,count(*) FROM sources GROUP BY state")},
            "quote_rows": len(rows),
            "distinct_contracts": len({(r["tour"], r["event_id"], r["year"], r["book"], r["market"], r["player_dg_id"], r["contract_players_json"]) for r in rows if r["identity_verified"]}),
            "event_bound_price_pairs": sum(r["vendor_open_close_pct"] is not None for r in rows),
            "qualified_clv_pairs": sum(r["close_verified"] for r in rows),
            "qualification_reasons": {reason: sum(reason in r["qualification_reasons"] for r in rows) for reason in sorted({x for r in rows for x in r["qualification_reasons"]})},
            "events": sorted({(r["tour"], r["event_id"], r["year"], r["event_name"]) for r in rows if r["identity_verified"]}),
            "limits": ["Vendor archive observations are not executed wagers.", "Opening/closing endpoints do not establish executable prices at arbitrary model decision times.", "Naive quote times retain unknown timezone; no event start or settlement rule is guessed.", "Raw revisions remain separate source versions; do not count repeated captures as independent trials."],
        }
    finally:
        conn.close()


def reconcile_forecasts(forecasts: list[dict], quotes: list[dict]) -> list[dict]:
    """Exact, provenance-required IDs only; no display-name or date guessing.

    Callers must provide source_sha256, source_pointer and identity_provenance
    when bridging a recovered card to vendor IDs. Historical open is never
    substituted for that card's quoted entry price.
    """
    results = []
    fields = ("tour", "event_id", "year", "book", "market", "player_dg_id", "opponent_dg_id")
    for forecast in forecasts:
        reasons = []
        required = ("source_sha256", "source_pointer", "identity_provenance", "tour", "event_id", "year", "book", "market", "player_dg_id")
        if any(forecast.get(k) in (None, "") for k in required):
            reasons.append("missing_original_forecast_identity_or_provenance")
        candidates = [r for r in quotes if all(r.get(k) == forecast.get(k) for k in fields) and r.get("vendor_open_close_pct") is not None and (r.get("family") != "three_ball" or r.get("contract_players_json") == forecast.get("contract_players_json"))] if not reasons else []
        # Identical vendor revisions may repeat the same close; conflicting closes stay unresolved.
        contracts = {(r.get("close_decimal"), r.get("close_time_raw"), r.get("settlement_rule")) for r in candidates}
        if not candidates:
            reasons.append("no_exact_vendor_contract")
        elif len(contracts) != 1:
            reasons.append("conflicting_vendor_closing_versions")
        taken = decimal_price(forecast.get("odds_decimal"))
        if taken is None:
            reasons.append("missing_original_forecast_price")
        match = candidates[0] if len(contracts) == 1 else None
        price_ratio = 100 * (taken / match["close_decimal"] - 1) if match and taken is not None else None
        if price_ratio is not None and not math.isfinite(price_ratio):
            price_ratio = None
            reasons.append("nonfinite_price_comparison")
        decision = aware_time(forecast.get("generated_at"))
        close = aware_time(match.get("close_time_raw")) if match else None
        if decision is None or close is None or decision >= close:
            reasons.append("decision_before_close_unverified")
        if not match or not match.get("close_verified"):
            reasons.append("vendor_close_unqualified")
        if not match or forecast.get("settlement_rule") != match.get("settlement_rule") or not forecast.get("settlement_rule"):
            reasons.append("matching_settlement_rule_unverified")
        if not forecast.get("publication_verified"):
            reasons.append("original_publication_unverified")
        results.append({"source_sha256": forecast.get("source_sha256"), "source_pointer": forecast.get("source_pointer"), "key": {k: forecast.get(k) for k in fields}, "matched_quote_ids": [r["quote_id"] for r in candidates], "recorded_forecast_price_vs_vendor_close_pct": price_ratio, "qualified_clv_pct": price_ratio if not reasons else None, "qualification_reasons": reasons, "executed_bet": False})
    return results
