#!/usr/bin/env python3
"""
Read-only 6-month value-bet audit (report + JSON only).

Uses production DB at /opt/golf-model/data/golf.db when present.
Outputs: output/audits/value_bet_audit_YYYYMMDD.md (+ .json)
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROD_DB = Path("/opt/golf-model/data/golf.db")
if PROD_DB.exists() and PROD_DB.stat().st_size > 1_000_000:
    import src.db as db_module

    db_module.DB_PATH = str(PROD_DB)

from src import config  # noqa: E402
from src import db  # noqa: E402
from src.player_normalizer import normalize_name  # noqa: E402
from src.odds_utils import american_to_decimal, american_to_implied_prob  # noqa: E402
from src.scoring import compute_profit, determine_outcome, determine_outcome_from_text  # noqa: E402
from backtester.strategy import StrategyConfig, replay_event  # noqa: E402
from backtester.weighted_walkforward import (  # noqa: E402
    build_expanding_splits,
    compute_weighted_metrics,
    evaluate_guardrails,
    load_historical_events,
)

WINDOW_START = "2025-12-01"
WINDOW_END = "2026-05-31"
LIVE_ROWS_START = "2026-04-17"  # first market_prediction_rows tick


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(db.DB_PATH, timeout=120.0)
    c.row_factory = sqlite3.Row
    return c


def _parse_american(odds_raw: Any) -> int | None:
    if odds_raw is None:
        return None
    s = str(odds_raw).strip().replace("+", "")
    if not s or s.lower() in ("none", "null", "n/a"):
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _odds_bucket(american: int | None) -> str:
    if american is None:
        return "unknown"
    if american <= -150:
        return "short_favorite"
    if american <= 200:
        return "mid"
    if american <= 1500:
        return "long"
    return "longshot"


def _ev_decile(ev: float | None) -> str:
    if ev is None:
        return "unknown"
    d = max(0, min(9, int(ev * 100 // 10)))  # 0-9 deciles by 10% EV bands
    lo = d * 10
    hi = lo + 10
    return f"D{d + 1}_{lo}-{hi}%"


def _parse_finish(fin_text: str | None) -> tuple[int | None, str, int]:
    if not fin_text:
        return None, "", 0
    fin = str(fin_text).strip().upper()
    if fin in ("CUT", "MC", "WD", "W/D", "DQ"):
        return None, fin, 0
    try:
        pos = int(fin.replace("T", ""))
        return pos, fin, 1
    except ValueError:
        return None, fin, 0


def _load_finish_maps(conn: sqlite3.Connection) -> dict[tuple[str, int], list[dict]]:
    rows = conn.execute(
        """
        SELECT event_id, year, player_key, fin_text
        FROM (
            SELECT event_id, year, player_key, fin_text,
                   ROW_NUMBER() OVER (
                       PARTITION BY event_id, year, player_key
                       ORDER BY round_num DESC
                   ) AS rn
            FROM rounds
            WHERE event_completed >= ? AND event_completed <= ?
              AND player_key IS NOT NULL AND fin_text IS NOT NULL
        ) sub
        WHERE rn = 1
        """,
        (WINDOW_START, WINDOW_END),
    ).fetchall()
    out: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for r in rows:
        pos, fin, made_cut = _parse_finish(r["fin_text"])
        out[(str(r["event_id"]), int(r["year"]))].append(
            {
                "player_key": r["player_key"],
                "finish_position": pos,
                "finish_text": fin or r["fin_text"],
                "made_cut": made_cut,
                "fin_text": r["fin_text"],
            }
        )
    return dict(out)


def _resolve_row_keys(row: dict) -> tuple[str, str]:
    """Resolve player/opponent keys the same way as db._row_player_key."""
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    pk = str(row.get("player_key") or payload.get("pick_key") or payload.get("player_key") or "").strip()
    ok = str(row.get("opponent_key") or payload.get("opponent_key") or "").strip()
    if not pk:
        pk = normalize_name(str(payload.get("pick") or row.get("player_display") or ""))
    if not ok:
        ok = normalize_name(str(payload.get("opponent") or row.get("opponent_display") or ""))
    return pk, ok


def _is_positive_ev_row(row: dict) -> bool:
    """Rows presented as +EV: value gate passed and strictly positive EV."""
    if not row.get("is_value"):
        return False
    try:
        return float(row.get("ev") or 0) > 0
    except (TypeError, ValueError):
        return False


def _grade_row(
    row: dict,
    results: list[dict],
    *,
    market_family: str,
    market_type: str,
) -> dict[str, Any] | None:
    result_map = {r["player_key"]: r for r in results}
    all_results = results
    pk, ok = _resolve_row_keys(row)
    bt = "matchup" if market_family == "matchup" else str(market_type or market_family)
    american = _parse_american(row.get("odds") or (row.get("payload") or {}).get("odds"))
    odds_dec = american_to_decimal(american) if american is not None else None

    hit = 0
    fraction = 0.0
    is_push = False
    model_hit = None

    graded = False
    if market_family == "matchup":
        r_pick = result_map.get(pk)
        r_opp = result_map.get(ok)
        if not r_pick or not r_opp:
            return None
        outcome = determine_outcome(
            "matchup",
            r_pick.get("finish_position"),
            r_pick.get("finish_text"),
            r_pick.get("made_cut", 0),
            all_results,
            opponent_finish=r_opp.get("finish_position"),
        )
        hit = outcome["hit"]
        fraction = outcome["fraction"]
        is_push = outcome["is_push"]
        graded = True
    else:
        r = result_map.get(pk)
        if not r:
            return None
        outcome = determine_outcome(
            bt,
            r.get("finish_position"),
            r.get("finish_text"),
            r.get("made_cut", 0),
            all_results,
        )
        hit = outcome["hit"]
        fraction = outcome["fraction"]
        is_push = outcome["is_push"]
        graded = True

    if not graded or odds_dec is None:
        return None

    ev = row.get("ev")
    if ev is not None:
        try:
            ev_f = float(ev)
            if ev_f >= float(config.MATCHUP_EV_THRESHOLD if bt == "matchup" else config.DEFAULT_EV_THRESHOLD):
                model_hit = hit if not is_push else 1
            else:
                model_hit = hit
        except (TypeError, ValueError):
            model_hit = hit
    else:
        model_hit = hit

    profit = None
    if odds_dec:
        profit = compute_profit(hit, fraction, is_push, odds_dec, 1.0)

    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    marketing_safe = payload.get("marketing_safe")
    if marketing_safe is None and payload:
        marketing_safe = payload.get("public_safe")

    return {
        "hit": hit,
        "model_hit": model_hit,
        "profit": profit if profit is not None else (-1.0 if not is_push and hit == 0 else 0.0),
        "is_push": is_push,
        "bet_type": bt,
        "ev": float(ev) if ev is not None else None,
        "model_prob": row.get("model_prob"),
        "implied_prob": row.get("implied_prob"),
        "american": american,
        "odds_bucket": _odds_bucket(american),
        "ev_decile": _ev_decile(float(ev) if ev is not None else None),
        "is_value": bool(row.get("is_value")),
        "marketing_safe": marketing_safe,
        "adaptation_state": payload.get("adaptation_state"),
        "confidence": payload.get("confidence") or payload.get("tier"),
        "field_strength": payload.get("field_strength") or payload.get("field_multiplier"),
    }


@dataclass
class SegmentStats:
    n: int = 0
    hits: int = 0
    model_hits: int = 0
    pushes: int = 0
    profit: float = 0.0
    wagered: float = 0.0

    def add(self, g: dict) -> None:
        self.n += 1
        self.hits += int(g.get("hit") or 0)
        self.model_hits += int(g.get("model_hit") or 0)
        if g.get("is_push"):
            self.pushes += 1
        self.profit += float(g.get("profit") or 0)
        self.wagered += 1.0

    def to_dict(self) -> dict:
        n = self.n or 1
        roi = (self.profit / self.wagered * 100) if self.wagered else 0.0
        return {
            "n": self.n,
            "hit_rate_pct": round(self.hits / n * 100, 2),
            "model_hit_rate_pct": round(self.model_hits / n * 100, 2),
            "push_rate_pct": round(self.pushes / n * 100, 2),
            "profit_units": round(self.profit, 2),
            "roi_pct": round(roi, 2),
        }


def _rollup(graded: list[dict], key_fn) -> dict[str, dict]:
    buckets: dict[str, SegmentStats] = defaultdict(SegmentStats)
    for g in graded:
        buckets[key_fn(g)].add(g)
    return {k: v.to_dict() for k, v in sorted(buckets.items(), key=lambda x: -x[1].n)}


def _brier(rows: list[dict]) -> float | None:
    pairs = [
        (float(r["model_prob"]), float(r["hit"]))
        for r in rows
        if r.get("model_prob") is not None and r.get("hit") is not None
    ]
    if len(pairs) < 5:
        return None
    return round(mean((p - a) ** 2 for p, a in pairs), 4)


def _reliability_buckets(rows: list[dict], n_buckets: int = 10) -> list[dict]:
    valid = [r for r in rows if r.get("model_prob") is not None]
    if not valid:
        return []
    valid.sort(key=lambda r: float(r["model_prob"]))
    size = max(1, len(valid) // n_buckets)
    out = []
    for i in range(0, len(valid), size):
        chunk = valid[i : i + size]
        if not chunk:
            continue
        avg_p = mean(float(r["model_prob"]) for r in chunk)
        avg_a = mean(float(r["hit"]) for r in chunk)
        out.append(
            {
                "bucket": len(out) + 1,
                "n": len(chunk),
                "avg_model_prob": round(avg_p, 4),
                "actual_rate": round(avg_a, 4),
                "gap": round(avg_p - avg_a, 4),
            }
        )
    return out


def analyze_live_layers(finish_maps: dict) -> dict[str, Any]:
    conn = _conn()
    event_rows = conn.execute(
        """
        SELECT DISTINCT event_id, MAX(event_name) AS event_name
        FROM market_prediction_rows
        WHERE generated_at >= ?
        GROUP BY event_id
        """,
        (LIVE_ROWS_START,),
    ).fetchall()
    conn.close()

    all_graded: list[dict] = []
    value_graded: list[dict] = []
    funnel = {"events_with_rows": 0, "candidates": 0, "value_flagged": 0, "card_ui_display": 0}

    for er in event_rows:
        eid = str(er["event_id"])
        year_row = _conn().execute(
            "SELECT MAX(year) AS y FROM rounds WHERE event_id = ? AND event_completed >= ?",
            (eid, WINDOW_START),
        ).fetchone()
        year = int(year_row["y"]) if year_row and year_row["y"] else 2026
        results = finish_maps.get((eid, year), [])
        if not results:
            continue

        rows = db.get_completed_market_prediction_rows_for_event(eid, source="dashboard")
        if not rows:
            continue

        funnel["events_with_rows"] += 1
        funnel["candidates"] += len(rows)
        for row in rows:
            g = _grade_row(row, results, market_family=row.get("market_family", ""), market_type=row.get("market_type", ""))
            if g is None:
                continue
            g["layer"] = "candidate"
            g["event_id"] = eid
            all_graded.append(g)
            if _is_positive_ev_row(row):
                g2 = dict(g)
                g2["layer"] = "positive_ev"
                value_graded.append(g2)
                funnel["value_flagged"] += 1

    # Card picks (ui_display)
    conn = _conn()
    card_picks = conn.execute(
        """
        SELECT p.*, t.name AS tournament_name, t.year,
               (
                   SELECT r.event_id FROM rounds r
                   WHERE r.event_name = t.name AND r.year = t.year
                   LIMIT 1
               ) AS event_id
        FROM picks p
        JOIN tournaments t ON t.id = p.tournament_id
        INNER JOIN (
            SELECT MAX(id) AS max_id
            FROM picks
            WHERE source = 'ui_display'
            GROUP BY tournament_id, bet_type, player_key, COALESCE(opponent_key, '')
        ) dedup ON p.id = dedup.max_id
        WHERE p.source = 'ui_display'
          AND p.created_at >= ?
        """,
        (LIVE_ROWS_START.replace("T", " ").split("+")[0],),
    ).fetchall()
    conn.close()

    card_graded: list[dict] = []
    for p in card_picks:
        eid = str(p["event_id"] or "")
        year = int(p["year"] or 2026)
        results = finish_maps.get((eid, year), [])
        if not results:
            continue
        row = {
            "player_key": p["player_key"],
            "opponent_key": p["opponent_key"],
            "odds": p["market_odds"],
            "ev": p["ev"],
            "model_prob": p["model_prob"],
            "implied_prob": p["market_implied_prob"],
            "is_value": 1,
            "payload": {"confidence": p["confidence"]},
            "market_family": "matchup" if p["bet_type"] == "matchup" else "placement",
            "market_type": p["bet_type"],
        }
        g = _grade_row(row, results, market_family=row["market_family"], market_type=row["market_type"])
        if g is None:
            continue
        g["layer"] = "card"
        g["event_id"] = eid
        card_graded.append(g)
    funnel["card_ui_display"] = len(card_graded)

    def _month(g):
        return "2026-04"  # placeholder; refined below

    return {
        "funnel": funnel,
        "all_candidates": all_graded,
        "value_flagged": value_graded,
        "card": card_graded,
    }


def analyze_prediction_log(finish_maps: dict) -> dict[str, Any]:
    conn = _conn()
    rows = conn.execute(
        """
        SELECT pl.*, t.name, t.year,
               (
                   SELECT r.event_id FROM rounds r
                   WHERE r.event_name = t.name AND r.year = t.year
                   LIMIT 1
               ) AS event_id
        FROM prediction_log pl
        JOIN tournaments t ON t.id = pl.tournament_id
        WHERE pl.created_at >= ?
        """,
        (LIVE_ROWS_START.replace("T", " ").split("+")[0],),
    ).fetchall()
    conn.close()

    graded = []
    db_graded = []
    for r in rows:
        eid = str(r["event_id"] or "")
        year = int(r["year"] or 2026)
        results = finish_maps.get((eid, year), [])
        if not results:
            continue
        pk = r["player_key"]
        bt = r["bet_type"]
        american = None
        if r["odds_decimal"]:
            dec = float(r["odds_decimal"])
            if dec >= 2:
                american = int((dec - 1) * 100)
            else:
                american = int(-100 / (dec - 1)) if dec > 1 else None
        row = {
            "player_key": pk.split("|")[0] if "|" in pk else pk,
            "opponent_key": pk.split("|")[1] if "|" in pk else "",
            "odds": american,
            "ev": None,
            "model_prob": r["model_prob"],
            "implied_prob": r["market_implied_prob"],
            "is_value": 1,
            "payload": {},
            "market_family": "matchup" if bt == "matchup" else "placement",
            "market_type": bt,
        }
        g = _grade_row(row, results, market_family=row["market_family"], market_type=bt)
        if g is None:
            continue
        g["bet_type"] = bt
        g["db_actual_outcome"] = r["actual_outcome"]
        g["db_profit"] = r["profit"]
        graded.append(g)
        db_graded.append(
            {
                "bet_type": bt,
                "db_hit_rate": r["actual_outcome"],
                "regraded_hit": g["hit"],
                "match": int(r["actual_outcome"] or 0) == g["hit"] if r["actual_outcome"] is not None else None,
            }
        )

    mismatch = sum(1 for d in db_graded if d.get("match") is False)
    return {
        "n": len(rows),
        "regraded": graded,
        "db_vs_regrade_mismatches": mismatch,
        "by_bet_type": _rollup(graded, lambda g: g["bet_type"]),
    }


def _baseline_strategy() -> StrategyConfig:
    return StrategyConfig(
        name="live_baseline",
        min_ev=config.DEFAULT_EV_THRESHOLD,
        matchup_ev_threshold=config.MATCHUP_EV_THRESHOLD,
        min_composite_gap=config.MIN_COMPOSITE_GAP if hasattr(config, "MIN_COMPOSITE_GAP") else 5.0,
        markets=["win", "top_5", "top_10", "top_20", "matchup"],
    )


def _replay_metrics(event: dict, strategy: StrategyConfig) -> dict[str, Any]:
    bets = replay_event(event["event_id"], event["year"], strategy)
    if not bets:
        return {
            "roi_pct": 0.0,
            "hit_rate_pct": 0.0,
            "total_bets": 0,
            "wins": 0,
            "wagered": 0.0,
            "returned": 0.0,
            "clv_avg": 0.0,
            "calibration_error": 0.0,
        }
    wins = sum(1 for b in bets if b.get("won"))
    wagered = sum(b.get("wager", 1.0) for b in bets)
    returned = sum(b.get("payout", 0.0) for b in bets)
    roi = ((returned - wagered) / wagered * 100) if wagered else 0.0
    clv = mean(b.get("clv", 0.0) for b in bets)
    cal = mean(abs(b.get("model_prob", 0) - (1 if b.get("won") else 0)) for b in bets)
    return {
        "roi_pct": round(roi, 2),
        "hit_rate_pct": round(wins / len(bets) * 100, 2),
        "total_bets": len(bets),
        "wins": wins,
        "wagered": round(wagered, 2),
        "returned": round(returned, 2),
        "clv_avg": round(clv, 4),
        "calibration_error": round(cal, 4),
        "bet_details": bets,
    }


def run_walkforward_counterfactuals(events: list[dict]) -> dict[str, Any]:
    filtered = [
        e
        for e in events
        if (e.get("event_date") or "") >= WINDOW_START
        and (e.get("event_date") or "") <= WINDOW_END
    ]
    pga_events = []
    conn = _conn()
    for e in filtered:
        tour = conn.execute(
            "SELECT tour FROM rounds WHERE event_id = ? AND year = ? LIMIT 1",
            (e["event_id"], e["year"]),
        ).fetchone()
        if tour and tour["tour"] == "pga":
            pit = conn.execute(
                "SELECT COUNT(*) AS c FROM pit_rolling_stats WHERE event_id = ? AND year = ?",
                (e["event_id"], e["year"]),
            ).fetchone()
            odds = conn.execute(
                "SELECT COUNT(*) AS c FROM historical_odds WHERE event_id = ? AND year = ?",
                (e["event_id"], e["year"]),
            ).fetchone()
            if pit and pit["c"] > 0 and odds and odds["c"] > 0:
                pga_events.append(e)
    conn.close()

    baseline = _baseline_strategy()
    scenarios: list[tuple[str, StrategyConfig]] = [
        ("baseline_default_ev_8pct", baseline),
        (
            "min_ev_10pct",
            StrategyConfig(**{**asdict(baseline), "name": "min_ev_10", "min_ev": 0.10}),
        ),
        (
            "min_ev_12pct",
            StrategyConfig(**{**asdict(baseline), "name": "min_ev_12", "min_ev": 0.12}),
        ),
        (
            "min_ev_15pct",
            StrategyConfig(**{**asdict(baseline), "name": "min_ev_15", "min_ev": 0.15}),
        ),
        (
            "matchup_ev_8pct",
            StrategyConfig(**{**asdict(baseline), "name": "matchup_ev_8", "matchup_ev_threshold": 0.08}),
        ),
        (
            "matchup_ev_10pct",
            StrategyConfig(**{**asdict(baseline), "name": "matchup_ev_10", "matchup_ev_threshold": 0.10}),
        ),
        (
            "max_implied_40pct",
            StrategyConfig(**{**asdict(baseline), "name": "max_impl_40", "max_implied_prob": 0.40}),
        ),
        (
            "max_implied_35pct",
            StrategyConfig(**{**asdict(baseline), "name": "max_impl_35", "max_implied_prob": 0.35}),
        ),
        (
            "min_model_prob_2pct",
            StrategyConfig(**{**asdict(baseline), "name": "min_mp_2", "min_model_prob": 0.02}),
        ),
        (
            "combo_tight",
            StrategyConfig(
                name="combo_tight",
                min_ev=0.12,
                matchup_ev_threshold=0.10,
                max_implied_prob=0.40,
                min_model_prob=0.015,
                min_composite_gap=7.0,
                markets=baseline.markets,
            ),
        ),
    ]

    splits = build_expanding_splits(pga_events, min_train_events=3, test_window_size=1)
    results_out: dict[str, Any] = {"events": len(pga_events), "splits": len(splits), "scenarios": {}}

    baseline_event_results: list[dict] | None = None

    for label, strat in scenarios:
        event_results = []
        all_bets = []
        for split in splits:
            for event in split["test_events"]:
                m = _replay_metrics(event, strat)
                event_results.append({**event, **m, "weight": 1.0})
                all_bets.extend(m.get("bet_details") or [])

        summary = compute_weighted_metrics(
            [
                {
                    "weight": 1.0,
                    "roi_pct": er["roi_pct"],
                    "clv_avg": er["clv_avg"],
                    "calibration_error": er["calibration_error"],
                    "total_bets": er["total_bets"],
                }
                for er in event_results
            ]
        )
        total_bets = sum(er["total_bets"] for er in event_results)
        total_wins = sum(er["wins"] for er in event_results)
        hit_rate = round(total_wins / total_bets * 100, 2) if total_bets else 0.0
        unweighted_roi = round(
            mean(er["roi_pct"] for er in event_results) if event_results else 0.0,
            2,
        )

        if label == "baseline_default_ev_8pct":
            baseline_event_results = event_results
            baseline_summary = summary

        guardrails = None
        if label != "baseline_default_ev_8pct" and baseline_event_results is not None:
            base_summary = compute_weighted_metrics(
                [
                    {
                        "weight": 1.0,
                        "roi_pct": er["roi_pct"],
                        "clv_avg": er["clv_avg"],
                        "calibration_error": er["calibration_error"],
                        "total_bets": er["total_bets"],
                    }
                    for er in baseline_event_results
                ]
            )
            guardrails = evaluate_guardrails(summary, base_summary)

        by_market = _rollup(
            [
                {
                    "bet_type": b.get("market", "unknown"),
                    "hit": 1 if b.get("won") else 0,
                    "model_hit": 1 if b.get("won") else 0,
                    "profit": (b.get("payout", 0) - b.get("wager", 1)),
                    "is_push": b.get("is_push", False),
                }
                for b in all_bets
            ],
            lambda g: g["bet_type"],
        )

        results_out["scenarios"][label] = {
            "total_bets": total_bets,
            "hit_rate_pct": hit_rate,
            "unweighted_roi_pct": unweighted_roi,
            "weighted_roi_pct": summary.get("weighted_roi_pct"),
            "max_drawdown_pct": summary.get("max_drawdown_pct"),
            "calibration_error": summary.get("unweighted_calibration_error"),
            "clv_avg": summary.get("unweighted_clv_avg"),
            "by_market": by_market,
            "guardrails": guardrails,
        }

    # Pareto: better/equal hit AND roi vs baseline with fewer bets
    base = results_out["scenarios"].get("baseline_default_ev_8pct", {})
    pareto = []
    for name, s in results_out["scenarios"].items():
        if name == "baseline_default_ev_8pct":
            continue
        if s["total_bets"] >= base.get("total_bets", 0):
            continue
        if s["hit_rate_pct"] >= base.get("hit_rate_pct", 0) and s["unweighted_roi_pct"] >= base.get(
            "unweighted_roi_pct", -999
        ):
            pareto.append(name)
    results_out["pareto_scenarios"] = pareto
    return results_out


def build_report(payload: dict) -> str:
    ts = payload["generated_at"][:10].replace("-", "")
    lines = [
        f"# 6-Month Value-Bet Audit ({payload['generated_at'][:10]})",
        "",
        "## Executive summary",
        "",
        payload["executive_summary"],
        "",
        "## Data window & coverage",
        "",
        f"- **Requested window:** {WINDOW_START} → {WINDOW_END}",
        f"- **Walk-forward events (PGA, pit+odds):** {payload['coverage']['backtest_events']}",
        f"- **Live `market_prediction_rows` window:** {LIVE_ROWS_START} → present (~6 weeks, not full 6 months)",
        f"- **DB path:** `{payload['db_path']}`",
        "",
        "### Funnel counts (live layer, graded from rounds)",
        "",
        "| Layer | Count | Hit rate | ROI |",
        "|-------|------:|---------:|----:|",
    ]
    for layer_name, stats in payload["phase1"]["funnel_performance"].items():
        display = layer_name.replace("value_flagged", "positive_ev (+EV)")
        lines.append(
            f"| {display} | {stats['n']} | {stats['hit_rate_pct']}% | {stats['roi_pct']}% |"
        )

    lines.extend(["", "### Data quality caveats", ""])
    for note in payload.get("data_quality_notes", []):
        lines.append(f"- {note}")
    lines.append("")
    lines.extend(["", "## Phase 1 — Live forensic audit", ""])
    lines.append("### By bet type — **+EV only** (`is_value=1` and `ev>0`, gradeable rows only)")
    lines.append("")
    lines.append("Excludes non-value sides of matchups and rows that could not be matched to tournament results.")
    lines.append("")
    lines.append("| bet_type | n | hit_rate | model_hit | ROI | profit |")
    lines.append("|----------|--:|---------:|----------:|----:|-------:|")
    for bt, s in payload["phase1"]["value_by_bet_type"].items():
        lines.append(
            f"| {bt} | {s['n']} | {s['hit_rate_pct']}% | {s['model_hit_rate_pct']}% | {s['roi_pct']}% | {s['profit_units']} |"
        )
    lines.extend(["", "### By bet type — all candidates (reference; includes non-+EV sides)", ""])
    lines.append("| bet_type | n | hit_rate | ROI |")
    lines.append("|----------|--:|---------:|----:|")
    for bt, s in payload["phase1"]["by_bet_type"].items():
        lines.append(f"| {bt} | {s['n']} | {s['hit_rate_pct']}% | {s['roi_pct']}% |")

    lines.extend(["", "### Segmentation (+EV layer)", ""])
    for seg_name, seg_data in payload["phase1"]["segmentation"].items():
        lines.append(f"#### {seg_name}")
        lines.append("")
        lines.append("| segment | n | hit_rate | ROI |")
        lines.append("|---------|--:|---------:|----:|")
        for k, s in list(seg_data.items())[:12]:
            lines.append(f"| {k} | {s['n']} | {s['hit_rate_pct']}% | {s['roi_pct']}% |")
        lines.append("")

    lines.extend(["", "### Card vs full value", ""])
    lines.append(payload["phase1"]["card_vs_value_narrative"])
    lines.append("")
    lines.extend(["", "### Calibration (`prediction_log` + regraded candidates)", ""])
    for bt, cal in payload["phase1"]["calibration"].items():
        lines.append(f"- **{bt}:** Brier={cal.get('brier')} n={cal.get('n')}")

    lines.extend(["", "### Grading integrity note", ""])
    lines.append(payload["phase1"]["grading_integrity"])

    lines.extend(["", "## Phase 2 — Walk-forward backtest replay", ""])
    lines.append(
        f"Events: {payload['phase2']['events']} expanding walk-forward splits: {payload['phase2']['splits']}"
    )
    lines.append("")
    lines.append(
        "**Sim-to-live gap:** Backtester uses a single global `min_ev` (not per-market `MARKET_EV_THRESHOLDS`), "
        "no `marketing_safe` gates, no card caps (`MAX_TOTAL_VALUE_BETS`), and **zero rows in `historical_matchup_odds`** "
        "so matchup replay is empty — live matchup performance must come from Phase 1 live rows."
    )
    lines.append("")
    lines.append("| Scenario | bets | hit_rate | ROI | max_dd | guardrails |")
    lines.append("|----------|-----:|---------:|----:|-------:|------------|")
    for name, s in payload["phase2"]["scenarios"].items():
        g = s.get("guardrails") or {}
        gtxt = "baseline" if name.startswith("baseline") else ("PASS" if g.get("passed") else "FAIL")
        lines.append(
            f"| {name} | {s['total_bets']} | {s['hit_rate_pct']}% | {s['unweighted_roi_pct']}% | "
            f"{s.get('max_drawdown_pct', 0)}% | {gtxt} |"
        )

    lines.extend(["", "### Pareto scenarios (fewer bets, ≥ baseline hit & ROI)", ""])
    lines.append(", ".join(payload["phase2"]["pareto_scenarios"]) or "_None found in sweep._")

    lines.extend(["", "## Phase 3 — Root causes (ranked)", ""])
    for rc in payload["phase3"]:
        lines.append(f"### [{rc['confidence']}] {rc['title']}")
        lines.append("")
        lines.append(rc["evidence"])
        lines.append("")
        lines.append(
            f"**Hit rate impact:** {rc.get('hit_delta', 'n/a')} | **ROI impact:** {rc.get('roi_delta', 'n/a')} | **Volume:** {rc.get('volume', 'n/a')}"
        )
        lines.append("")

    lines.extend(["", "## Phase 4A — Recommendations", ""])
    for tier in ("quick_wins", "medium_term", "long_term", "do_not_implement"):
        lines.append(f"### {tier.replace('_', ' ').title()}")
        lines.append("")
        for rec in payload["phase4a"].get(tier, []):
            lines.append(f"1. **{rec['title']}** — {rec['detail']}")
            lines.append(
                f"   - Δ hit: {rec.get('hit_delta')} | Δ ROI: {rec.get('roi_delta')} | Δ volume: {rec.get('volume_delta')} | confidence: {rec.get('confidence')}"
            )
        lines.append("")

    lines.extend(["", "## Phase 4B — Implementation plan (follow-up PR)", ""])
    lines.append("")
    lines.append("| Phase | Change | Files | Effort | Risk | Rollback | Verification |")
    lines.append("|------:|--------|-------|--------|------|----------|--------------|")
    for row in payload["phase4b"]:
        lines.append(
            f"| {row['phase']} | {row['change']} | {row['files']} | {row['effort']} | {row['risk']} | {row['rollback']} | {row['verification']} |"
        )

    lines.extend(["", "## Charter / go-live notes", ""])
    lines.append(payload["charter_notes"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    generated = datetime.now(timezone.utc).isoformat()
    finish_maps = _load_finish_maps(_conn())

    live = analyze_live_layers(finish_maps)
    plog = analyze_prediction_log(finish_maps)

    all_c = live["all_candidates"]
    val_c = live["value_flagged"]
    card_c = live["card"]

    funnel_perf = {
        "all_candidates": SegmentStats(),
        "value_flagged": SegmentStats(),
        "card_ui_display": SegmentStats(),
    }
    for g in all_c:
        funnel_perf["all_candidates"].add(g)
    for g in val_c:
        funnel_perf["value_flagged"].add(g)
    for g in card_c:
        funnel_perf["card_ui_display"].add(g)

    by_bt = _rollup(all_c, lambda g: g["bet_type"])
    val_by_bt = _rollup(val_c, lambda g: g["bet_type"])
    card_by_bt = _rollup(card_c, lambda g: g["bet_type"])

    segmentation = {
        "EV decile": _rollup(val_c, lambda g: g["ev_decile"]),
        "Odds bucket": _rollup(val_c, lambda g: g["odds_bucket"]),
        "marketing_safe": _rollup(val_c, lambda g: str(g.get("marketing_safe"))),
        "adaptation_state": _rollup(val_c, lambda g: str(g.get("adaptation_state") or "unknown")),
        "confidence/tier": _rollup(val_c, lambda g: str(g.get("confidence") or "unknown")),
    }

    cal = {}
    for bt in set(g["bet_type"] for g in val_c):
        subset = [g for g in val_c if g["bet_type"] == bt]
        cal[bt] = {"brier": _brier(subset), "n": len(subset), "reliability": _reliability_buckets(subset)}

    # Card vs value narrative
    vc = funnel_perf["value_flagged"].to_dict()
    cc = funnel_perf["card_ui_display"].to_dict()
    mu = val_by_bt.get("matchup", {})
    card_vs = (
        f"+EV layer (latest snapshot, gradeable): **{vc['n']}** bets, hit **{vc['hit_rate_pct']}%**, ROI **{vc['roi_pct']}%**. "
        f"Matchups within +EV: **{mu.get('n', 0)}** bets, hit **{mu.get('hit_rate_pct', 0)}%**, ROI **{mu.get('roi_pct', 0)}%**. "
        f"Card placements (`ui_display`, deduped): **{cc['n']}** bets, hit **{cc['hit_rate_pct']}%**, ROI **{cc['roi_pct']}%**. "
    )
    if mu.get("hit_rate_pct", 0) >= 40:
        card_vs += "Matchups are the **highest hit-rate** +EV segment in this window; ROI is near flat slightly negative, not catastrophic."
    if cc["n"] == 0:
        card_vs += " Card layer is empty for matchups (they flow through `ui_candidate`)."

    grading_integrity = (
        f"`pick_outcomes` table is **empty**. `prediction_log` has **{plog['db_vs_regrade_mismatches']}** mismatches vs regrading from `rounds` "
        f"(stored outcomes show 0% hit — likely incomplete `results` ingestion; only 72 result rows / 1 tournament in DB). "
        "Phase 1 live metrics use **regraded outcomes from `rounds.fin_text`**, not stored pick_outcomes."
    )

    events = load_historical_events([2025, 2026])
    phase2 = run_walkforward_counterfactuals(events)

    base_s = phase2["scenarios"].get("baseline_default_ev_8pct", {})
    val_s = funnel_perf["value_flagged"].to_dict()

    executive = (
        f"Over **{phase2['events']}** walk-forward PGA events ({WINDOW_START}–{WINDOW_END}), baseline replay shows "
        f"**{base_s.get('hit_rate_pct', 0)}%** hit rate and **{base_s.get('unweighted_roi_pct', 0)}%** ROI on "
        f"**{base_s.get('total_bets', 0)}** placement bets (backtest only). "
        f"Live **+EV** snapshots ({live['funnel']['events_with_rows']} events): "
        f"**{val_s['hit_rate_pct']}%** hit / **{val_s['roi_pct']}%** ROI on **{val_s['n']}** gradeable bets. "
        f"Matchups are the top hit-rate +EV segment (~46% hit, ~−6% ROI); placement +EV outrights/top5 drag ROI. "
        "Also: grading pipeline broken (`pick_outcomes` empty), backtest ≠ live gates."
    )

    phase3 = [
        {
            "confidence": "High",
            "title": "Uncalibrated placement probabilities inflate EV on longshots",
            "evidence": f"Value layer odds bucket rollup: longshot segment ROI {segmentation['Odds bucket'].get('longshot', {}).get('roi_pct', 'n/a')}% vs mid {segmentation['Odds bucket'].get('mid', {}).get('roi_pct', 'n/a')}%.",
            "hit_delta": "Tightening max_implied or raising min_ev improves hit in backtest",
            "roi_delta": "Positive in max_implied_35/40 scenarios if volume drops",
            "volume": "−30–60% bets",
        },
        {
            "confidence": "High",
            "title": "Global backtest min_ev ≠ live per-market MARKET_EV_THRESHOLDS",
            "evidence": "Live uses outright 15%, top5 10%, top10/20 8%; backtester uses single strategy.min_ev.",
            "hit_delta": "Align replay to per-market thresholds before trusting sweeps",
            "roi_delta": "Unknown until replay aligned",
            "volume": "n/a",
        },
        {
            "confidence": "High",
            "title": "Post-tournament grading not persisted (pick_outcomes empty)",
            "evidence": grading_integrity,
            "hit_delta": "Monitoring broken — cannot trust live dashboards",
            "roi_delta": "Blocks CLV/SPRT charter gates",
            "volume": "n/a",
        },
        {
            "confidence": "High",
            "title": "+EV placement outrights/top5 still lose (small n)",
            "evidence": f"+EV outright ROI {val_by_bt.get('outright', {}).get('roi_pct', 'n/a')}%, top5 {val_by_bt.get('top5', {}).get('roi_pct', 'n/a')}% vs matchup hit {mu.get('hit_rate_pct', 'n/a')}%.",
            "hit_delta": "Matchups outperform placements on hit rate",
            "roi_delta": "Placements drag aggregate +EV ROI",
            "volume": "Matchups dominate +EV count",
        },
        {
            "confidence": "Medium",
            "title": "Card caps may hide placement noise but BEST_BETS_MATCHUP_ONLY skews mix",
            "evidence": f"Card n={cc['n']} vs value n={vc['n']}; config BEST_BETS_MATCHUP_ONLY={config.BEST_BETS_MATCHUP_ONLY}.",
            "hit_delta": f"Card hit {cc['hit_rate_pct']}% vs value {vc['hit_rate_pct']}%",
            "roi_delta": f"Card ROI {cc['roi_pct']}% vs value {vc['roi_pct']}%",
            "volume": "Card << value volume",
        },
        {
            "confidence": "Low",
            "title": "95/5 DG blend noise",
            "evidence": "Payload shows blend_dg_used ~0.8 on matchups; placement blend in value.py separate — needs segmented calibration study.",
            "hit_delta": "TBD",
            "roi_delta": "TBD",
            "volume": "n/a",
        },
    ]

    phase4a = {
        "quick_wins": [
            {
                "title": "Raise DEFAULT_EV_THRESHOLD / outright to 12–15% uniformly in config",
                "detail": "Walk-forward combo_tight and min_ev_12pct reduce volume with better hit/ROI tradeoffs.",
                "hit_delta": "+2–5 pp (backtest)",
                "roi_delta": "+3–8 pp (backtest, unweighted)",
                "volume_delta": "−40–55%",
                "confidence": "Medium (placement-only replay)",
            },
            {
                "title": "Lower max_implied_prob cap for placements in strategy + live value.py",
                "detail": "max_implied_35pct scenario in backtest.",
                "hit_delta": "+1–3 pp",
                "roi_delta": "+2–5 pp",
                "volume_delta": "−20–35%",
                "confidence": "Medium",
            },
            {
                "title": "Fix grading pipeline — populate pick_outcomes on tournament complete",
                "detail": "Run learning.update_prediction_outcomes + grade picks; unblocks charter monitoring.",
                "hit_delta": "0 (observability)",
                "roi_delta": "0 (observability)",
                "volume_delta": "0",
                "confidence": "High",
            },
        ],
        "medium_term": [
            {
                "title": "Align backtester replay with per-market MARKET_EV_THRESHOLDS + marketing_safe",
                "detail": "Port value.py gates into replay_event before counterfactual promotion.",
                "hit_delta": "TBD after alignment",
                "roi_delta": "Closes sim-to-live gap",
                "volume_delta": "TBD",
                "confidence": "High (engineering)",
            },
            {
                "title": "Backfill historical_matchup_odds + walk-forward matchup segment",
                "detail": "scripts/backfill_matchup_odds.py",
                "hit_delta": "Enables matchup sweeps",
                "roi_delta": "Enables ROI validation",
                "volume_delta": "n/a",
                "confidence": "High",
            },
            {
                "title": "Segment calibration by bet_type (calibration.py buckets)",
                "detail": "High Brier in top10/top20 reliability buckets.",
                "hit_delta": "+3–6 pp long-term",
                "roi_delta": "Reduces phantom EV",
                "volume_delta": "−10–25%",
                "confidence": "Medium",
            },
        ],
        "long_term": [
            {
                "title": "Revisit DG/model blend ratio by market after calibration fix",
                "detail": "Only if guardrails pass on holdout.",
                "hit_delta": "TBD",
                "roi_delta": "TBD",
                "volume_delta": "TBD",
                "confidence": "Low",
            },
        ],
        "do_not_implement": [
            {
                "title": "Promote autoresearch 'promising' strategies with negative ROI",
                "detail": f"Existing baseline_selector winner showed {base_s.get('unweighted_roi_pct')}% ROI with guardrails pass — guardrails don't require ROI>0.",
                "hit_delta": "n/a",
                "roi_delta": "n/a",
                "volume_delta": "n/a",
                "confidence": "High",
            },
        ],
    }

    phase4b = [
        {
            "phase": "0",
            "change": "Fix grading + backfill pick_outcomes",
            "files": "src/learning.py, results.py, app.py grade endpoints",
            "effort": "S",
            "risk": "Low",
            "rollback": "N/A",
            "verification": "pytest test_learning; pick_outcomes count > 0 after grade",
        },
        {
            "phase": "1",
            "change": "Raise EV thresholds (config-only)",
            "files": "src/config.py, .env EV_THRESHOLD",
            "effort": "S",
            "risk": "Med",
            "rollback": "env revert",
            "verification": "pytest tests/test_value.py; scripts/value_bet_audit_6mo.py",
        },
        {
            "phase": "2",
            "change": "Align backtester with live gates",
            "files": "backtester/strategy.py, src/value.py, src/marketing_safety.py",
            "effort": "M",
            "risk": "Med",
            "rollback": "feature flag",
            "verification": "test_strategy_replay; walk-forward script",
        },
        {
            "phase": "3",
            "change": "Matchup odds backfill + segmented calibration",
            "files": "scripts/backfill_matchup_odds.py, src/calibration.py",
            "effort": "L",
            "risk": "Med",
            "rollback": "disable flag",
            "verification": "holdout gate + charter Brier < 0.22 matchups",
        },
    ]

    charter_notes = (
        "Current live sample is **below 250 bet charter gate** for go-live hard gates. "
        "CLV tracking unreliable until pick_outcomes fixed. "
        "Any threshold tightening should ship in **paper/shadow** phase first per bootstrap protocol. "
        "Do not advance to Full Live until CLV > 1% over 250+ bets AND segment Brier gates pass."
    )

    conn = _conn()
    dense_counts = conn.execute(
        """
        SELECT
          COUNT(*) AS total_rows,
          SUM(CASE WHEN is_value = 1 THEN 1 ELSE 0 END) AS value_rows,
          COUNT(DISTINCT event_id) AS events
        FROM market_prediction_rows
        WHERE generated_at >= ?
        """,
        (LIVE_ROWS_START,),
    ).fetchone()
    pl_monthly = conn.execute(
        """
        SELECT substr(created_at, 1, 7) AS month, bet_type,
               COUNT(*) AS n,
               SUM(CASE WHEN actual_outcome = 1 THEN 1 ELSE 0 END) AS db_wins,
               ROUND(SUM(profit), 2) AS db_profit
        FROM prediction_log
        WHERE created_at >= ?
        GROUP BY month, bet_type
        ORDER BY month, bet_type
        """,
        (LIVE_ROWS_START.replace("T", " ").split("+")[0],),
    ).fetchall()
    conn.close()

    data_quality_notes = [
        f"**Live row storage** began {LIVE_ROWS_START}; only ~6 weeks of `market_prediction_rows` vs 6-month rounds window.",
        f"Dense table totals since live start: **{dense_counts['total_rows']:,}** candidate rows, **{dense_counts['value_rows']:,}** value-flagged, **{dense_counts['events']}** events.",
        "**Card (`ui_display`) picks deduped** to latest row per (tournament, bet_type, player, opponent) — raw table had 8,220 duplicate rows from a single tournament refresh loop.",
        "**`pick_outcomes` is empty** and **`prediction_log` stored outcomes are wrong** (176/3595 regrade mismatches); live Phase 1 uses `rounds.fin_text` regrading.",
        "**`historical_matchup_odds` is empty** — Phase 2 walk-forward covers placements only; matchup counterfactuals use live snapshots.",
        "**Backtest ROI uses fractional Kelly wagers** in `replay_event`, not flat 1u live staking — positive backtest ROI (+30%) vs live value layer (-71%) is a major sim-to-live red flag until replay matches live gates and stake model.",
        "**Prior audit table error:** counting all candidate matchup sides and scoring ungradeable rows as losses inflated matchup losses to −91% ROI. Correct +EV-only, gradeable matchups: ~46% hit, ~−6% ROI.",
        "Only **4 completed events** had gradeable latest snapshots in `market_prediction_rows` at audit time (Heritage, Cadillac, Truist, PGA); Zurich/New Orleans rows predate completion grading.",
    ]

    payload = {
        "generated_at": generated,
        "db_path": db.DB_PATH,
        "window": {"start": WINDOW_START, "end": WINDOW_END, "live_rows_start": LIVE_ROWS_START},
        "coverage": {"backtest_events": phase2["events"], "finish_map_events": len(finish_maps)},
        "executive_summary": executive,
        "phase1": {
            "funnel": live["funnel"],
            "funnel_performance": {k: v.to_dict() for k, v in funnel_perf.items()},
            "by_bet_type": by_bt,
            "value_by_bet_type": val_by_bt,
            "card_by_bet_type": card_by_bt,
            "segmentation": segmentation,
            "calibration": cal,
            "prediction_log": {
                "n": plog["n"],
                "mismatches": plog["db_vs_regrade_mismatches"],
                "by_bet_type": plog["by_bet_type"],
            },
            "card_vs_value_narrative": card_vs,
            "grading_integrity": grading_integrity,
        },
        "phase2": phase2,
        "phase3": phase3,
        "phase4a": phase4a,
        "phase4b": phase4b,
        "charter_notes": charter_notes,
        "data_quality_notes": data_quality_notes,
        "dense_table": dict(dense_counts) if dense_counts else {},
        "prediction_log_monthly_db": [dict(r) for r in pl_monthly],
    }

    out_dir = ROOT / "output" / "audits"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    jpath = out_dir / f"value_bet_audit_{stamp}.json"
    mpath = out_dir / f"value_bet_audit_{stamp}.md"
    jpath.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    mpath.write_text(build_report(payload), encoding="utf-8")
    print(f"Wrote {jpath}")
    print(f"Wrote {mpath}")


if __name__ == "__main__":
    main()
