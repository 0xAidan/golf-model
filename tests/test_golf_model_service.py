from src.services.golf_model_service import GolfModelService


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
    )

    assert validation["major_event"] is True
    assert validation["has_cross_tour_field_risk"] is True
    assert validation["players_with_thin_rounds"] == ["Jon Rahm"]
    assert validation["players_missing_dg_skill"] == ["Jon Rahm"]
