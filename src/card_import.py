"""Import official picks from markdown betting cards and provenance JSON."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from src import db
from src.official_pick_record import dedupe_grading_picks, normalize_market_type
from src.player_normalizer import normalize_name

MATCHUP_TABLE_HEADER = re.compile(
    r"^\|\s*Pick\s*\|\s*vs\s*\|\s*Odds\s*\|\s*Model Win%\s*\|\s*EV\s*\|",
    re.IGNORECASE,
)
BEST_BETS_HEADER = re.compile(
    r"^\|\s*Pick\s*\|\s*(Market|Type)\s*\|\s*Odds\s*\|\s*EV%?\s*\|",
    re.IGNORECASE,
)
TOP5_HEADER = re.compile(
    r"^\|\s*Pick\s*\|\s*Type\s*\|\s*Odds\s*\|\s*EV%?\s*\|",
    re.IGNORECASE,
)

EXCLUDE_NAME_PATTERNS = (
    "methodology",
    "_audit_",
    "readiness_audit",
    "roi_if_ended_today",
    "backtest",
    "baseline_pack",
    "grading_reconciliation",
    "debug_",
)
EXCLUDE_PATH_PARTS = ("backtests", "audits", "__macosx")


@dataclass
class CardCandidate:
    path: Path
    event_slug: str
    file_date: date | None
    lane: str
    kind: str
    event_name_hint: str = ""


@dataclass
class ParsedPick:
    player_display: str
    opponent_display: str
    player_key: str
    opponent_key: str
    market_odds: str
    market_book: str
    model_prob: float | None
    ev: float | None
    market_type: str
    confidence: str | None = None
    reasoning: str | None = None


@dataclass
class ImportManifest:
    year: int
    events: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = str(value).strip().replace("%", "").replace(",", "")
    if not cleaned or cleaned in {"—", "-", "n/a"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_vs_pick(pick_cell: str) -> tuple[str, str] | None:
    text = pick_cell.replace("**", "").strip()
    if " vs " in text.lower():
        left, right = re.split(r"\s+vs\s+", text, maxsplit=1, flags=re.IGNORECASE)
        return left.strip(), right.strip()
    return None


def _player_keys(player: str, opponent: str) -> tuple[str, str]:
    return normalize_name(player), normalize_name(opponent)


def parse_file_date(path: Path) -> date | None:
    match = re.search(r"(20\d{6})", path.name)
    if not match:
        return None
    raw = match.group(1)
    try:
        return datetime.strptime(raw, "%Y%m%d").date()
    except ValueError:
        return None


def infer_lane(path: Path) -> str:
    lowered = str(path).lower()
    if "sandbox" in lowered or "trial241" in lowered:
        return "lab"
    return "dashboard"


def classify_file(path: Path) -> str | None:
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}
    if any(part in parts for part in EXCLUDE_PATH_PARTS) or name.startswith("._"):
        return None
    if any(pattern in name for pattern in EXCLUDE_NAME_PATTERNS):
        return None
    if path.suffix.lower() == ".json":
        return "provenance" if "provenance" in name else None
    if path.suffix.lower() != ".md":
        return None
    return "betting_card"


def extract_event_name_from_card(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            title = re.sub(r"\s*[—-]\s*Betting Card\s*$", "", title, flags=re.IGNORECASE)
            title = re.sub(r"\s*[—-]\s*Team Event Notice\s*$", "", title, flags=re.IGNORECASE)
            return title.strip()
    return ""


def resolve_event_id(conn: sqlite3.Connection, event_name: str, year: int) -> dict | None:
    needle = event_name.strip().lower()
    needle = re.sub(r"\s+20\d{2}$", "", needle).strip()
    if not needle:
        return None
    rows = conn.execute(
        """
        SELECT DISTINCT event_id, event_name, MIN(event_completed) AS first_completed
        FROM rounds
        WHERE year = ? AND event_id IS NOT NULL AND TRIM(event_id) != ''
          AND LOWER(event_name) LIKE ?
        GROUP BY event_id, event_name
        """,
        (year, f"%{needle}%"),
    ).fetchall()
    for row in rows:
        if str(row["event_name"] or "").strip().lower() == needle:
            return dict(row)
    if len(rows) == 1:
        return dict(rows[0])
    for row in rows:
        if needle in str(row["event_name"] or "").strip().lower():
            return dict(row)
    return None


def _section_market_type(lines: list[str], start_index: int) -> str:
    for idx in range(max(0, start_index - 8), start_index):
        header = lines[idx].strip().lower()
        if "round matchup" in header:
            return "round_matchups"
        if "tournament matchup" in header or "72-hole" in header:
            return "tournament_matchups"
        if "3-ball" in header:
            return "three_ball"
    return "tournament_matchups"


def _parse_table_row(parts: list[str], market_type: str) -> ParsedPick | None:
    if len(parts) < 5:
        return None
    player = parts[0].replace("**", "").strip()
    opponent = parts[1].strip()
    odds_str = parts[2].strip()
    model_prob = _safe_float(parts[3])
    ev_val = _safe_float(parts[4])
    book = parts[7].strip() if len(parts) > 7 else ""
    tier = parts[6].strip() if len(parts) > 6 else ""
    why = parts[8].strip() if len(parts) > 8 else ""
    if not player or not opponent or not odds_str:
        return None
    player_key, opponent_key = _player_keys(player, opponent)
    ev_fraction = (ev_val / 100.0) if ev_val is not None and ev_val > 1 else ev_val
    model_fraction = (model_prob / 100.0) if model_prob is not None and model_prob > 1 else model_prob
    return ParsedPick(
        player_display=player,
        opponent_display=opponent,
        player_key=player_key,
        opponent_key=opponent_key,
        market_odds=odds_str,
        market_book=book if book and book != "—" else "",
        model_prob=model_fraction,
        ev=ev_fraction,
        market_type=normalize_market_type(market_type),
        confidence=tier or None,
        reasoning=why or None,
    )


def parse_matchup_tables(text: str) -> list[ParsedPick]:
    lines = text.splitlines()
    picks: list[ParsedPick] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if MATCHUP_TABLE_HEADER.match(line):
            market_type = _section_market_type(lines, i)
            i += 2
            while i < len(lines):
                stripped = lines[i].strip()
                if not stripped.startswith("|"):
                    break
                parts = [part.strip() for part in stripped.strip("|").split("|")]
                parsed = _parse_table_row(parts, market_type)
                if parsed:
                    picks.append(parsed)
                i += 1
            continue
        i += 1
    return picks


def parse_best_bets_table(text: str) -> list[ParsedPick]:
    lines = text.splitlines()
    picks: list[ParsedPick] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if BEST_BETS_HEADER.match(line) or TOP5_HEADER.match(line):
            i += 2
            while i < len(lines):
                stripped = lines[i].strip()
                if not stripped.startswith("|"):
                    break
                parts = [part.strip() for part in stripped.strip("|").split("|")]
                if len(parts) < 4:
                    i += 1
                    continue
                market = parts[1].strip().lower()
                if market not in {"matchup", "h2h", "head_to_head"}:
                    i += 1
                    continue
                pair = _parse_vs_pick(parts[0])
                if not pair:
                    i += 1
                    continue
                player, opponent = pair
                odds_str = parts[2].strip()
                ev_val = _safe_float(parts[3])
                tier = parts[4].strip() if len(parts) > 4 else ""
                player_key, opponent_key = _player_keys(player, opponent)
                ev_fraction = (ev_val / 100.0) if ev_val is not None and ev_val > 1 else ev_val
                picks.append(
                    ParsedPick(
                        player_display=player,
                        opponent_display=opponent,
                        player_key=player_key,
                        opponent_key=opponent_key,
                        market_odds=odds_str,
                        market_book="",
                        model_prob=None,
                        ev=ev_fraction,
                        market_type="tournament_matchups",
                        confidence=tier or None,
                    )
                )
                i += 1
            continue
        i += 1
    return picks


def parse_card_file(path: Path) -> list[ParsedPick]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    picks = parse_matchup_tables(text)
    picks.extend(parse_best_bets_table(text))
    return picks


def parse_provenance_json(path: Path) -> list[ParsedPick]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("market_rows") or payload.get("rows") or payload.get("picks") or []
    picks: list[ParsedPick] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        market_family = str(row.get("market_family") or row.get("bet_type") or "").lower()
        if market_family not in {"matchup", "matchups"} and "matchup" not in str(row.get("market_type") or "").lower():
            continue
        player = row.get("player_display") or row.get("player") or ""
        opponent = row.get("opponent_display") or row.get("opponent") or ""
        if not player or not opponent:
            continue
        ev = row.get("ev")
        try:
            ev_val = float(ev) if ev is not None else None
        except (TypeError, ValueError):
            ev_val = None
        picks.append(
            ParsedPick(
                player_display=str(player),
                opponent_display=str(opponent),
                player_key=str(row.get("player_key") or normalize_name(str(player))),
                opponent_key=str(row.get("opponent_key") or normalize_name(str(opponent))),
                market_odds=str(row.get("odds") or row.get("market_odds") or ""),
                market_book=str(row.get("book") or row.get("market_book") or ""),
                model_prob=row.get("model_prob"),
                ev=ev_val,
                market_type=normalize_market_type(row.get("market_type") or "tournament_matchups"),
            )
        )
    return picks


def discover_card_candidates(search_dirs: Iterable[Path]) -> list[CardCandidate]:
    candidates: list[CardCandidate] = []
    for base in search_dirs:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            kind = classify_file(path)
            if not kind:
                continue
            candidates.append(
                CardCandidate(
                    path=path,
                    event_slug=path.stem.lower(),
                    file_date=parse_file_date(path),
                    lane=infer_lane(path),
                    kind=kind,
                )
            )
    return candidates


def select_canonical_card(
    candidates: list[CardCandidate],
    *,
    event_name: str,
    round1_thursday: date | None,
) -> tuple[CardCandidate | None, list[CardCandidate]]:
    del event_name
    betting = [c for c in candidates if c.kind in {"betting_card", "provenance"}]
    if not betting:
        return None, []

    def sort_key(card: CardCandidate) -> tuple:
        file_date = card.file_date or date.min
        if round1_thursday:
            if file_date <= round1_thursday:
                distance = (round1_thursday - file_date).days
                return (0, distance, file_date.toordinal())
            return (1, (file_date - round1_thursday).days, file_date.toordinal())
        return (0, 0, file_date.toordinal())

    ranked = sorted(betting, key=sort_key)
    chosen = ranked[0]
    rejected = [card for card in betting if card.path != chosen.path]
    return chosen, rejected


def _ensure_tournament(conn: sqlite3.Connection, *, name: str, event_id: str, year: int) -> int:
    row = conn.execute(
        "SELECT id FROM tournaments WHERE event_id = ? AND year = ?",
        (event_id, year),
    ).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO tournaments (name, year, event_id) VALUES (?, ?, ?)",
        (name, year, event_id),
    )
    conn.commit()
    return int(cur.lastrowid)


def _has_locked_outcomes(conn: sqlite3.Connection, tournament_id: int) -> bool:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM pick_outcomes po
        JOIN picks p ON p.id = po.pick_id
        WHERE p.tournament_id = ? AND po.outcome_locked = 1
        """,
        (tournament_id,),
    ).fetchone()
    return bool(row and int(row["c"] or 0) > 0)


def parsed_to_pick_rows(
    parsed: list[ParsedPick],
    *,
    tournament_id: int,
    source: str,
    model_variant: str,
    card_path: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pick in parsed:
        rows.append(
            {
                "tournament_id": tournament_id,
                "model_variant": model_variant,
                "source": source,
                "bet_type": "matchup",
                "market_type": pick.market_type,
                "player_key": pick.player_key,
                "player_display": pick.player_display,
                "opponent_key": pick.opponent_key,
                "opponent_display": pick.opponent_display,
                "model_prob": pick.model_prob,
                "market_odds": pick.market_odds,
                "market_book": pick.market_book,
                "ev": pick.ev,
                "confidence": pick.confidence,
                "reasoning": f"card_import:{card_path.name}; {pick.reasoning or ''}".strip("; "),
            }
        )
    return rows


def import_cards_from_dirs(
    search_dirs: list[Path],
    *,
    year: int = 2026,
    dry_run: bool = True,
) -> ImportManifest:
    db.ensure_initialized()
    conn = db.get_conn()
    manifest = ImportManifest(year=year)
    candidates = discover_card_candidates(search_dirs)

    by_event: dict[str, list[CardCandidate]] = {}
    for candidate in candidates:
        try:
            if candidate.kind == "betting_card":
                text = candidate.path.read_text(encoding="utf-8")
                event_name = extract_event_name_from_card(text)
            else:
                event_name = candidate.path.stem.replace("_provenance", "").replace("_", " ")
            resolved = resolve_event_id(conn, event_name, year)
            if not resolved:
                manifest.errors.append(f"unresolved_event: {candidate.path} ({event_name})")
                continue
            event_id = str(resolved["event_id"])
            candidate.event_name_hint = str(resolved.get("event_name") or event_name)
            by_event.setdefault(event_id, []).append(candidate)
        except OSError as exc:
            manifest.errors.append(f"read_error: {candidate.path}: {exc}")

    for event_id, event_candidates in by_event.items():
        event_name = event_candidates[0].event_name_hint
        schedule_row = conn.execute(
            """
            SELECT MIN(event_completed) AS round1
            FROM rounds WHERE event_id = ? AND year = ?
            """,
            (event_id, year),
        ).fetchone()
        round1_thursday = None
        if schedule_row and schedule_row["round1"]:
            try:
                round1_thursday = datetime.strptime(str(schedule_row["round1"])[:10], "%Y-%m-%d").date()
            except ValueError:
                round1_thursday = None

        dashboard_cards = [c for c in event_candidates if c.lane == "dashboard"]
        lab_cards = [c for c in event_candidates if c.lane == "lab"]
        lane_results: dict[str, Any] = {}

        for lane_name, lane_candidates in (("dashboard", dashboard_cards), ("lab", lab_cards)):
            if not lane_candidates:
                continue
            chosen, rejected = select_canonical_card(
                lane_candidates,
                event_name=event_name,
                round1_thursday=round1_thursday,
            )
            if not chosen:
                continue
            if chosen.kind == "provenance":
                parsed = parse_provenance_json(chosen.path)
            else:
                parsed = parse_card_file(chosen.path)
            parsed = [pick for pick in parsed if pick.market_odds]
            positive = [pick for pick in parsed if (pick.ev or 0) > 0]
            pick_source = "lab_sandbox" if lane_name == "lab" else "cockpit"
            model_variant = "v5" if lane_name == "lab" else "baseline"
            tournament_id = _ensure_tournament(conn, name=event_name, event_id=event_id, year=year)
            locked = _has_locked_outcomes(conn, tournament_id)
            pick_rows = parsed_to_pick_rows(
                positive,
                tournament_id=tournament_id,
                source=pick_source,
                model_variant=model_variant,
                card_path=chosen.path,
            )
            pick_rows = dedupe_grading_picks(pick_rows)
            inserted = 0
            if not dry_run and positive and not locked:
                db.store_picks(pick_rows)
                inserted = len(pick_rows)
            else:
                inserted = len(pick_rows)

            lane_results[lane_name] = {
                "canonical_card": str(chosen.path),
                "rejected": [str(card.path) for card in rejected],
                "parsed_matchups": len(parsed),
                "positive_ev": len(positive),
                "would_insert": inserted,
                "skipped_locked": locked,
            }

        if lane_results:
            manifest.events.append(
                {
                    "event_id": event_id,
                    "name": event_name,
                    "lanes": lane_results,
                }
            )

    conn.close()
    return manifest
