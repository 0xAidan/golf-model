"""
Champion-challenger model protocol (recovery defect 3.3.1).

Defines the minimal interface every candidate model must expose so it can be
registered and evaluated in shadow mode. The champion (`v4.2`) is wrapped by
`ChampionModel` and delegates to the existing matchup_value / value pipelines
WITHOUT altering numeric output — it is a pure adapter.

Phase-2 challengers (T1 shot-level SG, T2 Monte Carlo) will land here as
additional classes and be listed in `src.config.CHALLENGERS`. This module
does not add any challenger implementations on its own.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ModelProtocol(Protocol):
    """Structural protocol every champion/challenger model implements."""

    name: str
    version: str

    def predict_matchup(
        self,
        p1: dict[str, Any],
        p2: dict[str, Any],
        features: dict[str, Any],
    ) -> float:
        """Return P(p1 wins) in [0, 1]."""
        ...

    def predict_outright(
        self,
        player: dict[str, Any],
        features: dict[str, Any],
    ) -> float:
        """Return outright win probability in [0, 1]."""
        ...


class BaseModel:
    """Concrete base that satisfies ModelProtocol with safe defaults.

    Subclasses set `name` / `version` and override the predict methods.
    """

    name: str = "base"
    version: str = "0.0"

    def predict_matchup(
        self,
        p1: dict[str, Any],
        p2: dict[str, Any],
        features: dict[str, Any],
    ) -> float:
        raise NotImplementedError

    def predict_outright(
        self,
        player: dict[str, Any],
        features: dict[str, Any],
    ) -> float:
        raise NotImplementedError


class ChampionModel(BaseModel):
    """Adapter for the current live model (v4.2).

    The champion's numeric output must stay byte-identical to pre-rails main.
    Rather than re-derive probabilities here, this adapter accepts the
    probability the live pipeline already computed via the `features` dict
    (key `champion_p`). When the caller wants an independent recompute, it can
    pass the Platt sigmoid inputs and the adapter will fall through to
    `src.matchup_value` helpers. Either way, no new math is introduced.
    """

    name = "v4.2"
    version = "4.2"

    def predict_matchup(
        self,
        p1: dict[str, Any],
        p2: dict[str, Any],
        features: dict[str, Any],
    ) -> float:
        precomputed = features.get("champion_p")
        if precomputed is not None:
            return float(precomputed)
        # Fallback: replicate the Platt-only path from matchup_value without
        # any blending (the caller must pass the DG blend separately via
        # features if they want the full live number).
        import math

        from src.matchup_value import _get_platt_params

        gap = float(features.get("composite_gap", 0.0))
        a, b = _get_platt_params()
        return 1.0 / (1.0 + math.exp(a * abs(gap) + b))

    def predict_outright(
        self,
        player: dict[str, Any],
        features: dict[str, Any],
    ) -> float:
        precomputed = features.get("champion_p")
        if precomputed is not None:
            return float(precomputed)
        return float(player.get("model_prob", 0.0) or 0.0)


# Module-level registry. Challengers MUST also be referenced by name in
# `src.config.CHALLENGERS` to be evaluated — presence here alone has no effect.
MODELS: dict[str, BaseModel] = {
    ChampionModel.name: ChampionModel(),
}


def register_model(model: BaseModel) -> None:
    """Register a model instance under its declared `name`."""
    if not isinstance(model, BaseModel):
        raise TypeError("register_model requires a BaseModel instance")
    MODELS[model.name] = model


def get_model(name: str) -> BaseModel | None:
    return MODELS.get(name)


def get_champion() -> BaseModel:
    from src import config

    champion = MODELS.get(config.CHAMPION)
    if champion is None:
        raise RuntimeError(f"Champion {config.CHAMPION!r} not registered in MODELS")
    return champion


def iter_active_challengers() -> list[BaseModel]:
    """Return the BaseModel instances for every name in config.CHALLENGERS.

    Names that are not registered are silently skipped (never break the
    pipeline). Shadow evaluation is best-effort.
    """
    from src import config

    out: list[BaseModel] = []
    for name in config.CHALLENGERS:
        model = MODELS.get(name)
        if model is not None:
            out.append(model)
    return out
