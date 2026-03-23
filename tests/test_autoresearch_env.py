"""Autoresearch environment flags."""

def test_autoresearch_auto_apply_default_off(monkeypatch):
    from src.autoresearch_env import autoresearch_auto_apply_enabled

    monkeypatch.delenv("AUTORESEARCH_AUTO_APPLY", raising=False)
    assert autoresearch_auto_apply_enabled() is False


def test_autoresearch_auto_apply_on(monkeypatch):
    from src.autoresearch_env import autoresearch_auto_apply_enabled

    monkeypatch.setenv("AUTORESEARCH_AUTO_APPLY", "1")
    assert autoresearch_auto_apply_enabled() is True
