"""Inference for the additive, versioned expected-strokes research challenger.

This module deliberately does not replace any existing ranking or pricing path.
Every feature uses rounds from events completed strictly before ``as_of``.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Iterable, Mapping

FEATURE_NAMES = (
    "sg_total_8", "sg_total_24", "sg_total_50",
    "sg_ott_24", "sg_app_24", "sg_arg_24", "sg_putt_24",
    "sg_ott_50", "sg_app_50", "sg_arg_50", "sg_putt_50",
    "recent_trend", "course_residual", "history_coverage", "layoff",
)
SG_COMPONENTS = ("sg_total", "sg_ott", "sg_app", "sg_arg", "sg_putt")
FEATURE_NAMES_V2 = (*FEATURE_NAMES, "sg_raw_50", "sg_total_100", "sg_total_150",
                    "ewm_total_16", "ewm_total_48", "ewm_total_120",
                    "ewm_ott_48", "ewm_app_48", "ewm_arg_48", "ewm_putt_48",
                    "volatility_50", "course_time_residual", "skill_layoff")


def day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def provider_player_key(row: Mapping, *, tour: str | None = None) -> str | None:
    """A name is display provenance; only a tour and positive DataGolf ID identify a player."""
    scope = str(tour or row.get("tour") or "").strip().lower()
    values = [row.get(field) for field in ("dg_id", "datagolf_id") if row.get(field) is not None]
    if not scope or not values or any(isinstance(value, bool) for value in values):
        return None
    text = [str(value).strip() for value in values]
    if any(not value.isdigit() or int(value) <= 0 for value in text) or len({int(value) for value in text}) != 1:
        return None
    return f"{scope}:datagolf:{int(text[0])}"


def eligible_history(rounds: Iterable[Mapping], as_of: str) -> list[dict]:
    """Return deterministically ordered prior completed rounds, deduplicated by identity."""
    cutoff = day(as_of)
    if cutoff is None:
        raise ValueError("as_of must be an ISO date")
    unique: dict[tuple, dict] = {}
    conflicting: set[tuple] = set()
    for raw in rounds:
        identity = provider_player_key(raw)
        completed = day(raw.get("event_completed"))
        if identity is None or completed is None or completed >= cutoff or finite(raw.get("sg_total")) is None:
            continue
        key = (identity, str(raw.get("event_id")), raw.get("year"), raw.get("round_num"))
        row = dict(raw)
        if key in unique and any(finite(unique[key].get(k)) != finite(row.get(k)) for k in SG_COMPONENTS):
            conflicting.add(key)
        unique.setdefault(key, row)
    return sorted(
        (r for k, r in unique.items() if k not in conflicting),
        key=lambda r: (str(r.get("event_completed")), str(r.get("event_id")), int(r.get("round_num") or 0)),
    )


def _shrunk_mean(rows: list[dict], component: str, window: int, prior: float) -> float:
    values = [v for r in rows[-window:] if (v := finite(r.get(component))) is not None]
    return sum(values) / (len(values) + prior) if values else 0.0


def player_features(rounds: Iterable[Mapping], *, as_of: str, course_num: Any = None) -> dict[str, Any]:
    history = eligible_history(rounds, as_of)
    if len({provider_player_key(row) for row in history}) > 1:
        raise ValueError("Features require a single tour/DataGolf player identity")
    raw: dict[str, float] = {}
    for window, prior in ((8, 8.0), (24, 12.0), (50, 20.0)):
        raw[f"sg_total_{window}"] = _shrunk_mean(history, "sg_total", window, prior)
    for window, prior in ((24, 12.0), (50, 20.0)):
        for component in SG_COMPONENTS[1:]:
            raw[f"{component}_{window}"] = _shrunk_mean(history, component, window, prior)
    course = [r for r in history if course_num is not None and str(r.get("course_num")) == str(course_num)]
    course_n = min(len(course), 50)
    raw["recent_trend"] = raw["sg_total_8"] - raw["sg_total_50"]
    course_mean = _shrunk_mean(course, "sg_total", 50, 20.0)
    raw["course_residual"] = course_mean - raw["sg_total_50"] * course_n / (course_n + 20.0)
    raw["history_coverage"] = min(len(history), 50) / 50.0
    latest = day(history[-1].get("event_completed")) if history else None
    gap = (day(as_of) - latest).days if latest is not None else 90
    raw["layoff"] = min(gap, 90) / 90.0
    return {
        "values": [raw[name] for name in FEATURE_NAMES],
        "history_rounds": len(history),
        "last_observed": latest.isoformat() if latest else None,
        "feature_coverage": min(len(history), 50) / 50.0,
        "naive_sg": _shrunk_mean(history, "sg_total", 50, 0.0),
    }


def predict_expected_sg(model: Mapping, features: Iterable[float]) -> float:
    values = list(features)
    names = tuple(model.get("feature_names", []))
    if names not in {FEATURE_NAMES, FEATURE_NAMES_V2} or len(values) != len(names):
        raise ValueError("Unsupported learning-challenger feature schema")
    if model.get("kind") == "sg50_shrink":
        count = values[names.index("history_coverage")] * 50
        return values[names.index("sg_raw_50")] * count / (count + float(model["prior_rounds"]))
    if model.get("kind") == "boosted_stumps":
        return float(model["intercept"]) + sum(
            float(tree["left"] if values[tree["feature"]] <= tree["threshold"] else tree["right"])
            for tree in model["trees"])
    values += [max(0.0, values[index] - knot) for index, knot in model.get("basis_knots", [])]
    mean, scale, coef = model["feature_mean"], model["feature_scale"], model["coefficients"]
    return float(model["intercept"]) + sum(
        float(c) * (float(v) - float(m)) / float(s)
        for v, m, s, c in zip(values, mean, scale, coef)
    )


def player_features_v2(rounds: Iterable[Mapping], *, as_of: str, course_num: Any = None) -> dict[str, Any]:
    """Expanded, predetermined recency features using strictly completed past events."""
    history = eligible_history(rounds, as_of)
    profile = player_features(history, as_of=as_of, course_num=course_num)
    values = {name: value for name, value in zip(FEATURE_NAMES, profile["values"])}
    values["sg_raw_50"] = profile["naive_sg"]
    for window in (100, 150):
        values[f"sg_total_{window}"] = _shrunk_mean(history, "sg_total", window, 20.0)

    def ewm(component, half_life):
        weighted, mass = 0.0, 0.0
        for age, row in enumerate(reversed(history[-240:])):
            value = finite(row.get(component))
            if value is not None:
                weight = 2 ** (-age / half_life)
                weighted += weight * value
                mass += weight
        return weighted / (mass + 8.0) if mass else 0.0

    for half_life in (16, 48, 120):
        values[f"ewm_total_{half_life}"] = ewm("sg_total", half_life)
    for component in ("ott", "app", "arg", "putt"):
        values[f"ewm_{component}_48"] = ewm(f"sg_{component}", 48)
    latest = [float(row["sg_total"]) for row in history[-50:]]
    values["volatility_50"] = math.sqrt(sum((v - profile["naive_sg"]) ** 2 for v in latest) / len(latest)) if latest else 0.0
    course_sum = course_mass = 0.0
    for row in history:
        if course_num is not None and str(row.get("course_num")) == str(course_num):
            age = (day(as_of) - day(row["event_completed"])).days
            weight = 2 ** (-age / 730.0)
            course_sum += float(row["sg_total"]) * weight
            course_mass += weight
    values["course_time_residual"] = (course_sum - values["ewm_total_48"] * course_mass) / (course_mass + 20.0)
    values["skill_layoff"] = values["ewm_total_48"] * values["layoff"]
    profile["values"] = [values[name] for name in FEATURE_NAMES_V2]
    return profile


def pair_probability(model: Mapping, player_score: float, opponent_score: float) -> float:
    """Calibrated binary finish-order probability, conditional on a decisive comparison.

    This is a shadow probability: ties, withdrawals and market settlement rules need
    a dedicated pricing layer before it can be used as an executable quote.
    """
    logit = max(-30.0, min(30.0, float(model["pair_slope"]) * (player_score - opponent_score)))
    return 1.0 / (1.0 + math.exp(-logit))


def rank_players(
    model: Mapping,
    rounds: Iterable[Mapping],
    players: Iterable[Mapping],
    *,
    as_of: str,
    course_num: Any = None,
    tour: str = "pga",
    identity_rounds: Iterable[Mapping] | None = None,
    diagnostics: dict | None = None,
) -> list[dict[str, Any]]:
    """Project the fitted research model on a named field, preserving its own SG unit."""
    rounds = list(rounds)
    players = list(players)
    scope = str(tour).strip().lower()
    by_player: dict[str, list] = {}
    aliases: dict[str, set[str]] = {}
    for row in identity_rounds if identity_rounds is not None else rounds:
        identity = provider_player_key(row)
        if identity is None or str(row.get("tour") or "").strip().lower() != scope:
            continue
        names = [row.get("player_key"), *(alias.get("player_key") for alias in row.get("_source_aliases", []))]
        for alias in names:
            if alias:
                aliases.setdefault(str(alias), set()).add(identity)
    for row in rounds:
        identity = provider_player_key(row)
        if identity is not None and str(row.get("tour") or "").strip().lower() == scope:
            by_player.setdefault(identity, []).append(row)
    withheld = []
    public_alias_counts = {}
    for player in players:
        alias = str(player.get("player_key") or "")
        public_alias_counts[alias] = public_alias_counts.get(alias, 0) + 1
    ranked = []
    for player in players:
        key = str(player.get("player_key") or "")
        if not key:
            continue
        if public_alias_counts[key] > 1:
            withheld.append({"player_key": key, "reason": "duplicate_field_alias"})
            continue
        explicit = any(player.get(field) is not None for field in ("dg_id", "datagolf_id"))
        identity = provider_player_key(player, tour=scope) if explicit else None
        matched = "datagolf_id" if explicit else "unique_observed_alias"
        if explicit and (identity is None or (player.get("tour") and str(player["tour"]).lower() != scope)):
            withheld.append({"player_key": key, "reason": "invalid_provider_identity"})
            continue
        if explicit and aliases.get(key) and identity not in aliases[key]:
            withheld.append({"player_key": key, "reason": "provider_id_alias_mismatch"})
            continue
        if not explicit:
            matches = aliases.get(key, set())
            if len(matches) != 1:
                withheld.append({"player_key": key, "reason": "ambiguous_alias_missing_provider_id" if matches else "missing_provider_identity"})
                continue
            identity = next(iter(matches))
        builder = player_features_v2 if tuple(model.get("feature_names", [])) == FEATURE_NAMES_V2 else player_features
        profile = builder(by_player.get(identity, []), as_of=as_of, course_num=course_num)
        # Do not invent rankings for players with no usable historical coverage.
        if profile["history_rounds"] < int(model.get("minimum_history_rounds", 8)):
            withheld.append({"player_key": key, "reason": "insufficient_provider_history"})
            continue
        ranked.append({
            "player_key": key,
            "provider_player_key": identity, "dg_id": int(identity.rsplit(":", 1)[1]), "tour": scope,
            "identity_match": matched,
            "player_display": player.get("player_display") or player.get("player") or key.replace("_", " ").title(),
            "expected_sg_per_round": round(predict_expected_sg(model, profile["values"]), 4),
            "history_rounds": profile["history_rounds"],
            "last_observed": profile["last_observed"],
            "feature_coverage": profile["feature_coverage"],
        })
    ranked.sort(key=lambda r: (-r["expected_sg_per_round"], r["player_key"]))
    for index, row in enumerate(ranked, 1):
        row["rank"] = index
    if diagnostics is not None:
        diagnostics.update({"requested": len(players), "ranked": len(ranked), "withheld": withheld})
    return ranked
