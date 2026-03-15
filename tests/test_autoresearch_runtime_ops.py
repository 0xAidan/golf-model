import os
import sys
import tempfile

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_autoresearch_status_contract_fields(monkeypatch):
    import app as app_module

    monkeypatch.setattr(
        "backtester.optimizer_runtime.get_optimizer_status",
        lambda: {
            "running": True,
            "run_count": 5,
            "last_run_started_at": "2026-03-14T00:00:00Z",
            "last_run_finished_at": "2026-03-14T00:01:00Z",
            "last_error": None,
            "last_result": {"metrics": {"keep_rate": 0.2, "crash_rate": 0.0, "guardrail_fail_rate": 0.1}},
        },
    )

    client = TestClient(app_module.app)
    response = client.get("/api/autoresearch/status")
    payload = response.json()
    assert response.status_code == 200
    assert "status" in payload
    assert "run_count" in payload["status"]


def test_autoresearch_runs_roi_delta_backfilled_from_dossier(monkeypatch):
    import app as app_module

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as tmp:
        tmp.write(
            "# Research Dossier\n"
            "- Weighted ROI: -3.20\n"
            "- Baseline Weighted ROI: -1.10\n"
        )
        dossier_path = tmp.name

    class _Rows:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class _FakeConn:
        def execute(self, *_args, **_kwargs):
            return _Rows(
                [
                    {
                        "id": 1,
                        "name": "candidate",
                        "hypothesis": "test hypothesis",
                        "source": "openai",
                        "scope": "global",
                        "status": "evaluated",
                        "years_json": "[2024, 2025]",
                        "theory_metadata_json": '{"title": "Candidate Title"}',
                        "summary_metrics_json": '{"weighted_roi_pct": -3.2, "weighted_clv_avg": 0.01}',
                        "guardrail_results_json": '{"passed": true, "reasons": [], "verdict": "promising"}',
                        "artifact_markdown_path": dossier_path,
                        "created_at": "2026-03-15T02:00:00Z",
                        "evaluated_at": "2026-03-15T02:01:00Z",
                    }
                ]
            )

        def close(self):
            return None

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(app_module, "get_conn", lambda: _FakeConn())

    client = TestClient(app_module.app)
    response = client.get("/api/autoresearch/runs?scope=global&limit=5")
    assert response.status_code == 200
    payload = response.json()
    assert payload["runs"]
    run = payload["runs"][0]
    assert run["roi_delta"] == -2.1

    os.unlink(dossier_path)

