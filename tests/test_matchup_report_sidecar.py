"""Exercise the isolated HTTP service without app imports or model execution."""

from datetime import datetime, timedelta, timezone
import hashlib
from http.client import HTTPConnection
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from threading import Thread

import pytest

from scripts import serve_matchup_reports as sidecar


def _snapshot(*, age=30, verified=True):
    return {
        "snapshot_id": "snapshot-test",
        "generated_at": (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat(),
        "upcoming_tournament": {
            "source_event_id": "528", "event_name": "Butterfield Bermuda Championship",
            "eligibility": {"verified": verified, "code": "field_verified" if verified else "field_unverified"},
            "matchup_bets": [{"player_key": "test_player", "opponent_key": "other", "ev": 0.07}],
        },
    }


@pytest.fixture
def service(tmp_path):
    database = tmp_path / "source.db"
    with sqlite3.connect(database) as conn:
        conn.executescript("""
            CREATE TABLE tournaments (id INTEGER PRIMARY KEY, year INTEGER, event_id TEXT, name TEXT);
            CREATE TABLE picks (id INTEGER PRIMARY KEY, tournament_id INTEGER, source TEXT,
                model_variant TEXT, bet_type TEXT, market_type TEXT, player_key TEXT,
                opponent_key TEXT, market_book TEXT, market_odds TEXT, model_prob REAL);
            CREATE TABLE pick_outcomes (id INTEGER PRIMARY KEY, pick_id INTEGER, hit INTEGER,
                stake REAL, profit REAL, grading_authority TEXT);
            INSERT INTO tournaments VALUES (1, 2026, '528', 'Test event');
            INSERT INTO picks VALUES (1, 1, 'cockpit', 'baseline', 'matchup',
                'tournament_matchups', 'test_player', 'other', 'book', '+110', 0.55);
            INSERT INTO pick_outcomes VALUES (1, 1, 1, 1, 1.1, 'matchup_outcome');
        """)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(_snapshot()))
    server = sidecar.ReportServer(sidecar.Settings(database, snapshot), 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path, method="GET"):
        client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        client.request(method, path)
        response = client.getresponse()
        body = response.read()
        result = (response.status, dict(response.getheaders()), json.loads(body) if body else None)
        client.close()
        return result

    yield request, snapshot, database
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_reports_are_read_only_and_snapshot_projection_preserves_values(service):
    request, snapshot, database = service
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (snapshot, database)}
    status, headers, board = request("/api/desk/board?track=champion&mode=upcoming&event_id=528")
    assert status == 200
    assert headers["Cache-Control"] == "no-store"
    assert board["state"] == "fresh"
    assert board["source"]["stale_after_seconds"] == 3720
    assert board["picks"]["matchups"] == _snapshot()["upcoming_tournament"]["matchup_bets"]
    status, _, evidence = request("/api/market-evidence?lane=dashboard&season=2026")
    assert status == 200
    assert evidence["state"] == "available"
    assert evidence["coverage"]["raw_pick_records"] == 1
    assert evidence["provenance"]["history_changes"] is False
    assert evidence["provenance"]["model_changes"] is False
    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before}


def test_stale_missing_unverified_and_wrong_event_states(service):
    request, snapshot, _ = service
    snapshot.write_text(json.dumps(_snapshot(age=3800)))
    assert request("/api/desk/board")[2]["state"] == "stale"
    snapshot.write_text(json.dumps(_snapshot(verified=False)))
    board = request("/api/desk/board")[2]
    assert board["state"] == "unavailable"
    assert board["picks"]["matchups"] == []
    snapshot.write_text(json.dumps(_snapshot()))
    board = request("/api/desk/board?event_id=wrong")[2]
    assert board["reason"]["code"] == "event_identity_mismatch"
    assert board["picks"]["matchups"] == []
    assert request("/api/desk/board?track=challenger")[2]["reason"]["code"] == "challenger_lane_unavailable"
    snapshot.write_text("not JSON; secret-token")
    assert request("/api/desk/board")[2]["state"] == "unavailable"
    snapshot.unlink()
    assert request("/api/desk/board")[2]["state"] == "unavailable"
    assert not snapshot.exists()


@pytest.mark.parametrize("query", [
    "/api/desk/board?mode=past", "/api/desk/board?mode=invalid",
    "/api/desk/board?track=all", "/api/desk/board?track=champion&track=challenger",
    "/api/desk/board?event_id=", "/api/market-evidence?lane=invalid",
    "/api/market-evidence?season=1900", "/api/market-evidence?season=oops",
    "/api/market-evidence?season=" + "9" * 5000, "/api/market-evidence?token=secret-token",
])
def test_invalid_requests_are_rejected_without_echoing_query(service, query):
    status, _, body = service[0](query)
    assert status == 400
    assert "secret-token" not in json.dumps(body)


def test_only_exact_routes_get_and_head_are_supported(service):
    request, _, _ = service
    status, headers, body = request("/health", "HEAD")
    assert status == 200 and body is None
    assert int(headers["Content-Length"]) > 0
    assert request("/health")[2] == {"ok": True, "service": "golf-evidence", "read_only": True}
    assert request("/api/operator/board")[0] == 404
    assert request("/api/desk/board/extra")[0] == 404
    assert request("/api/market-evidence", "POST")[0] == 405


def test_missing_db_is_not_created_and_unexpected_errors_do_not_leak(service, monkeypatch):
    request, _, database = service
    database.unlink()
    status, _, body = request("/api/market-evidence")
    assert status == 200 and body["state"] == "unavailable"
    assert not database.exists()

    def fail(*args, **kwargs):
        raise RuntimeError("https://provider.example?key=secret-token /private/data.db")

    monkeypatch.setattr(sidecar, "build_market_evidence", fail)
    status, _, body = request("/api/market-evidence")
    assert status == 503
    assert "secret-token" not in json.dumps(body)
    assert "/private" not in json.dumps(body)


def test_isolated_import_loads_no_application_or_models():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([
        sys.executable, "-c",
        "import sys; from scripts import serve_matchup_reports; "
        "assert 'src.db' not in sys.modules; assert 'app' not in sys.modules; "
        "assert not any(n.startswith(('src.models', 'backtester')) for n in sys.modules)",
    ], cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_minimal_release_imports_with_no_site_packages(tmp_path):
    root = Path(__file__).resolve().parents[1]
    shutil.copyfile(root / "scripts/serve_matchup_reports.py", tmp_path / "serve_matchup_reports.py")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/__init__.py").write_text("")
    for name in ("market_evidence.py", "operator_read_model.py", "operator_contract.py"):
        shutil.copyfile(root / "src" / name, tmp_path / "src" / name)
    result = subprocess.run([
        sys.executable, "-I", "-S", "-B", str(tmp_path / "serve_matchup_reports.py"), "--help",
    ], cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "--stale-after-seconds" in result.stdout
    assert not list(tmp_path.rglob("*.pyc"))
