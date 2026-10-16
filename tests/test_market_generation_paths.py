"""Exercise live service, worker wrappers and both legacy generation entry points."""

import json

from fastapi.testclient import TestClient
import pytest

from src.market_generation_policy import get_market_generation_policy, update_market_generation_policy
from src.services.golf_model_service import GolfModelService


@pytest.fixture(autouse=True)
def isolated_policy(monkeypatch, tmp_path):
    monkeypatch.setenv("GOLF_MARKET_GENERATION_POLICY_DIR", str(tmp_path / "policy"))
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.delenv("MARKET_GENERATION_API_KEY", raising=False)


def set_markets(markets):
    return update_market_generation_policy(enabled_markets=markets, expected_revision=get_market_generation_policy()["revision"])


@pytest.fixture
def composite():
    return [
        {"rank": index + 1, "player_key": key, "player_display": name, "composite": 70 - index * 5,
         "form": 68, "course_fit": 66, "momentum": 55}
        for index, (key, name) in enumerate([("player_a", "Player A"), ("player_b", "Player B")])
    ]


@pytest.fixture
def run_service(monkeypatch, tmp_db, tmp_path, composite):
    monkeypatch.setattr(GolfModelService, "_sync_tournament_data", lambda self, tid, event_id=None: {"decompositions_raw": None})
    monkeypatch.setattr(GolfModelService, "_resolve_field_keys", lambda self, tid, synced: (["player_a", "player_b"], "datagolf_field_updates"))
    monkeypatch.setattr(GolfModelService, "_sync_skill_data", lambda *args: None)
    monkeypatch.setattr(GolfModelService, "_validate_field_data", lambda *args, **kwargs: {
        "has_cross_tour_field_risk": False, "strict_field_verified": True, "failed_invariants": [], "summary": "Verified field"})
    monkeypatch.setattr(GolfModelService, "_compute_rolling_stats", lambda *args: {})
    monkeypatch.setattr(GolfModelService, "_load_course_profile", lambda *args: {})
    monkeypatch.setattr(GolfModelService, "_get_weights", lambda *args: {})
    monkeypatch.setattr(GolfModelService, "_run_composite", lambda *args: composite)
    monkeypatch.setattr(GolfModelService, "_generate_card", lambda *args, **kwargs: str(tmp_path / "card.md"))
    monkeypatch.setattr("src.portfolio.enforce_diversification", lambda bets, **kwargs: bets)
    monkeypatch.setattr("src.telegram_alerts.maybe_send_matchup_ev_alerts", lambda **kwargs: None)

    def run(**kwargs):
        return GolfModelService().run_analysis(
            tournament_name="Preserved Open", course_name="Test Course", event_id="1",
            enable_ai=False, enable_backfill=False, include_methodology=False,
            output_dir=str(tmp_path), strategy_source="config", **kwargs,
        )

    return run


@pytest.mark.parametrize("mode", ["full", "placements-only", "matchups-only", "round-matchups"])
def test_disabled_all_still_ranks_but_never_generates_or_logs_market_rows(run_service, tmp_db, monkeypatch, composite, mode):
    set_markets([])
    for name in ("_fetch_odds", "_compute_value_bets", "_fetch_matchup_value_bets", "_fetch_3ball_value_bets", "_log_predictions", "_log_matchup_predictions"):
        monkeypatch.setattr(GolfModelService, name, lambda *args, **kwargs: pytest.fail("Disabled market generation was invoked"))
    before = tmp_db.get_conn()
    old_counts = {name: before.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in ("picks", "prediction_log", "pick_outcomes")}
    before.close()
    result = run_service(mode=mode)
    assert result["status"] == "complete"
    assert result["composite_results"] == composite
    assert result["value_bets"] == {}
    assert result["matchup_bets"] == result["matchup_bets_all_books"] == []
    conn = tmp_db.get_conn()
    assert {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in old_counts} == old_counts
    run = json.loads(conn.execute("SELECT result_json FROM runs ORDER BY id DESC LIMIT 1").fetchone()[0])
    conn.close()
    assert run["market_generation_policy"]["enabled_markets"] == []


def test_in_progress_run_retains_its_captured_policy(run_service, monkeypatch, composite):
    captured = set_markets([])

    def compute(*args):
        set_markets(["72h"])
        return composite

    monkeypatch.setattr(GolfModelService, "_run_composite", compute)
    monkeypatch.setattr(GolfModelService, "_fetch_matchup_value_bets", lambda *args, **kwargs: pytest.fail("A running pass must keep its captured policy"))
    result = run_service()
    assert result["market_generation_policy"]["revision"] == captured["revision"]
    assert get_market_generation_policy()["enabled_markets"] == ["72h"]


def test_unavailable_policy_pauses_selections_and_keeps_rankings(run_service, monkeypatch, tmp_path, composite):
    root = tmp_path / "policy"
    root.mkdir()
    (root / "current.json").write_text("broken")
    monkeypatch.setattr(GolfModelService, "_fetch_odds", lambda *args: pytest.fail("Unverified policy must fail closed"))
    result = run_service()
    assert result["status"] == "complete"
    assert result["composite_results"] == composite
    assert result["market_generation_policy"]["state"] == "unavailable"
    assert "policy could not be verified" in result["warnings"][0]


def test_placements_require_both_policy_and_strategy_permission(tmp_db, monkeypatch, composite):
    set_markets(["top10", "top20"])
    service = GolfModelService(strategy_config={"allowed_markets": {"outright", "top10"}})
    monkeypatch.setattr("src.odds.get_best_odds", lambda odds: odds)
    called = []
    monkeypatch.setattr("src.value.find_value_bets", lambda *args, **kwargs: called.append(kwargs["bet_type"]) or [])
    result = service._compute_value_bets(composite, {"outrights": [{}], "top_10": [{}], "top_20": [{}], "top15": [{}], "make_cut": [{}]}, 1)
    assert result == {"top10": []}
    assert called == ["top10"]


@pytest.mark.parametrize("allowed,mode,expected", [
    (["18h"], "round-matchups", ["round_matchups"]),
    (["72h"], "round-matchups", ["tournament_matchups"]),
    (["18h"], "full", []),
    (["72h", "18h"], "full", ["tournament_matchups"]),
    ([], "round-matchups", []),
])
def test_matchup_mode_and_fallback_cannot_bypass_policy(tmp_db, monkeypatch, composite, allowed, mode, expected):
    set_markets(allowed)
    fetched = []
    monkeypatch.setattr("src.datagolf.fetch_matchup_odds_with_diagnostics", lambda market, tour: (fetched.append(market) or [], {"reason_code": "no_odds"}))
    service = GolfModelService()
    card, all_books, diag = service._fetch_matchup_value_bets(composite, 1, mode)
    assert fetched == expected
    assert card == all_books == []
    if not expected:
        assert diag["state"] == "policy_disabled"


def test_disabled_group_does_not_fetch_or_compute(tmp_db, monkeypatch, composite):
    set_markets(["72h"])
    monkeypatch.setattr("src.datagolf.fetch_matchup_odds", lambda **kwargs: pytest.fail("Group generation disabled"))
    assert GolfModelService()._fetch_3ball_value_bets(composite, 1) == []


@pytest.mark.parametrize("lane", ["dashboard", "lab"])
def test_worker_snapshot_wrappers_keep_captured_policy_metadata(monkeypatch, lane):
    from backtester.strategy import StrategyConfig
    from src.services import live_snapshot_service

    captured = set_markets([])

    class FakeService:
        def __init__(self, **kwargs):
            pass

        def run_analysis(self, **kwargs):
            return {"status": "complete", "market_generation_policy": captured}

    monkeypatch.setattr("src.services.golf_model_service.GolfModelService", FakeService)
    monkeypatch.setattr("src.strategy_resolution.resolve_runtime_strategy", lambda scope: (StrategyConfig(name="baseline"), {}))
    fn = live_snapshot_service.run_snapshot_analysis if lane == "dashboard" else live_snapshot_service.run_lab_snapshot_analysis
    result = fn()
    assert result["strategy_meta"]["market_generation_policy"] == captured


@pytest.mark.parametrize("allowed", [[], ["top10"]])
def test_legacy_csv_upload_only_logs_enabled_markets(tmp_db, monkeypatch, composite, allowed):
    import app

    set_markets(allowed)
    monkeypatch.setattr(app, "ingest_folder", lambda *args: {})
    monkeypatch.setattr(app, "compute_composite", lambda *args: composite)
    submitted = []
    original_store = app.store_picks
    monkeypatch.setattr(app, "store_picks", lambda rows: submitted.extend(rows) or original_store(rows))
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    monkeypatch.setattr(app, "fetch_odds_api", lambda *args: pytest.fail("No network requests expected"))
    result = TestClient(app.app).post("/api/analyze", data={"tournament": "CSV Open"}, files=[("files", ("sample.csv", b"player,value\nPlayer A,1\n", "text/csv"))])
    assert result.status_code == 200
    conn = tmp_db.get_conn()
    rows = conn.execute("SELECT bet_type FROM picks").fetchall()
    conn.close()
    assert [row["bet_type"] for row in submitted] == (["top10", "top10"] if allowed else [])
    # Existing inventory safeguards still reject unquoted legacy-upload rows.
    assert rows == []
    assert app._last_analysis["composite"] == composite


@pytest.mark.parametrize("allowed", [[], ["top10"]])
def test_legacy_analyze_cli_honors_policy_for_manual_and_api_odds(tmp_db, monkeypatch, tmp_path, composite, allowed):
    import analyze

    set_markets(allowed)
    folder = tmp_path / "csvs"
    folder.mkdir()
    (folder / "sample.csv").write_text("player,value\nPlayer A,1\n")
    monkeypatch.setattr("sys.argv", ["analyze.py", "--tournament", "CLI Open", "--folder", str(folder), "--no-sync", "--odds", "fake.json"])
    monkeypatch.setattr(analyze, "ingest_folder", lambda *args: {})
    monkeypatch.setattr(analyze, "compute_composite", lambda *args, **kwargs: composite)
    monkeypatch.setattr(analyze, "get_all_players", lambda *args: ["player_a", "player_b"])
    fetched = []
    monkeypatch.setattr(analyze, "fetch_odds_api", lambda market: fetched.append(market) or [{"market": market}])
    monkeypatch.setattr(analyze, "load_manual_odds", lambda *args: [{"market": "outrights"}, {"market": "top_10"}, {"market": "make_cut"}])
    monkeypatch.setattr(analyze, "get_best_odds", lambda odds: odds)
    computed = []
    monkeypatch.setattr(analyze, "find_value_bets", lambda *args, **kwargs: computed.append(kwargs["bet_type"]) or [])
    cards = []
    monkeypatch.setattr(analyze, "generate_card", lambda *args, **kwargs: cards.append(args) or "no-write.md")
    analyze.main()
    assert fetched == (["top_10"] if allowed else [])
    assert computed == (["top10"] if allowed else [])
    assert cards[0][2] == composite


@pytest.mark.parametrize("allowed,mode,expected_placements,expected_matchups", [
    ([], "full", [], []),
    (["top10", "72h"], "full", ["top10"], ["tournament_matchups"]),
    (["18h"], "full", [], []),
    (["18h"], "round-matchups", [], ["round_matchups"]),
    (["group"], "placements-only", [], ["3_balls"]),
    (None, "full", ["outright", "top5", "top10", "top20"], ["tournament_matchups", "3_balls"]),
])
def test_standalone_prediction_cli_captures_policy_before_any_generation(
    tmp_db, monkeypatch, composite, allowed, mode, expected_placements, expected_matchups,
):
    import run_predictions as cli
    from backtester.strategy import StrategyConfig

    if allowed is not None:
        set_markets(allowed)
    monkeypatch.setenv("DATAGOLF_API_KEY", "test-never-sent")
    monkeypatch.setattr("sys.argv", ["run_predictions.py", "--mode", mode])
    monkeypatch.setattr(cli, "SHADOW_MODE", False)
    monkeypatch.setattr(cli, "resolve_runtime_strategy", lambda scope: (StrategyConfig(name="preserved"), {"strategy_source": "default", "strategy_name": "preserved"}))
    monkeypatch.setattr(cli, "_acquire_deploy_lock", lambda: True)
    monkeypatch.setattr(cli, "_release_deploy_lock", lambda: None)
    monkeypatch.setattr(cli, "_check_and_run_post_review", lambda **kwargs: None)
    monkeypatch.setattr(cli, "_run_data_integrity_gates", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli.db, "get_rounds_backfill_status", lambda: [
        {"tour": "pga", "year": year, "round_count": 1, "player_count": 1} for year in range(2020, 2026)
    ])
    monkeypatch.setattr(cli.db, "get_all_players", lambda *args: [r["player_key"] for r in composite])
    monkeypatch.setattr(cli, "compute_rolling_metrics", lambda *args, **kwargs: {})
    monkeypatch.setattr(cli, "load_course_profile", lambda *args: None)
    monkeypatch.setattr(cli, "compute_composite", lambda *args, **kwargs: composite)
    monkeypatch.setattr(cli, "is_ai_available", lambda: False)
    monkeypatch.setattr(cli, "get_best_odds", lambda odds: odds)
    monkeypatch.setattr("src.feature_flags.is_enabled", lambda flag: flag == "3ball")
    monkeypatch.setattr(cli, "enforce_diversification", lambda bets, **kwargs: bets)
    monkeypatch.setattr(cli, "_store_displayed_picks_for_grading", lambda **kwargs: 0)
    placements = []
    matchups = []
    outright_fetches = []

    def safe_call(description, fn, *args, **kwargs):
        if fn is cli.get_current_event_info:
            return {"event_name": "CLI Future Open", "event_id": "1", "course": "Test Course", "course_key": "1", "start_date": "2099-01-01"}
        if fn is cli.fetch_all_outright_odds:
            outright_fetches.append(True)
            return {key: [{"bookmaker": "test"}] for key in ("outrights", "top_5", "top_10", "top_20", "frl")}
        if fn is cli.fetch_matchup_odds:
            matchups.append(kwargs["market"])
            return []
        return None

    monkeypatch.setattr(cli, "safe_api_call", safe_call)
    monkeypatch.setattr(cli, "find_value_bets", lambda *args, **kwargs: placements.append(kwargs["bet_type"]) or [])
    cards = []
    provenance = []
    monkeypatch.setattr(cli, "generate_card", lambda *args, **kwargs: cards.append((args, kwargs)) or "no-write.md")
    monkeypatch.setattr(cli, "generate_methodology", lambda *args, **kwargs: "no-write-methodology.md")
    monkeypatch.setattr(cli, "write_run_provenance", lambda **kwargs: provenance.append(kwargs) or "no-write.json")
    cli.main()
    assert placements == expected_placements
    assert matchups == expected_matchups
    assert cards[0][0][2] == composite
    assert provenance[0]["runtime_settings"]["market_generation_policy"]["enabled_markets"] == get_market_generation_policy()["enabled_markets"]
    if allowed == []:
        assert not outright_fetches
