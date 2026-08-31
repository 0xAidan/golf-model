from src import ops_alerts


def test_send_ops_alert_ntfy(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "golf-ops-test")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    calls: list[dict] = []

    class FakeResponse:
        status_code = 200

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse()

    monkeypatch.setattr(ops_alerts.requests, "post", fake_post)
    sent = ops_alerts.send_ops_alert("Title", "Body")
    assert sent["ntfy"] is True
    assert calls[0]["url"].endswith("/golf-ops-test")


def test_send_ops_alert_noop_without_config(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    def boom(*_a, **_k):
        raise AssertionError("should not post")

    monkeypatch.setattr(ops_alerts.requests, "post", boom)
    sent = ops_alerts.send_ops_alert("Title", "Body")
    assert sent == {"ntfy": False, "telegram": False}
