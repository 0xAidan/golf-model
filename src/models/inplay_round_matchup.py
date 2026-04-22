"""
T6 — In-play round matchup prediction (SHADOW MODE ONLY).

Predicts P(player1 beats player2 over the current round) given the holes
already played. Logic:

  1. Start from the pre-round prior (model's expected score differential
     and per-player SD).
  2. Update with the partial score so far: remaining score is modeled as
     a Brownian bridge with SD scaled by sqrt(holes_remaining / 18).

This module is SHADOW ONLY in this PR: predictions are logged but never
turned into real bets. `assert_inplay_staking_disabled()` is invoked in
the bet-ticket path; flipping `INPLAY_STAKING_ENABLED` in config will
deliberately trip the assertion.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

from src import config


HOLES_PER_ROUND = 18
DEFAULT_PLAYER_ROUND_SD = 2.8  # typical per-player single-round SD in strokes
# Source marker carried on any downstream object (e.g. bet ticket payload).
# The bet-ticket builder must refuse to place a bet when this marker is set.
INPLAY_SOURCE_MARKER = "inplay_round_matchup_shadow"


def _safe_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _player_round_sd(player: str, features: Mapping[str, object] | None) -> float:
    """Per-player round SD. Uses features['round_sd'][player] if present; else default."""
    if not features:
        return DEFAULT_PLAYER_ROUND_SD
    sd_map = features.get("round_sd")
    if isinstance(sd_map, Mapping) and player in sd_map:
        return max(0.5, _safe_float(sd_map[player], DEFAULT_PLAYER_ROUND_SD))
    return DEFAULT_PLAYER_ROUND_SD


def _pre_round_prior(
    p1: str,
    p2: str,
    round_num: int,
    features: Mapping[str, object] | None,
) -> tuple[float, float]:
    """
    Return (mu_diff, sd_diff): expected score differential (p1 - p2) over
    a full round and its SD. Uses the pre-round model skill estimates if
    provided in features; otherwise a flat prior.
    """
    mu = 0.0
    if features:
        priors = features.get("pre_round_mean")
        if isinstance(priors, Mapping):
            m1 = _safe_float(priors.get(p1), 0.0)
            m2 = _safe_float(priors.get(p2), 0.0)
            mu = m1 - m2
    sd1 = _player_round_sd(p1, features)
    sd2 = _player_round_sd(p2, features)
    sd = math.sqrt(sd1 * sd1 + sd2 * sd2)
    return mu, sd


def predict_inplay_round(
    p1: str,
    p2: str,
    round_num: int,
    hole_num: int,
    current_scores: Mapping[str, float] | Sequence[float] | None,
    features: Mapping[str, object] | None = None,
) -> float:
    """
    Predict P(p1 beats p2) over the CURRENT round given holes already played.

    - `hole_num` is the number of holes COMPLETED so far (0..18).
    - `current_scores` maps player -> strokes-to-par (or strokes) already
      accumulated; a 2-sequence (p1_score, p2_score) is also accepted.
    - `features` may carry per-player SD and pre-round skill priors; if
      absent, flat priors and a default SD are used.

    Returns a probability in (0, 1).
    """
    mu_full, sd_full = _pre_round_prior(p1, p2, round_num, features)

    holes_done = max(0, min(HOLES_PER_ROUND, int(hole_num)))
    holes_left = HOLES_PER_ROUND - holes_done

    s1 = s2 = 0.0
    if isinstance(current_scores, Mapping):
        s1 = _safe_float(current_scores.get(p1), 0.0)
        s2 = _safe_float(current_scores.get(p2), 0.0)
    elif current_scores is not None:
        try:
            s1 = _safe_float(current_scores[0], 0.0)
            s2 = _safe_float(current_scores[1], 0.0)
        except (IndexError, TypeError):
            pass
    diff_so_far = s1 - s2  # lower is better; negative means p1 leads

    if holes_left == 0:
        # Round complete — deterministic outcome (with a tiny tie nudge).
        if diff_so_far < 0:
            return 0.999
        if diff_so_far > 0:
            return 0.001
        return 0.5

    # Brownian-bridge remainder: mean scales with fraction of holes left,
    # SD scales with sqrt of fraction of holes left.
    frac_left = holes_left / HOLES_PER_ROUND
    mu_remaining = mu_full * frac_left
    sd_remaining = max(0.1, sd_full * math.sqrt(frac_left))

    # Total final diff = diff_so_far + remainder. p1 beats p2 iff total < 0.
    # P(diff_so_far + X < 0) = Phi((-diff_so_far - mu_remaining) / sd_remaining)
    z = (-diff_so_far - mu_remaining) / sd_remaining
    p = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return min(0.999, max(0.001, p))


def assert_inplay_staking_disabled(source: str | None = None) -> None:
    """
    Hard staking ban for in-play round matchups.

    Call this anywhere a bet ticket is about to be built so that an in-play
    prediction can never be turned into a real stake while SHADOW mode is
    active. Also fails if `INPLAY_STAKING_ENABLED` is ever flipped to True
    in this PR.
    """
    if source == INPLAY_SOURCE_MARKER:
        raise RuntimeError(
            "In-play round matchups are in shadow mode only"
        )
    if getattr(config, "INPLAY_STAKING_ENABLED", False):
        raise RuntimeError(
            "In-play round matchups are in shadow mode only"
        )


def build_bet_ticket(prediction: Mapping[str, object]) -> dict:
    """
    Minimal bet-ticket builder used to enforce the staking ban. Any caller
    that tries to turn an in-play round matchup prediction (source marked
    accordingly) into a real ticket will hit the assertion and raise.

    Kept small on purpose — this is the trip-wire, not the real ticket
    builder used by the rest of the system.
    """
    source = str(prediction.get("source") or "")
    assert_inplay_staking_disabled(source)
    return {
        "source": source,
        "player1": prediction.get("player1"),
        "player2": prediction.get("player2"),
        "predicted_p1": prediction.get("predicted_p1"),
        "stake": 0.0,
    }
