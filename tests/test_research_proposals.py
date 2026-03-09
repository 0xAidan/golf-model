"""Tests for research proposal schema and lifecycle foundations."""

import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.db as db

_original_path = db.DB_PATH


def setup_module():
    """Create a fresh temp DB for each test module run."""
    tmp = tempfile.mktemp(suffix=".db")
    db.DB_PATH = tmp
    db._DB_INITIALIZED = False
    db.ensure_initialized()


def teardown_module():
    """Restore original DB path."""
    if os.path.exists(db.DB_PATH):
        os.unlink(db.DB_PATH)
    db.DB_PATH = _original_path
    db._DB_INITIALIZED = False


def _base_proposal_row(cycle_key: str = "cycle-1") -> dict:
    return {
        "name": "proposal_a",
        "hypothesis": "Test a safer EV threshold",
        "source": "manual",
        "scope": "global",
        "status": "draft",
        "cycle_key": cycle_key,
        "strategy_config_json": json.dumps({"min_ev": 0.07}, sort_keys=True),
        "baseline_strategy_json": json.dumps({"min_ev": 0.05}, sort_keys=True),
        "program_version": "v1",
        "event_weighting_mode": "full_season_weighted",
        "candidate_count_in_cycle": 3,
        "years_json": json.dumps([2024, 2025]),
        "filters_json": json.dumps({"tour": "pga"}, sort_keys=True),
        "theory_metadata_json": json.dumps({"source_type": "openai", "title": "theory"}, sort_keys=True),
        "summary_metrics_json": None,
        "segmented_metrics_json": None,
        "guardrail_results_json": None,
        "repro_metadata_json": json.dumps({"seed": 42}, sort_keys=True),
        "artifact_markdown_path": None,
        "artifact_manifest_path": None,
        "converted_experiment_id": None,
    }


def test_research_tables_exist():
    """Proposal tables should be created during DB initialization."""
    conn = db.get_conn()
    names = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    conn.close()

    assert "research_proposals" in names
    assert "proposal_reviews" in names


def test_can_insert_proposal_and_review():
    """Research proposals and their reviews should be persistable."""
    proposal = _base_proposal_row()
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
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        tuple(proposal.values()),
    )
    proposal_id = cursor.lastrowid

    conn.execute(
        """
        INSERT INTO proposal_reviews (proposal_id, decision, reviewer, notes)
        VALUES (?, ?, ?, ?)
        """,
        (proposal_id, "approved", "test", "looks good"),
    )
    conn.commit()

    stored = conn.execute(
        "SELECT status, cycle_key FROM research_proposals WHERE id = ?",
        (proposal_id,),
    ).fetchone()
    review = conn.execute(
        "SELECT decision, reviewer FROM proposal_reviews WHERE proposal_id = ?",
        (proposal_id,),
    ).fetchone()
    conn.close()

    assert stored["status"] == "draft"
    assert stored["cycle_key"] == "cycle-1"
    assert review["decision"] == "approved"
    assert review["reviewer"] == "test"


def test_duplicate_proposal_same_cycle_is_rejected():
    """Same strategy config in the same cycle should not be insertable twice."""
    proposal = _base_proposal_row(cycle_key="cycle-dedup")
    conn = db.get_conn()
    insert_sql = """
        INSERT INTO research_proposals (
            name, hypothesis, source, scope, status, cycle_key,
            strategy_config_json, baseline_strategy_json, program_version,
            event_weighting_mode, candidate_count_in_cycle, years_json,
            filters_json, theory_metadata_json, summary_metrics_json, segmented_metrics_json,
            guardrail_results_json, repro_metadata_json,
            artifact_markdown_path, artifact_manifest_path, converted_experiment_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """

    conn.execute(insert_sql, tuple(proposal.values()))
    with_raised = False
    try:
        conn.execute(insert_sql, tuple(proposal.values()))
        conn.commit()
    except sqlite3.IntegrityError:
        with_raised = True
    finally:
        conn.close()

    assert with_raised, "Duplicate proposals in the same cycle should hit a unique constraint"


def test_invalid_proposal_status_is_rejected():
    """Proposal status should be constrained to the known lifecycle states."""
    proposal = _base_proposal_row(cycle_key="cycle-invalid-status")
    proposal["status"] = "launched_into_space"
    conn = db.get_conn()

    raised = False
    try:
        conn.execute(
            """
            INSERT INTO research_proposals (
                name, hypothesis, source, scope, status, cycle_key,
                strategy_config_json, baseline_strategy_json, program_version,
                event_weighting_mode, candidate_count_in_cycle, years_json,
                filters_json, theory_metadata_json, summary_metrics_json, segmented_metrics_json,
                guardrail_results_json, repro_metadata_json,
                artifact_markdown_path, artifact_manifest_path, converted_experiment_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            tuple(proposal.values()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raised = True
    finally:
        conn.close()

    assert raised, "Unexpected proposal statuses should be blocked by a CHECK constraint"


def test_converted_experiment_can_link_to_experiment():
    """Converted proposals should be able to point at an experiments row."""
    conn = db.get_conn()
    exp_cursor = conn.execute(
        """
        INSERT INTO experiments (
            hypothesis, source, strategy_config_json, scope, status
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("baseline experiment", "manual", json.dumps({"min_ev": 0.05}), "global", "pending"),
    )
    experiment_id = exp_cursor.lastrowid

    proposal = _base_proposal_row(cycle_key="cycle-convert-link")
    proposal["status"] = "converted"
    proposal["converted_experiment_id"] = experiment_id

    prop_cursor = conn.execute(
        """
        INSERT INTO research_proposals (
            name, hypothesis, source, scope, status, cycle_key,
            strategy_config_json, baseline_strategy_json, program_version,
            event_weighting_mode, candidate_count_in_cycle, years_json,
            filters_json, theory_metadata_json, summary_metrics_json, segmented_metrics_json,
            guardrail_results_json, repro_metadata_json,
            artifact_markdown_path, artifact_manifest_path, converted_experiment_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        tuple(proposal.values()),
    )
    proposal_id = prop_cursor.lastrowid
    conn.commit()

    linked = conn.execute(
        """
        SELECT converted_experiment_id
        FROM research_proposals
        WHERE id = ?
        """,
        (proposal_id,),
    ).fetchone()
    conn.close()

    assert linked["converted_experiment_id"] == experiment_id


def test_create_and_list_proposal():
    """Proposal helpers should persist and list proposal rows."""
    from backtester.proposals import create_proposal, list_proposals

    proposal_id = create_proposal(
        name="proposal_listed",
        hypothesis="Lower threshold to increase bet volume",
        strategy_config={"min_ev": 0.04},
        baseline_strategy={"min_ev": 0.05},
        cycle_key="cycle-crud-list",
        source="manual",
        scope="global",
        program_version="v1",
        event_weighting_mode="full_season_weighted",
        candidate_count_in_cycle=2,
        years=[2024, 2025],
        filters={"tour": "pga"},
        theory_metadata={"source_type": "openai", "title": "listed"},
        repro_metadata={"seed": 42},
    )

    rows = list_proposals()
    created = next(row for row in rows if row["id"] == proposal_id)

    assert created["name"] == "proposal_listed"
    assert created["status"] == "draft"
    assert created["cycle_key"] == "cycle-crud-list"
    assert "listed" in created["theory_metadata_json"]


def test_update_proposal_evaluation_moves_to_evaluated():
    """Evaluation updates should move a draft proposal into evaluated state."""
    from backtester.proposals import create_proposal, get_proposal, update_proposal_evaluation

    proposal_id = create_proposal(
        name="proposal_eval",
        hypothesis="Increase form weight",
        strategy_config={"w_sub_form": 0.5},
        baseline_strategy={"w_sub_form": 0.4},
        cycle_key="cycle-evaluated",
        theory_metadata={"source_type": "openai", "title": "eval"},
        repro_metadata={"seed": 42},
    )

    update_proposal_evaluation(
        proposal_id,
        summary_metrics={"weighted_roi": 4.2},
        segmented_metrics={"majors": {"weighted_roi": 5.1}},
        guardrail_results={"verdict": "promising"},
        artifact_markdown_path="output/research/proposal_eval.md",
        artifact_manifest_path="output/research/proposal_eval.json",
    )

    stored = get_proposal(proposal_id)
    assert stored["status"] == "evaluated"
    assert stored["artifact_markdown_path"] == "output/research/proposal_eval.md"


def test_cannot_approve_proposal_before_evaluation():
    """Only evaluated proposals should be approvable."""
    from backtester.proposals import approve_proposal, create_proposal

    proposal_id = create_proposal(
        name="proposal_not_ready",
        hypothesis="Do not approve a draft",
        strategy_config={"min_ev": 0.06},
        baseline_strategy={"min_ev": 0.05},
        cycle_key="cycle-approve-guard",
        repro_metadata={"seed": 42},
    )

    raised = False
    try:
        approve_proposal(proposal_id, reviewer="tester", notes="too early")
    except ValueError:
        raised = True

    assert raised, "Draft proposals should not be approvable"


def test_approve_and_reject_write_review_rows():
    """Approval and rejection should update state and create audit reviews."""
    from backtester.proposals import (
        approve_proposal,
        create_proposal,
        get_proposal,
        reject_proposal,
        update_proposal_evaluation,
    )

    approved_id = create_proposal(
        name="proposal_to_approve",
        hypothesis="Ready for approval",
        strategy_config={"min_ev": 0.07},
        baseline_strategy={"min_ev": 0.05},
        cycle_key="cycle-approve",
        repro_metadata={"seed": 42},
    )
    update_proposal_evaluation(
        approved_id,
        summary_metrics={"weighted_roi": 3.0},
        segmented_metrics={},
        guardrail_results={"verdict": "promising"},
        artifact_markdown_path="approved.md",
        artifact_manifest_path="approved.json",
    )
    approve_proposal(approved_id, reviewer="alice", notes="ship to experiment stage")

    rejected_id = create_proposal(
        name="proposal_to_reject",
        hypothesis="Ready for rejection",
        strategy_config={"min_ev": 0.09},
        baseline_strategy={"min_ev": 0.05},
        cycle_key="cycle-reject",
        repro_metadata={"seed": 42},
    )
    update_proposal_evaluation(
        rejected_id,
        summary_metrics={"weighted_roi": -1.0},
        segmented_metrics={},
        guardrail_results={"verdict": "blocked_by_guardrails"},
        artifact_markdown_path="rejected.md",
        artifact_manifest_path="rejected.json",
    )
    reject_proposal(rejected_id, reviewer="bob", notes="bad drawdown")

    approved = get_proposal(approved_id)
    rejected = get_proposal(rejected_id)
    conn = db.get_conn()
    review_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM proposal_reviews WHERE proposal_id IN (?, ?)",
        (approved_id, rejected_id),
    ).fetchone()["cnt"]
    conn.close()

    assert approved["status"] == "approved"
    assert rejected["status"] == "rejected"
    assert review_count == 2


def test_convert_proposal_to_experiment():
    """Approved proposals should convert into runnable experiments exactly once."""
    from backtester.proposals import (
        approve_proposal,
        convert_proposal_to_experiment,
        create_proposal,
        get_proposal,
        update_proposal_evaluation,
    )

    proposal_id = create_proposal(
        name="proposal_convert",
        hypothesis="Convert to experiment",
        strategy_config={"min_ev": 0.08},
        baseline_strategy={"min_ev": 0.05},
        cycle_key="cycle-convert",
        repro_metadata={"seed": 42},
    )
    update_proposal_evaluation(
        proposal_id,
        summary_metrics={"weighted_roi": 2.4},
        segmented_metrics={},
        guardrail_results={"verdict": "promising"},
        artifact_markdown_path="convert.md",
        artifact_manifest_path="convert.json",
    )
    approve_proposal(proposal_id, reviewer="alice", notes="approved for experiment creation")

    experiment_id = convert_proposal_to_experiment(proposal_id)
    stored = get_proposal(proposal_id)

    assert experiment_id > 0
    assert stored["status"] == "converted"
    assert stored["converted_experiment_id"] == experiment_id
