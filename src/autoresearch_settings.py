"""
UI-persisted autoresearch settings (guardrail mode, engine mode, Optuna, theory LLM).
Stored in data/autoresearch_settings.json; env vars can still override guardrails in config layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SETTINGS_DIR = Path(__file__).resolve().parent.parent / "data"
_SETTINGS_FILE = _SETTINGS_DIR / "autoresearch_settings.json"
_CACHE: dict[str, Any] | None = None

DEFAULT_GUARDRAIL_MODE = "strict"
VALID_GUARDRAIL_MODES = ("strict", "loose")

DEFAULT_ENGINE_MODE = "research_cycle"
VALID_ENGINE_MODES = ("research_cycle", "optuna")

DEFAULT_SETTINGS: dict[str, Any] = {
    "guardrail_mode": DEFAULT_GUARDRAIL_MODE,
    "engine_mode": DEFAULT_ENGINE_MODE,
    "use_theory_engine_llm": False,
    "optuna_study_name": "golf_mo_dashboard",
    "optuna_trials_per_cycle": 3,
}


def _ensure_dir() -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)


def _merge_defaults(raw: dict[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    mode = (raw.get("guardrail_mode") or "").strip().lower()
    if mode in VALID_GUARDRAIL_MODES:
        out["guardrail_mode"] = mode
    em = (raw.get("engine_mode") or DEFAULT_ENGINE_MODE).strip().lower()
    if em in VALID_ENGINE_MODES:
        out["engine_mode"] = em
    if "use_theory_engine_llm" in raw:
        out["use_theory_engine_llm"] = bool(raw["use_theory_engine_llm"])
    if raw.get("optuna_study_name"):
        out["optuna_study_name"] = str(raw["optuna_study_name"]).strip()[:120] or DEFAULT_SETTINGS["optuna_study_name"]
    if raw.get("optuna_trials_per_cycle") is not None:
        try:
            n = int(raw["optuna_trials_per_cycle"])
            out["optuna_trials_per_cycle"] = max(1, min(50, n))
        except (TypeError, ValueError):
            pass
    return out


def get_settings() -> dict[str, Any]:
    """Return current autoresearch settings (cached)."""
    global _CACHE
    if _CACHE is not None:
        return dict(_CACHE)
    if not _SETTINGS_FILE.exists():
        _CACHE = dict(DEFAULT_SETTINGS)
        return dict(_CACHE)
    try:
        with open(_SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
        _CACHE = _merge_defaults(data)
        return dict(_CACHE)
    except (json.JSONDecodeError, OSError):
        _CACHE = dict(DEFAULT_SETTINGS)
        return dict(_CACHE)


def set_settings(updates: dict[str, Any]) -> dict[str, Any]:
    """Update settings, persist, clear cache."""
    global _CACHE
    _CACHE = None
    current = get_settings()
    if "guardrail_mode" in updates:
        mode = (str(updates["guardrail_mode"]).strip().lower()
                if updates["guardrail_mode"] else DEFAULT_GUARDRAIL_MODE)
        if mode not in VALID_GUARDRAIL_MODES:
            mode = DEFAULT_GUARDRAIL_MODE
        current["guardrail_mode"] = mode
    if "engine_mode" in updates:
        em = (str(updates["engine_mode"]).strip().lower()
              if updates["engine_mode"] else DEFAULT_ENGINE_MODE)
        if em not in VALID_ENGINE_MODES:
            em = DEFAULT_ENGINE_MODE
        current["engine_mode"] = em
    if "use_theory_engine_llm" in updates:
        current["use_theory_engine_llm"] = bool(updates["use_theory_engine_llm"])
    if "optuna_study_name" in updates and updates["optuna_study_name"]:
        current["optuna_study_name"] = str(updates["optuna_study_name"]).strip()[:120]
    if "optuna_trials_per_cycle" in updates and updates["optuna_trials_per_cycle"] is not None:
        try:
            n = int(updates["optuna_trials_per_cycle"])
            current["optuna_trials_per_cycle"] = max(1, min(50, n))
        except (TypeError, ValueError):
            pass
    _ensure_dir()
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    _CACHE = dict(current)
    return dict(current)


def get_guardrail_mode() -> str:
    """Return effective guardrail mode: from UI settings file. Env override in config layer."""
    return get_settings().get("guardrail_mode") or DEFAULT_GUARDRAIL_MODE


def invalidate_cache() -> None:
    """Test helper: clear in-process settings cache."""
    global _CACHE
    _CACHE = None
