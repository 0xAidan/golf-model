import os

from src import ai_brain


def test_is_ai_available_ignores_placeholder_openai_key(monkeypatch):
    monkeypatch.setenv("AI_BRAIN_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "your_openai_key_here")
    monkeypatch.setattr(ai_brain, "_ENV_BOOTSTRAPPED", True)
    assert ai_brain.is_ai_available() is False


def test_is_ai_available_accepts_real_openai_key(monkeypatch):
    monkeypatch.setenv("AI_BRAIN_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    monkeypatch.setattr(ai_brain, "_ENV_BOOTSTRAPPED", True)
    assert ai_brain.is_ai_available() is True
