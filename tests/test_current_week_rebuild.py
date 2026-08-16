from src.current_week_rebuild import current_event_target, rebuild_current_week


def test_current_event_target_missing(monkeypatch) -> None:
    monkeypatch.setattr("src.current_week_rebuild.get_current_event_info", lambda tour="pga": None)
    result = current_event_target()
    assert result["ok"] is False
    assert result["skipped"] is True


def test_rebuild_current_week_records_target(monkeypatch) -> None:
    written: list[dict] = []

    monkeypatch.setattr(
        "src.current_week_rebuild.get_current_event_info",
        lambda tour="pga": {"event_id": "401", "event_name": "FedEx St. Jude Championship"},
    )
    monkeypatch.setattr(
        "src.current_week_rebuild.write_rebuild_heartbeat",
        lambda **kwargs: written.append(kwargs),
    )
    monkeypatch.setattr(
        "src.current_week_rebuild.queue_live_refresh",
        lambda: {"queued": True},
    )
    monkeypatch.setattr(
        "src.current_week_rebuild.grade_completed_events",
        lambda year=None: {"ok": True},
    )

    report = rebuild_current_week()
    assert report["ok"] is True
    assert report["current_event"]["event_id"] == "401"
    assert any(row.get("target_event_id") == "401" for row in written)
