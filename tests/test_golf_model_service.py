from src.services.golf_model_service import GolfModelService
from src.methodology import _data_sources


def test_backfill_rounds_includes_alt_for_major_events(monkeypatch):
    service = GolfModelService(tour="pga")
    fetched = []

    monkeypatch.setattr("src.services.golf_model_service.db.get_rounds_backfill_status", lambda: [])
    monkeypatch.setattr(
        "src.datagolf.fetch_historical_rounds",
        lambda tour, event_id, year: fetched.append((tour, year)) or [],
    )
    monkeypatch.setattr("src.datagolf._parse_rounds_response", lambda raw, tour, year: [])
    monkeypatch.setattr("src.services.golf_model_service.db.store_rounds", lambda rows: None)
    monkeypatch.setattr("src.services.golf_model_service.time.sleep", lambda seconds: None)

    service._backfill_rounds(years=[2026], tournament_name="Masters Tournament")

    assert fetched == [("pga", 2026), ("alt", 2026)]


def test_backfill_rounds_keeps_regular_events_on_pga_only(monkeypatch):
    service = GolfModelService(tour="pga")
    fetched = []

    monkeypatch.setattr("src.services.golf_model_service.db.get_rounds_backfill_status", lambda: [])
    monkeypatch.setattr(
        "src.datagolf.fetch_historical_rounds",
        lambda tour, event_id, year: fetched.append((tour, year)) or [],
    )
    monkeypatch.setattr("src.datagolf._parse_rounds_response", lambda raw, tour, year: [])
    monkeypatch.setattr("src.services.golf_model_service.db.store_rounds", lambda rows: None)
    monkeypatch.setattr("src.services.golf_model_service.time.sleep", lambda seconds: None)

    service._backfill_rounds(years=[2026], tournament_name="Valero Texas Open")

    assert fetched == [("pga", 2026)]


def test_validate_field_data_flags_players_with_thin_rounds_and_missing_skill(monkeypatch):
    service = GolfModelService(tour="pga")

    monkeypatch.setattr(
        "src.services.golf_model_service.db.get_player_recent_rounds_by_key",
        lambda player_key, limit=24: []
        if player_key == "jon_rahm"
        else [{"round_num": idx + 1} for idx in range(12)],
    )
    monkeypatch.setattr(
        "src.services.golf_model_service.db.get_player_metrics",
        lambda tournament_id, player_key: []
        if player_key == "jon_rahm"
        else [{"metric_category": "dg_skill"}, {"metric_category": "dg_ranking"}],
    )

    validation = service._validate_field_data(
        tournament_id=7,
        tournament_name="Masters Tournament",
        field_keys=["jon_rahm", "ludvig_aberg"],
        field_source="datagolf_field_updates",
        expected_event_id="401155460",
    )

    assert validation["major_event"] is True
    assert validation["has_cross_tour_field_risk"] is True
    assert validation["players_with_thin_rounds"] == ["Jon Rahm"]
    assert validation["players_missing_dg_skill"] == ["Jon Rahm"]


def test_build_methodology_ctx_defaults_total_rounds_to_zero():
    service = GolfModelService(tour="pga")

    ctx = service._build_methodology_ctx(
        tournament_name="Masters Tournament",
        course_name="Augusta National",
        tid=7,
        composite=[],
        value_bets={},
        profile=None,
        ai_pre_analysis=None,
        matchup_bets=[],
        weights={},
        result={},
    )

    assert ctx["total_rounds"] == 0


def test_data_sources_handles_missing_total_rounds():
    lines = []

    _data_sources(
        lines,
        {
            "event_id": "123",
            "tournament_name": "Masters Tournament",
            "metric_counts": {},
            "rounds_by_year": {},
            "total_rounds": None,
        },
        {},
    )

    assert any("2019-2026 (0 total rounds)" in line for line in lines)


def test_fetch_matchup_value_bets_uses_all_books_and_matchup_threshold(monkeypatch):
    service = GolfModelService(
        tour="pga",
        strategy_config={"matchup_ev_threshold": 0.05},
    )
    captured = {}

    monkeypatch.setattr(
        "src.datagolf.fetch_matchup_odds_with_diagnostics",
        lambda market, tour="pga": (
            [
                {
                    "p1_player_name": "Player A",
                    "p2_player_name": "Player B",
                    "odds": {"bet365": {"p1": 110, "p2": -130}},
                }
            ],
            {"reason_code": "ok"},
        ),
    )
    monkeypatch.setattr("src.odds.get_preferred_book", lambda: "bet365")

    def _fake_find_matchup_value_bets(composite, odds, **kwargs):
        captured["kwargs"] = kwargs
        return (
            [],
            [],
            {
                "input_rows": len(odds),
                "selected_rows": 0,
                "all_qualifying_rows": 0,
                "reason_codes": {},
                "adaptation_state": "normal",
            },
        )

    monkeypatch.setattr(
        "src.matchup_value.find_matchup_value_bets_with_all_books",
        _fake_find_matchup_value_bets,
    )

    service._fetch_matchup_value_bets(
        composite=[{"player_key": "player_a", "player_display": "Player A", "composite": 70.0}],
        tid=9,
        mode="full",
    )

    assert captured["kwargs"]["ev_threshold"] == 0.05
    assert captured["kwargs"].get("required_book") is None


def test_run_analysis_logs_matchups_even_when_placement_quality_fails(monkeypatch):
    service = GolfModelService(tour="pga")
    logged = {"placements": 0, "matchups": 0}

    monkeypatch.setattr("src.services.golf_model_service.db.get_or_create_tournament", lambda tournament_name, course_name: 7)
    monkeypatch.setattr(
        "src.services.golf_model_service.db.get_all_players",
        lambda tid, confirmed_field_only=False: ["player_a", "player_b"],
    )
    monkeypatch.setattr("src.services.golf_model_service.db.get_rounds_count", lambda: 24)
    monkeypatch.setattr(
        GolfModelService,
        "_sync_tournament_data",
        lambda self, tid, event_id=None: {"decompositions_raw": None},
    )
    monkeypatch.setattr(GolfModelService, "_sync_skill_data", lambda self, tid, field_keys: None)
    monkeypatch.setattr(
        GolfModelService,
        "_validate_field_data",
        lambda self, tid, tournament_name, field_keys, field_source="unknown", expected_event_id=None: {
            "has_cross_tour_field_risk": False,
            "strict_field_verified": True,
            "failed_invariants": [],
            "summary": "Field verified for this event.",
        },
    )
    monkeypatch.setattr(GolfModelService, "_compute_rolling_stats", lambda self, tid, field_keys, course_num: {})
    monkeypatch.setattr(GolfModelService, "_load_course_profile", lambda self, course_name, decompositions_raw=None: {})
    monkeypatch.setattr(GolfModelService, "_get_weights", lambda self, course_num: {})
    monkeypatch.setattr(
        GolfModelService,
        "_run_composite",
        lambda self, tid, weights, course_name: [
            {
                "player_key": "player_a",
                "player_display": "Player A",
                "composite": 70.0,
                "form": 68.0,
                "course_fit": 66.0,
                "momentum": 55.0,
            },
            {
                "player_key": "player_b",
                "player_display": "Player B",
                "composite": 62.0,
                "form": 60.0,
                "course_fit": 58.0,
                "momentum": 45.0,
            },
        ],
    )
    monkeypatch.setattr(GolfModelService, "_fetch_odds", lambda self: {"outrights": [{"player": "Player A"}]})
    monkeypatch.setattr(
        GolfModelService,
        "_compute_value_bets",
        lambda self, composite, all_odds, tid: {
            "outright": [
                {
                    "pick": "Player A",
                    "ev": 0.85,
                    "is_value": False,
                    "suspicious": False,
                    "ev_capped": False,
                    "needs_review": False,
                }
            ]
        },
    )
    monkeypatch.setattr("src.portfolio.enforce_diversification", lambda bets, field_strength=None: bets)
    monkeypatch.setattr(
        GolfModelService,
        "_fetch_matchup_value_bets",
        lambda self, composite, tid, mode="full": (
            [
                {
                    "pick": "Player A",
                    "pick_key": "player_a",
                    "opponent": "Player B",
                    "opponent_key": "player_b",
                    "model_win_prob": 0.55,
                    "implied_prob": 0.5,
                    "ev": 0.1,
                    "ev_pct": "10.0%",
                }
            ],
            [
                {
                    "pick": "Player A",
                    "pick_key": "player_a",
                    "opponent": "Player B",
                    "opponent_key": "player_b",
                    "book": "bet365",
                    "model_win_prob": 0.55,
                    "implied_prob": 0.5,
                    "ev": 0.1,
                    "ev_pct": "10.0%",
                }
            ],
            {
                "state": "edges_available",
                "errors": [],
                "selection_counts": {"selected_rows": 1, "all_qualifying_rows": 1},
                "reason_codes": {},
            },
        ),
    )
    monkeypatch.setattr(GolfModelService, "_fetch_3ball_value_bets", lambda self, composite, tid: [])
    monkeypatch.setattr(
        "src.value.compute_run_quality",
        lambda value_bets: {"score": 0.99, "issues": ["Average |EV| = 85%"], "pass": False},
    )
    monkeypatch.setattr(GolfModelService, "_log_predictions", lambda self, tid, value_bets: logged.__setitem__("placements", logged["placements"] + 1))
    monkeypatch.setattr(GolfModelService, "_log_matchup_predictions", lambda self, tid, matchup_bets: logged.__setitem__("matchups", logged["matchups"] + 1))
    monkeypatch.setattr(GolfModelService, "_generate_card", lambda self, *args, **kwargs: "/tmp/card.md")
    monkeypatch.setattr(GolfModelService, "_log_run", lambda self, tid, result: None)

    result = service.run_analysis(
        tournament_name="Masters Tournament",
        course_name="Augusta National Golf Club",
        enable_ai=False,
        enable_backfill=False,
        include_methodology=False,
        mode="full",
        strategy_source="config",
    )

    assert result["status"] == "complete"
    assert len(result["matchup_bets_all_books"]) == 1
    assert logged["placements"] == 0
    assert logged["matchups"] == 1
