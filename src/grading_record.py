"""Shared grading record helpers for API routes."""

from __future__ import annotations

from src.scoring import compute_profit


def empty_record_bucket() -> dict:
    return {
        "picks": 0,
        "wins": 0,
        "losses": 0,
        "pushes": 0,
        "profit": 0.0,
        "hit_rate": None,
    }


def empty_record_summary() -> dict:
    return {
        "outrights": empty_record_bucket(),
        "matchups": empty_record_bucket(),
        "combined": empty_record_bucket(),
    }


def record_market_bucket(bet_type: str | None) -> str:
    return "matchups" if str(bet_type or "").strip().lower() == "matchup" else "outrights"


def american_odds_rank(market_odds) -> float:
    if market_odds is not None:
        try:
            return float(int(str(market_odds).strip().replace("+", "")))
        except (TypeError, ValueError):
            pass
    return -1_000_000.0


def matchup_record_key(pick: dict) -> tuple:
    return (
        str(pick.get("source") or ""),
        str(pick.get("model_variant") or ""),
        str(pick.get("bet_type") or "").strip().lower(),
        str(pick.get("player_key") or pick.get("player_display") or "").strip().lower(),
        str(pick.get("opponent_key") or pick.get("opponent_display") or "").strip().lower(),
    )


def matchup_identity_key(pick: dict) -> tuple[str, str]:
    return (
        str(pick.get("player_key") or pick.get("player_display") or "").strip().lower(),
        str(pick.get("opponent_key") or pick.get("opponent_display") or "").strip().lower(),
    )


def dedupe_record_picks(picks: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    matchup_indexes: dict[tuple, int] = {}

    for pick in picks:
        if record_market_bucket(pick.get("bet_type")) != "matchups":
            deduped.append(pick)
            continue

        key = matchup_record_key(pick)
        existing_index = matchup_indexes.get(key)
        if existing_index is None:
            matchup_indexes[key] = len(deduped)
            deduped.append(pick)
            continue

        if american_odds_rank(pick.get("market_odds")) > american_odds_rank(deduped[existing_index].get("market_odds")):
            deduped[existing_index] = pick

    return deduped


def one_unit_profit(row: dict) -> float:
    raw_profit = row.get("profit")
    raw_stake = row.get("stake")
    if raw_profit is not None:
        stake = float(raw_stake) if raw_stake not in (None, 0) else 1.0
        return float(raw_profit) / stake

    odds_decimal = row.get("odds_decimal")
    if odds_decimal is None:
        return 0.0

    hit = int(row.get("hit") or row.get("bet_hit") or 0)
    return compute_profit(
        hit=hit,
        fraction=1.0 if hit else 0.0,
        is_push=False,
        odds_decimal=float(odds_decimal),
        stake=1.0,
    )


def finalize_record_bucket(bucket: dict) -> dict:
    picks = int(bucket["picks"])
    profit = round(float(bucket["profit"]), 2)
    return {
        "picks": picks,
        "wins": int(bucket["wins"]),
        "losses": int(bucket["losses"]),
        "pushes": int(bucket["pushes"]),
        "profit": profit,
        "hit_rate": round(int(bucket["wins"]) / picks, 3) if picks else None,
    }


def build_record_summary(picks: list[dict]) -> dict:
    summary = empty_record_summary()

    for pick in dedupe_record_picks(picks):
        profit = one_unit_profit(pick)
        hit = int(pick.get("bet_hit") if pick.get("bet_hit") is not None else pick.get("hit") or 0)
        bucket_name = record_market_bucket(pick.get("bet_type"))

        for bucket in (summary[bucket_name], summary["combined"]):
            bucket["picks"] += 1
            bucket["profit"] += profit
            if hit == 1:
                bucket["wins"] += 1
            elif round(profit, 8) == 0:
                bucket["pushes"] += 1
            else:
                bucket["losses"] += 1

    return {key: finalize_record_bucket(bucket) for key, bucket in summary.items()}


def pick_lane_sql(lane: str) -> str:
    normalized = (lane or "all").strip().lower()
    if normalized in {"cockpit", "dashboard"}:
        return " AND (COALESCE(p.source,'') IN ('cockpit','ui_display')) "
    if normalized == "lab":
        return " AND p.source IN ('lab_sandbox', 'lab_sandbox_candidate') "
    return ""


def format_graded_pick_rows(rows: list[dict]) -> list[dict]:
    payloads: list[dict] = []
    for pick in rows:
        profit = one_unit_profit(dict(pick))
        hit = int(pick.get("hit") or 0)
        outcome = "win" if hit == 1 else ("push" if profit == 0 else "loss")
        payloads.append({
            **dict(pick),
            "profit": round(profit, 2),
            "outcome": outcome,
        })
    return dedupe_record_picks(payloads)


def build_lane_comparison(dashboard_picks: list[dict], lab_picks: list[dict]) -> dict:
    dash_keys = {matchup_identity_key(pick) for pick in dashboard_picks}
    lab_keys = {matchup_identity_key(pick) for pick in lab_picks}
    overlap = dash_keys & lab_keys
    dash_profit = sum(one_unit_profit(pick) for pick in dashboard_picks)
    lab_profit = sum(one_unit_profit(pick) for pick in lab_picks)
    dash_hits = sum(int(pick.get("hit") or 0) for pick in dashboard_picks)
    lab_hits = sum(int(pick.get("hit") or 0) for pick in lab_picks)
    dash_count = len(dashboard_picks)
    lab_count = len(lab_picks)
    return {
        "profit_delta": round(dash_profit - lab_profit, 2),
        "hit_rate_delta": round(
            (dash_hits / dash_count if dash_count else 0) - (lab_hits / lab_count if lab_count else 0),
            3,
        ),
        "picks_only_dashboard": len(dash_keys - lab_keys),
        "picks_only_lab": len(lab_keys - dash_keys),
        "overlap_matchups": len(overlap),
    }
