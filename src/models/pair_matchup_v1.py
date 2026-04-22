"""Pair / team matchup model — v1 (analytics-only, flag-gated).

Tracking issue: **#47**. This module is the Phase 1 deliverable of the T3
team-matchup work for the Zurich Classic. It is deliberately NOT wired into
the card, snapshot, or live API — predictions are persisted to a shadow
table (:func:`log_pair_prediction`) behind the ``PAIR_MATCHUP_V1`` config
flag and surfaced only via the research endpoint. Phase 3 (going live) is
intentionally out of scope this week.

Formats
-------
Zurich alternates between two formats across the four rounds:

* **Foursomes** (alternate shot) — a single ball per team; teammates
  alternate strokes. Variance is high and the weaker player drags the
  team down disproportionately. Our combiner is the geometric mean of
  the two players' skill ratings: the GM is dominated by the smaller
  value (``GM(a, 0) = 0``), which is the directional behaviour we want.
* **Fourball** (best ball) — each player plays their own ball and the
  team records the better of the two on each hole. The team's expected
  per-hole score is closer to ``min(A, B)`` than to the mean. We
  approximate ``E[min(A, B)]`` assuming per-round score distributions
  are independent Gaussians centred on each player's skill rating with
  an SD drawn from historical round-to-round variance (default 2.5
  strokes, roughly the PGA Tour per-round SG-total SD).

Both combiners reduce to a single scalar "team strength", and the
head-to-head probability is then a logistic on the team-strength
difference. Calibration is Phase 2 work; the v1 scale constant is set
so that a 0.5-stroke-per-round skill gap maps to roughly a 57% win
probability, which matches the empirical spread in DG individual H2H
closing odds.

If per-player skill ratings are unavailable for any member of either
pair, the function falls back to a DG-composite-average baseline (mean
of whatever composites we do have). The audit in
``docs/research/pair_matchup_phase0_audit.md`` documents when this
fallback is the only thing we can run.

All formulas here are v1 — intentionally simple, well-commented, and
easy to replace once Phase 2 calibration has enough history.
"""

from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from src import config

logger = logging.getLogger(__name__)


FORMAT_FOURSOMES = "foursomes"
FORMAT_FOURBALL = "fourball"
_VALID_FORMATS = {FORMAT_FOURSOMES, FORMAT_FOURBALL}

# Default per-round score SD used by the fourball combiner when we have
# no per-player variance estimate. Chosen from the PGA Tour round-to-round
# SG-total SD (~2.4–2.6 strokes over 2020–2025 DG rounds data).
_DEFAULT_ROUND_SD = 2.5

# Scale constant for the logistic team-strength → P(win) mapping. At
# scale=3.0, a 0.5-strokes-per-round skill gap maps to sigmoid(1.5) ≈ 0.818
# team-level dominance. For two evenly matched pairs (diff=0), it returns 0.5.
# v1 only — Phase 2 will fit this per-format on historical pair results.
_DEFAULT_LOGISTIC_SCALE = 1.5


@dataclass(frozen=True)
class PlayerFeature:
    """Minimal feature payload for one player used by the v1 combiner.

    Attributes
    ----------
    skill:
        Expected per-round skill, higher = better. In production this is
        the composite score or DG per-round SG-total mean. The combiner
        is format-agnostic about units; what matters is that the two
        players in a pair use the same scale.
    round_sd:
        Optional per-round standard deviation. If ``None``, the module
        default (:data:`_DEFAULT_ROUND_SD`) is used.
    composite:
        Optional DG composite for the fallback path. If ``skill`` is
        missing but ``composite`` is present, ``composite`` is used.
    """

    skill: float | None
    round_sd: float | None = None
    composite: float | None = None


def _as_feature(raw: Any) -> PlayerFeature:
    """Coerce a dict / mapping / PlayerFeature into a PlayerFeature."""
    if isinstance(raw, PlayerFeature):
        return raw
    if isinstance(raw, Mapping):
        return PlayerFeature(
            skill=_safe_float(raw.get("skill")),
            round_sd=_safe_float(raw.get("round_sd")),
            composite=_safe_float(raw.get("composite")),
        )
    raise TypeError(f"pair_matchup_v1: cannot coerce {type(raw)!r} to PlayerFeature")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _foursomes_strength(a: PlayerFeature, b: PlayerFeature) -> float | None:
    """Geometric mean of the two players' skills.

    Rationale: foursomes (alternate shot) scoring is dominated by the
    weaker player — a pushed tee shot or missed short putt is binding
    because the partner has no recovery tee ball. ``GM = sqrt(a * b)``
    collapses toward the smaller value (if either is 0, GM is 0), which
    captures the "chain is as strong as its weakest link" intuition.

    The GM is only defined for non-negative skills; raw skill ratings
    can be negative (SG = strokes GAINED vs field). We therefore shift
    into a positive regime by adding a constant k, take the GM, then
    shift back. k is large enough that realistic SG-total values never
    push below zero.

    Returns ``None`` if either skill is missing — caller should fall
    back to the DG-composite baseline.
    """
    if a.skill is None or b.skill is None:
        return None
    # Shift constant: realistic SG-total skill is in [-3, +3]. k=10 puts
    # everyone comfortably positive while keeping the GM sensitive to the
    # gap between teammates.
    k = 10.0
    shifted = math.sqrt(max(a.skill + k, 1e-9) * max(b.skill + k, 1e-9))
    return shifted - k


def _fourball_strength(a: PlayerFeature, b: PlayerFeature) -> float | None:
    """Expected-value approximation of ``max(a, b)`` per round.

    Fourball lets each player play their own ball; the team records
    the better score on every hole, so at the round level the team's
    score is approximately ``max(a_skill, b_skill)`` (higher skill =
    better) plus a small correction for the fact that even the "worse"
    player occasionally outscores the partner.

    For independent Gaussians X ~ N(μ_a, σ²) and Y ~ N(μ_b, σ²), the
    closed-form for E[max(X, Y)] is::

        E[max] = (μ_a + μ_b)/2 + |μ_a - μ_b|/2 * erf(|μ_a - μ_b| / (2σ√2))
                 + σ * sqrt(2/π) * exp(-Δ²/(4σ²))    (approx; see refs)

    v1 uses the common approximation::

        E[max] ≈ max(μ_a, μ_b) + σ * φ(Δ/σ) / 2 — Δ = |μ_a - μ_b|

    which is tight when Δ << σ (which it usually is for two tour pros)
    and degenerates to ``max(μ_a, μ_b)`` when the gap is large — again
    the directional behaviour we want.

    Returns ``None`` if either skill is missing.
    """
    if a.skill is None or b.skill is None:
        return None
    sigma_a = a.round_sd if a.round_sd is not None else _DEFAULT_ROUND_SD
    sigma_b = b.round_sd if b.round_sd is not None else _DEFAULT_ROUND_SD
    # Pooled SD assuming independence.
    sigma = math.sqrt((sigma_a**2 + sigma_b**2) / 2.0)
    if sigma <= 0:
        return max(a.skill, b.skill)
    delta = abs(a.skill - b.skill)
    # Standard normal PDF at delta/sigma, scaled by sigma — the tail bonus
    # the worse player contributes on days when they happen to play better.
    phi = math.exp(-0.5 * (delta / sigma) ** 2) / math.sqrt(2 * math.pi)
    bonus = sigma * phi * 0.5
    return max(a.skill, b.skill) + bonus


def _composite_fallback_strength(*players: PlayerFeature) -> float | None:
    """Mean of available DG composites. Used when skill is missing.

    Documented in the Phase 0 audit: when historical pair data is
    insufficient, v1 runs on this fallback. Directional behaviour is
    preserved (stronger composite → higher strength) but the scale is
    no longer in strokes-per-round.
    """
    composites = [p.composite for p in players if p.composite is not None]
    if not composites:
        return None
    return sum(composites) / len(composites)


def _logistic(x: float, scale: float = _DEFAULT_LOGISTIC_SCALE) -> float:
    """Numerically safe logistic. ``scale`` maps strength diff → win prob."""
    z = max(min(x * scale, 50.0), -50.0)
    return 1.0 / (1.0 + math.exp(-z))


def predict_pair(
    team_a: tuple[str, str],
    team_b: tuple[str, str],
    format: str,
    features: Mapping[str, Any] | None = None,
) -> float:
    """Return P(team_a beats team_b) under the given format.

    Parameters
    ----------
    team_a, team_b:
        ``(player_key_1, player_key_2)`` tuples. Order within a team
        does not matter. Player keys are the normalized-name keys used
        elsewhere in the pipeline (see ``src.player_normalizer``).
    format:
        Either ``"foursomes"`` or ``"fourball"``. Case-insensitive; any
        other value raises ``ValueError``.
    features:
        Mapping ``player_key -> PlayerFeature | dict``. Missing players
        trigger the DG-composite fallback; if that also cannot produce
        a strength for either team, the function returns ``0.5``
        (genuinely no-signal case — useful for shadow logging without
        lying about confidence).

    Returns
    -------
    float
        Probability that team_a wins the match. Always in ``[0, 1]``.
    """
    fmt = str(format or "").strip().lower()
    if fmt not in _VALID_FORMATS:
        raise ValueError(
            f"pair_matchup_v1.predict_pair: unknown format {format!r}; "
            f"expected one of {sorted(_VALID_FORMATS)}"
        )

    if len(team_a) != 2 or len(team_b) != 2:
        raise ValueError("pair_matchup_v1.predict_pair: each team must have exactly 2 players")

    features = features or {}
    a1 = _as_feature(features.get(team_a[0], {}))
    a2 = _as_feature(features.get(team_a[1], {}))
    b1 = _as_feature(features.get(team_b[0], {}))
    b2 = _as_feature(features.get(team_b[1], {}))

    combiner = _foursomes_strength if fmt == FORMAT_FOURSOMES else _fourball_strength
    s_a = combiner(a1, a2)
    s_b = combiner(b1, b2)

    if s_a is None:
        s_a = _composite_fallback_strength(a1, a2)
    if s_b is None:
        s_b = _composite_fallback_strength(b1, b2)

    if s_a is None or s_b is None:
        # No signal either way — do not pretend to have an edge. Phase 2
        # will tune this; for v1 shadow logging a tied probability is the
        # honest answer.
        return 0.5

    return _logistic(s_a - s_b)


# ---------------------------------------------------------------------------
# Shadow logging
# ---------------------------------------------------------------------------


_PAIR_PREDICTIONS_DDL = """
CREATE TABLE IF NOT EXISTS pair_matchup_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT,
    team_a_p1 TEXT NOT NULL,
    team_a_p2 TEXT NOT NULL,
    team_b_p1 TEXT NOT NULL,
    team_b_p2 TEXT NOT NULL,
    format TEXT NOT NULL,
    predicted_p_a REAL NOT NULL,
    ts TEXT DEFAULT (datetime('now'))
);
"""


def ensure_shadow_table(conn: sqlite3.Connection) -> None:
    """Create the shadow table if it doesn't exist. Idempotent."""
    conn.execute(_PAIR_PREDICTIONS_DDL)
    conn.commit()


def log_pair_prediction(
    conn: sqlite3.Connection,
    *,
    event_id: str | None,
    team_a: tuple[str, str],
    team_b: tuple[str, str],
    format: str,
    predicted_p_a: float,
) -> int:
    """Append one shadow prediction row. Returns the new row id.

    Gated on :data:`src.config.PAIR_MATCHUP_V1` — callers should skip
    invoking this when the flag is off. The guard here is defensive so
    that accidental calls from disabled code paths are no-ops.
    """
    if not config.PAIR_MATCHUP_V1:
        logger.debug("pair_matchup_v1: shadow log skipped (flag off)")
        return -1

    ensure_shadow_table(conn)
    cur = conn.execute(
        """INSERT INTO pair_matchup_predictions
           (event_id, team_a_p1, team_a_p2, team_b_p1, team_b_p2, format, predicted_p_a)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id,
            team_a[0],
            team_a[1],
            team_b[0],
            team_b[1],
            str(format).lower(),
            float(predicted_p_a),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def fetch_shadow_predictions(
    conn: sqlite3.Connection,
    *,
    event_id: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Read back shadow predictions. Used by the research endpoint."""
    ensure_shadow_table(conn)
    if event_id is None:
        cur = conn.execute(
            "SELECT * FROM pair_matchup_predictions ORDER BY id DESC LIMIT ?",
            (int(limit),),
        )
    else:
        cur = conn.execute(
            "SELECT * FROM pair_matchup_predictions WHERE event_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (event_id, int(limit)),
        )
    return [dict(r) for r in cur.fetchall()]


__all__ = [
    "FORMAT_FOURSOMES",
    "FORMAT_FOURBALL",
    "PlayerFeature",
    "predict_pair",
    "ensure_shadow_table",
    "log_pair_prediction",
    "fetch_shadow_predictions",
]
