"""Two-tier registry for research champion and live weekly model."""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass
from typing import Any

from backtester.experiments import get_active_strategy
from backtester.strategy import StrategyConfig
from src import db


@dataclass
class PromotionGateResult:
    passed: bool
    reasons: list[str]
    metrics: dict[str, Any]


class PromotionGateError(ValueError):
    """Raised when live promotion is blocked by charter gates."""

    def __init__(self, message: str, result: PromotionGateResult):
        super().__init__(message)
        self.result = result


class HoldoutGateError(ValueError):
    """Raised when holdout evidence is missing or failed."""


def _strategy_from_json(strategy_config_json: str | None) -> StrategyConfig | None:
    if not strategy_config_json:
        return None
    try:
        return StrategyConfig.from_json(strategy_config_json)
    except Exception:
        return None


def _current_row(table: str, scope: str) -> dict[str, Any] | None:
    conn = db.get_conn()
    row = conn.execute(
        f"""
        SELECT * FROM {table}
        WHERE scope = ? AND is_current = 1
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (scope,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_research_champion(scope: str = "global") -> StrategyConfig:
    row = _current_row("research_model_registry", scope)
    strategy = _strategy_from_json(row["strategy_config_json"]) if row else None
    return strategy or get_active_strategy(scope) or StrategyConfig(name="default_research_champion")


def get_research_champion_record(scope: str = "global") -> dict[str, Any] | None:
    row = _current_row("research_model_registry", scope)
    if not row:
        return None
    row["strategy"] = _strategy_from_json(row.get("strategy_config_json"))
    return row


def evaluate_live_promotion_gates(scope: str = "global") -> PromotionGateResult:
    """
    Evaluate hard gates from project charter before promoting to live.
    """
    from src.learning import compute_calibration
    from src.clv import compute_clv_summary

    calibration = compute_calibration()
    clv = compute_clv_summary()
    conn = db.get_conn()
    prediction_rows = conn.execute(
        """
        SELECT bet_type, model_prob, actual_outcome, profit
        FROM prediction_log
        WHERE model_prob IS NOT NULL AND actual_outcome IS NOT NULL
        """
    ).fetchall()
    conn.close()

    total_bets = int((calibration.get("roi") or {}).get("total_bets", 0) if isinstance(calibration, dict) else 0)
    avg_clv_pct = clv.get("avg_clv_pct")

    clv_conn = db.get_conn()
    clv_rows = clv_conn.execute("SELECT clv_pct FROM clv_log WHERE clv_pct IS NOT NULL").fetchall()
    clv_conn.close()
    clv_hit_rate = 0.0
    if clv_rows:
        positive = sum(1 for row in clv_rows if (row["clv_pct"] or 0) > 0)
        clv_hit_rate = (positive / len(clv_rows)) * 100.0

    matchup_rows = [row for row in prediction_rows if (row["bet_type"] or "").lower() == "matchup"]
    matchup_brier = None
    if matchup_rows:
        matchup_brier = sum((row["model_prob"] - row["actual_outcome"]) ** 2 for row in matchup_rows) / len(matchup_rows)

    by_market: dict[str, list[float]] = {}
    for row in prediction_rows:
        market = (row["bet_type"] or "unknown").lower()
        by_market.setdefault(market, []).append((row["model_prob"] - row["actual_outcome"]) ** 2)
    segment_brier = {
        market: (sum(vals) / len(vals))
        for market, vals in by_market.items()
        if vals
    }

    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    profit_rows = [row for row in prediction_rows if row["profit"] is not None]
    for row in profit_rows:
        cumulative += float(row["profit"] or 0.0)
        peak = max(peak, cumulative)
        drawdown = peak - cumulative
        max_drawdown = max(max_drawdown, drawdown)

    reasons: list[str] = []
    if total_bets < 250:
        reasons.append(f"minimum_bets_not_met ({total_bets}/250)")
    if avg_clv_pct is None or avg_clv_pct <= 1.0:
        reasons.append(f"avg_clv_not_met ({avg_clv_pct if avg_clv_pct is not None else 'n/a'} <= 1.0)")
    if clv_rows and clv_hit_rate <= 55.0:
        reasons.append(f"clv_hit_rate_not_met ({clv_hit_rate:.1f}% <= 55.0%)")
    elif not clv_rows:
        reasons.append("clv_hit_rate_not_met (no_clv_data)")
    if matchup_brier is None or matchup_brier >= 0.22:
        reasons.append(f"matchup_brier_not_met ({'n/a' if matchup_brier is None else round(matchup_brier, 4)} >= 0.22)")
    bad_segments = {k: v for k, v in segment_brier.items() if v > 0.28}
    if bad_segments:
        reasons.append(f"segment_brier_not_met ({', '.join(f'{k}:{v:.3f}' for k, v in bad_segments.items())})")
    if max_drawdown >= 20.0:
        reasons.append(f"drawdown_not_met ({max_drawdown:.2f} >= 20.0)")

    metrics = {
        "scope": scope,
        "total_bets": total_bets,
        "avg_clv_pct": avg_clv_pct,
        "clv_hit_rate_pct": round(clv_hit_rate, 2),
        "matchup_brier": round(matchup_brier, 6) if matchup_brier is not None else None,
        "segment_brier": {k: round(v, 6) for k, v in segment_brier.items()},
        "max_drawdown_units": round(max_drawdown, 4),
    }
    return PromotionGateResult(passed=not reasons, reasons=reasons, metrics=metrics)


def set_research_champion(
    strategy: StrategyConfig,
    *,
    scope: str = "global",
    source: str = "manual",
    proposal_id: int | None = None,
    theory_metadata: dict[str, Any] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    conn = db.get_conn()
    conn.execute("UPDATE research_model_registry SET is_current = 0 WHERE scope = ?", (scope,))
    cursor = conn.execute(
        """
        INSERT INTO research_model_registry (
            scope, strategy_config_json, source, proposal_id,
            theory_metadata_json, notes, is_current
        ) VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (
            scope,
            strategy.to_json(),
            source,
            proposal_id,
            json.dumps(theory_metadata, sort_keys=True) if theory_metadata is not None else None,
            notes,
        ),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return {"id": row_id, "strategy": strategy, "scope": scope}


def get_live_weekly_model(scope: str = "global") -> StrategyConfig:
    row = _current_row("live_model_registry", scope)
    strategy = _strategy_from_json(row["strategy_config_json"]) if row else None
    return strategy or get_active_strategy(scope) or StrategyConfig(name="default_live_weekly_model")


def get_live_weekly_model_record(scope: str = "global") -> dict[str, Any] | None:
    row = _current_row("live_model_registry", scope)
    if not row:
        return None
    row["strategy"] = _strategy_from_json(row.get("strategy_config_json"))
    return row


def set_live_weekly_model(
    strategy: StrategyConfig,
    *,
    scope: str = "global",
    promoted_by: str = "manual",
    notes: str | None = None,
    action: str = "manual_set",
    source_research_registry_id: int | None = None,
    replaced_live_registry_id: int | None = None,
) -> dict[str, Any]:
    current = get_live_weekly_model_record(scope)
    conn = db.get_conn()
    conn.execute("UPDATE live_model_registry SET is_current = 0 WHERE scope = ?", (scope,))
    cursor = conn.execute(
        """
        INSERT INTO live_model_registry (
            scope, strategy_config_json, source_research_registry_id,
            promoted_by, action, notes, replaced_live_registry_id, is_current
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            scope,
            strategy.to_json(),
            source_research_registry_id,
            promoted_by,
            action,
            notes,
            replaced_live_registry_id if replaced_live_registry_id is not None else (current["id"] if current else None),
        ),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return {"id": row_id, "strategy": strategy, "scope": scope}


def promote_research_champion_to_live(
    *,
    scope: str = "global",
    promoted_by: str = "manual",
    notes: str | None = None,
    enforce_gates: bool = True,
    enforce_holdout: bool = False,
    holdout_artifact_path: str | None = None,
) -> dict[str, Any]:
    research = get_research_champion_record(scope)
    if not research or not research.get("strategy"):
        raise ValueError("No research champion available to promote")
    gate_result = evaluate_live_promotion_gates(scope)
    if enforce_gates and not gate_result.passed:
        raise PromotionGateError("Promotion blocked by charter gates", gate_result)
    if enforce_holdout:
        _assert_holdout_passed(holdout_artifact_path)
    return set_live_weekly_model(
        research["strategy"],
        scope=scope,
        promoted_by=promoted_by,
        notes=notes,
        action="promote_research_champion",
        source_research_registry_id=research["id"],
    )


def _assert_holdout_passed(holdout_artifact_path: str | None = None) -> None:
    path = Path(holdout_artifact_path) if holdout_artifact_path else _latest_holdout_artifact()
    if path is None or not path.exists():
        raise HoldoutGateError("Promotion blocked: missing holdout artifact")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HoldoutGateError(f"Promotion blocked: invalid holdout artifact ({exc})") from exc
    if payload.get("holdout_verdict") != "pass":
        raise HoldoutGateError("Promotion blocked: holdout verdict is not pass")


def _latest_holdout_artifact() -> Path | None:
    output_dir = Path(__file__).resolve().parents[1] / "output" / "research"
    matches = sorted(output_dir.glob("holdout_verdict_*.json"))
    if not matches:
        return None
    return matches[-1]


def rollback_live_weekly_model(
    *,
    scope: str = "global",
    promoted_by: str = "manual",
    notes: str | None = None,
) -> dict[str, Any]:
    conn = db.get_conn()
    rows = conn.execute(
        """
        SELECT * FROM live_model_registry
        WHERE scope = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 2
        """,
        (scope,),
    ).fetchall()
    conn.close()
    if len(rows) < 2:
        raise ValueError("No previous live model exists to roll back to")
    current = dict(rows[0])
    previous = dict(rows[1])
    previous_strategy = _strategy_from_json(previous.get("strategy_config_json"))
    if previous_strategy is None:
        raise ValueError("Previous live model record is invalid")
    return set_live_weekly_model(
        previous_strategy,
        scope=scope,
        promoted_by=promoted_by,
        notes=notes,
        action="rollback_live_weekly_model",
        replaced_live_registry_id=current["id"],
    )
