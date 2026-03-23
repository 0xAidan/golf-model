"""Map Optuna trials to StrategyConfig (PIT sub-weights + core betting knobs)."""

from __future__ import annotations

import math
from dataclasses import replace

import optuna

from backtester.experiments import _normalize_sub_weights
from backtester.strategy import StrategyConfig


def _softmax3(log_a: float, log_b: float, log_c: float) -> tuple[float, float, float]:
    """Stable softmax for three logits → positive weights summing to 1."""
    m = max(log_a, log_b, log_c)
    ea = math.exp(log_a - m)
    eb = math.exp(log_b - m)
    ec = math.exp(log_c - m)
    s = ea + eb + ec
    if s <= 0:
        return 1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0
    return ea / s, eb / s, ec / s


def strategy_from_optuna_trial(trial: optuna.Trial, baseline: StrategyConfig) -> StrategyConfig:
    """
    Build a candidate StrategyConfig from one Optuna trial.

    Primary: softmax logits for w_sub_course_fit / w_sub_form / w_sub_momentum.
    Secondary: min_ev, kelly_fraction, softmax_temp, max_implied_prob (bounded).
    """
    log_cf = trial.suggest_float("logit_sub_course_fit", -4.0, 4.0)
    log_fm = trial.suggest_float("logit_sub_form", -4.0, 4.0)
    log_mm = trial.suggest_float("logit_sub_momentum", -4.0, 4.0)
    w_cf, w_fm, w_mm = _softmax3(log_cf, log_fm, log_mm)

    min_ev = trial.suggest_float("min_ev", 0.02, 0.18, step=0.005)
    kelly_fraction = trial.suggest_float("kelly_fraction", 0.05, 0.45, step=0.025)
    softmax_temp = trial.suggest_float("softmax_temp", 0.4, 2.5, step=0.05)
    max_implied_prob = trial.suggest_float("max_implied_prob", 0.20, 0.65, step=0.01)

    cfg = replace(
        baseline,
        w_sub_course_fit=round(w_cf, 4),
        w_sub_form=round(w_fm, 4),
        w_sub_momentum=round(w_mm, 4),
        min_ev=round(min_ev, 3),
        kelly_fraction=round(kelly_fraction, 3),
        softmax_temp=round(softmax_temp, 2),
        max_implied_prob=round(max_implied_prob, 3),
        name=f"{baseline.name or 'baseline'}_optuna_{trial.number}",
    )
    _normalize_sub_weights(cfg)
    return cfg
