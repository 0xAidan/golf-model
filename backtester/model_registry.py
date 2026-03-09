"""Two-tier registry for research champion and live weekly model."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from backtester.experiments import get_active_strategy
from backtester.strategy import StrategyConfig
from src import db


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
) -> dict[str, Any]:
    research = get_research_champion_record(scope)
    if not research or not research.get("strategy"):
        raise ValueError("No research champion available to promote")
    return set_live_weekly_model(
        research["strategy"],
        scope=scope,
        promoted_by=promoted_by,
        notes=notes,
        action="promote_research_champion",
        source_research_registry_id=research["id"],
    )


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
