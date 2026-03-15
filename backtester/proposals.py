"""Proposal storage and explicit review lifecycle for research ideas."""

from __future__ import annotations

import json
from typing import Any

from backtester.experiments import create_experiment
from backtester.strategy import StrategyConfig
from src import db


ALLOWED_STATUSES = {"draft", "evaluated", "approved", "rejected", "converted", "error"}


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True)


def _row_to_dict(row) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _require_status(current: str, allowed: set[str], action: str) -> None:
    if current not in allowed:
        allowed_list = ", ".join(sorted(allowed))
        raise ValueError(f"Cannot {action} proposal in state '{current}'. Allowed: {allowed_list}")


def create_proposal(
    *,
    name: str,
    hypothesis: str,
    strategy_config: dict[str, Any],
    baseline_strategy: dict[str, Any] | None = None,
    cycle_key: str,
    source: str = "manual",
    scope: str = "global",
    program_version: str = "v1",
    event_weighting_mode: str = "full_season_weighted",
    candidate_count_in_cycle: int | None = None,
    years: list[int] | None = None,
    filters: dict[str, Any] | None = None,
    theory_metadata: dict[str, Any] | None = None,
    repro_metadata: dict[str, Any] | None = None,
) -> int:
    conn = db.get_conn()
    cursor = conn.execute(
        """
        INSERT INTO research_proposals (
            name, hypothesis, source, scope, status, cycle_key,
            strategy_config_json, baseline_strategy_json, program_version,
            event_weighting_mode, candidate_count_in_cycle, years_json,
            filters_json, theory_metadata_json, summary_metrics_json, segmented_metrics_json,
            guardrail_results_json, repro_metadata_json,
            artifact_markdown_path, artifact_manifest_path, converted_experiment_id
        ) VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, NULL, NULL, NULL)
        """,
        (
            name,
            hypothesis,
            source,
            scope,
            cycle_key,
            _json_dumps(strategy_config),
            _json_dumps(baseline_strategy),
            program_version,
            event_weighting_mode,
            candidate_count_in_cycle,
            _json_dumps(years),
            _json_dumps(filters),
            _json_dumps(theory_metadata),
            _json_dumps(repro_metadata),
        ),
    )
    conn.commit()
    proposal_id = cursor.lastrowid
    conn.close()
    return proposal_id


def list_proposals(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    conn = db.get_conn()
    if status:
        rows = conn.execute(
            """
            SELECT * FROM research_proposals
            WHERE status = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM research_proposals
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    conn.close()
    return [_row_to_dict(row) for row in rows]


def get_proposal(proposal_id: int) -> dict[str, Any]:
    conn = db.get_conn()
    row = conn.execute(
        "SELECT * FROM research_proposals WHERE id = ?",
        (proposal_id,),
    ).fetchone()
    conn.close()
    if row is None:
        raise ValueError(f"Proposal {proposal_id} not found")
    return _row_to_dict(row)


def update_proposal_evaluation(
    proposal_id: int,
    *,
    summary_metrics: dict[str, Any],
    segmented_metrics: dict[str, Any],
    guardrail_results: dict[str, Any],
    artifact_markdown_path: str,
    artifact_manifest_path: str,
) -> None:
    proposal = get_proposal(proposal_id)
    _require_status(proposal["status"], {"draft"}, "evaluate")

    conn = db.get_conn()
    conn.execute(
        """
        UPDATE research_proposals
        SET status = 'evaluated',
            summary_metrics_json = ?,
            segmented_metrics_json = ?,
            guardrail_results_json = ?,
            artifact_markdown_path = ?,
            artifact_manifest_path = ?,
            evaluated_at = datetime('now')
        WHERE id = ?
        """,
        (
            _json_dumps(summary_metrics),
            _json_dumps(segmented_metrics),
            _json_dumps(guardrail_results),
            artifact_markdown_path,
            artifact_manifest_path,
            proposal_id,
        ),
    )
    conn.commit()
    conn.close()


def _write_review(proposal_id: int, decision: str, reviewer: str, notes: str | None = None) -> None:
    conn = db.get_conn()
    conn.execute(
        """
        INSERT INTO proposal_reviews (proposal_id, decision, reviewer, notes)
        VALUES (?, ?, ?, ?)
        """,
        (proposal_id, decision, reviewer, notes),
    )
    conn.commit()
    conn.close()


def approve_proposal(proposal_id: int, *, reviewer: str, notes: str | None = None) -> None:
    proposal = get_proposal(proposal_id)
    _require_status(proposal["status"], {"evaluated"}, "approve")

    conn = db.get_conn()
    conn.execute(
        """
        UPDATE research_proposals
        SET status = 'approved',
            approved_at = datetime('now')
        WHERE id = ?
        """,
        (proposal_id,),
    )
    conn.commit()
    conn.close()
    _write_review(proposal_id, "approved", reviewer, notes)


def reject_proposal(proposal_id: int, *, reviewer: str, notes: str | None = None) -> None:
    proposal = get_proposal(proposal_id)
    _require_status(proposal["status"], {"evaluated"}, "reject")

    conn = db.get_conn()
    conn.execute(
        """
        UPDATE research_proposals
        SET status = 'rejected',
            rejected_at = datetime('now')
        WHERE id = ?
        """,
        (proposal_id,),
    )
    conn.commit()
    conn.close()
    _write_review(proposal_id, "rejected", reviewer, notes)


def convert_proposal_to_experiment(proposal_id: int) -> int:
    proposal = get_proposal(proposal_id)
    _require_status(proposal["status"], {"approved"}, "convert")

    strategy_data = json.loads(proposal["strategy_config_json"])
    strategy = StrategyConfig(**strategy_data)
    if not strategy.name or strategy.name == "default":
        strategy.name = proposal["name"]
    if not strategy.description:
        strategy.description = proposal["hypothesis"]

    experiment_id = create_experiment(
        hypothesis=proposal["hypothesis"],
        strategy=strategy,
        source=proposal["source"],
        scope=proposal["scope"],
    )

    conn = db.get_conn()
    conn.execute(
        """
        UPDATE research_proposals
        SET status = 'converted',
            converted_experiment_id = ?
        WHERE id = ?
        """,
        (experiment_id, proposal_id),
    )
    conn.commit()
    conn.close()
    return experiment_id
