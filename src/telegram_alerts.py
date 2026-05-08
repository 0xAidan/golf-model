"""
Personal Telegram notifications for high-EV matchup lines.

Configured via TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, and optional thresholds.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

import requests

from src import db

logger = logging.getLogger("golf.telegram_alerts")

_missing_config_warned: dict[str, bool] = {"flag": False}

_DEFAULT_EV_THRESHOLD = 0.085
_DEFAULT_MAX_ROWS = 8


def send_telegram_message(text: str) -> bool:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_raw = os.environ.get("TELEGRAM_CHAT_ID")
    chat_id: str | int | None
    if chat_raw is None or str(chat_raw).strip() == "":
        chat_id = None
    else:
        s = str(chat_raw).strip()
        try:
            chat_id = int(s)
        except ValueError:
            chat_id = s
    if not token or chat_id is None:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text},
            timeout=10.0,
        )
        if resp.status_code != 200:
            logger.warning(
                "Telegram sendMessage failed: status=%s body=%s",
                resp.status_code,
                (resp.text or "")[:500],
            )
            return False
        return True
    except requests.RequestException as exc:
        logger.warning("Telegram sendMessage request error: %s", exc)
        return False


def _parse_ev_threshold() -> float:
    raw = os.environ.get("TELEGRAM_MATCHUP_EV_THRESHOLD")
    if raw is None or str(raw).strip() == "":
        return _DEFAULT_EV_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_EV_THRESHOLD


def _parse_max_rows() -> int:
    raw = os.environ.get("TELEGRAM_MATCHUP_ALERT_MAX_ROWS")
    if raw is None or str(raw).strip() == "":
        return _DEFAULT_MAX_ROWS
    try:
        n = int(raw)
        return max(1, n)
    except ValueError:
        return _DEFAULT_MAX_ROWS


def _row_ev(row: dict[str, Any]) -> float | None:
    ev = row.get("ev")
    if ev is None:
        return None
    try:
        return float(ev)
    except (TypeError, ValueError):
        return None


def stable_alert_hash(
    *,
    event_id: str | None,
    row: dict[str, Any],
) -> str:
    mt = row.get("market_type")
    market_type = "" if mt is None else str(mt)
    odds = row.get("odds")
    odds_s = "" if odds is None else str(odds)
    parts = [
        str(event_id or ""),
        str(row.get("pick_key") or ""),
        str(row.get("opponent_key") or ""),
        str(row.get("book") or ""),
        odds_s,
        market_type,
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _format_line(row: dict[str, Any]) -> str:
    pick = row.get("pick") or row.get("pick_key") or "?"
    opp = row.get("opponent") or row.get("opponent_key") or "?"
    book = row.get("book") or "?"
    odds = row.get("odds")
    odds_s = str(odds) if odds is not None else "?"
    ev = _row_ev(row)
    ev_pct = f"{ev * 100:.1f}%" if ev is not None else "?"
    mt = row.get("market_type")
    mt_suffix = f" [{mt}]" if mt else ""
    ev_part = f"EV {ev_pct}"
    return f"• {pick} vs {opp} @ {book} {odds_s} — {ev_part}{mt_suffix}"


def maybe_send_matchup_ev_alerts(
    *,
    event_name: str | None,
    event_id: str | None,
    matchup_bets_all_books: list[dict] | None,
    matchup_diagnostics: dict | None,
) -> None:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_raw = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or chat_raw is None or str(chat_raw).strip() == "":
        if not _missing_config_warned["flag"]:
            logger.warning(
                "Telegram matchup alerts disabled: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
            )
            _missing_config_warned["flag"] = True
        return

    diag = matchup_diagnostics or {}
    if diag.get("state") == "pipeline_error":
        return
    errors = diag.get("errors")
    if errors:
        return

    rows_in = matchup_bets_all_books or []
    threshold = _parse_ev_threshold()
    max_rows = _parse_max_rows()

    qualifying: list[dict[str, Any]] = []
    for row in rows_in:
        if not isinstance(row, dict):
            continue
        ev = _row_ev(row)
        if ev is None or ev < threshold:
            continue
        qualifying.append(row)

    qualifying.sort(key=lambda r: _row_ev(r) or 0.0, reverse=True)

    fresh_lines: list[str] = []
    eid = str(event_id) if event_id is not None else ""
    for row in qualifying:
        if len(fresh_lines) >= max_rows:
            break
        h = stable_alert_hash(event_id=eid or None, row=row)
        if db.try_claim_telegram_alert(h):
            fresh_lines.append(_format_line(row))

    if not fresh_lines:
        return

    title = event_name or "Matchup"
    header = f"Matchup EV alerts — {title}"
    body = "\n".join([header] + fresh_lines)
    send_telegram_message(body)
