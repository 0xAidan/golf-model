import os
import sys

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

