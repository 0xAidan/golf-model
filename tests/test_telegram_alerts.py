"""Tests for personal Telegram matchup EV alerts."""

from unittest.mock import MagicMock


def test_missing_env_no_http(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    def boom(*_a, **_k):
        raise AssertionError("requests.post should not run without Telegram env")

    monkeypatch.setattr("src.telegram_alerts.requests.post", boom)

    from src.telegram_alerts import maybe_send_matchup_ev_alerts

    maybe_send_matchup_ev_alerts(
        event_name="Test Event",
        event_id="401",
        matchup_bets_all_books=[
            {
                "pick": "A",
                "opponent": "B",
                "pick_key": "a",
                "opponent_key": "b",
                "book": "bk",
                "odds": 100,
                "ev": 0.2,
            }
        ],
        matchup_diagnostics={"state": "ok", "errors": []},
    )


def test_ev_threshold_filters_rows(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    monkeypatch.delenv("TELEGRAM_MATCHUP_EV_THRESHOLD", raising=False)

    captured: dict[str, str] = {}

    def fake_send(text: str) -> bool:
        captured["text"] = text
        return True

    monkeypatch.setattr("src.telegram_alerts.send_telegram_message", fake_send)
    monkeypatch.setattr("src.telegram_alerts.db.try_claim_telegram_alert", lambda _h: True)

    from src.telegram_alerts import maybe_send_matchup_ev_alerts

    maybe_send_matchup_ev_alerts(
        event_name="Tournament",
        event_id="e1",
        matchup_bets_all_books=[
            {
                "pick": "Low",
                "opponent": "X",
                "pick_key": "low",
                "opponent_key": "x",
                "book": "bk",
                "odds": 100,
                "ev": 0.05,
            },
            {
                "pick": "High",
                "opponent": "Y",
                "pick_key": "high",
                "opponent_key": "y",
                "book": "bk",
                "odds": -110,
                "ev": 0.10,
            },
        ],
        matchup_diagnostics={"errors": []},
    )

    assert "High" in captured["text"]
    assert "Low" not in captured["text"]


def test_dedupe_skip_sends_nothing(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    sent: list[str] = []

    def fake_send(text: str) -> bool:
        sent.append(text)
        return True

    monkeypatch.setattr("src.telegram_alerts.send_telegram_message", fake_send)
    monkeypatch.setattr("src.telegram_alerts.db.try_claim_telegram_alert", lambda _h: False)

    from src.telegram_alerts import maybe_send_matchup_ev_alerts

    maybe_send_matchup_ev_alerts(
        event_name="T",
        event_id="1",
        matchup_bets_all_books=[
            {
                "pick": "A",
                "opponent": "B",
                "pick_key": "a",
                "opponent_key": "b",
                "book": "bk",
                "odds": 100,
                "ev": 0.15,
            }
        ],
        matchup_diagnostics={"errors": []},
    )

    assert sent == []


def test_pipeline_error_skips_send(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    posted: list[int] = []

    monkeypatch.setattr(
        "src.telegram_alerts.requests.post",
        lambda *a, **k: posted.append(1) or MagicMock(status_code=200),
    )

    from src.telegram_alerts import maybe_send_matchup_ev_alerts

    maybe_send_matchup_ev_alerts(
        event_name="T",
        event_id="1",
        matchup_bets_all_books=[
            {"pick": "A", "opponent": "B", "pick_key": "a", "opponent_key": "b", "book": "bk", "odds": 100, "ev": 0.2}
        ],
        matchup_diagnostics={"state": "pipeline_error", "errors": ["x"]},
    )

    assert posted == []


def test_stable_alert_hash_includes_market_type():
    from src.telegram_alerts import stable_alert_hash

    base = {
        "pick_key": "p1",
        "opponent_key": "p2",
        "book": "bk",
        "odds": 100,
        "ev": 0.1,
    }
    h1 = stable_alert_hash(event_id="e", row={**base, "market_type": "tournament_matchups"})
    h2 = stable_alert_hash(event_id="e", row={**base, "market_type": "round_matchups"})
    assert h1 != h2
