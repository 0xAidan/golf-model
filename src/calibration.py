"""
Empirical calibration curve for probability correction.

After each tournament, computes prediction accuracy by probability bucket
and builds correction factors. When we have enough data (50+ predictions
per bucket), these corrections are applied to future probabilities.

Rows are stored per ``bet_type`` (e.g. ``top10``, ``matchup``) with a global
aggregate under ``bet_type == ''`` used when a market-specific bucket is
thinly sampled.
"""

from __future__ import annotations

from typing import Any

from src import db

PROBABILITY_BUCKETS = [
    (0.00, 0.02, "0-2%"),
    (0.02, 0.05, "2-5%"),
    (0.05, 0.10, "5-10%"),
    (0.10, 0.20, "10-20%"),
    (0.20, 0.35, "20-35%"),
    (0.35, 0.50, "35-50%"),
    (0.50, 1.00, "50-100%"),
]

MIN_SAMPLE_FOR_CORRECTION = 50

_GLOBAL_BET_TYPE = ""


def _bucket_label(probability: float) -> str | None:
    for low, high, label in PROBABILITY_BUCKETS:
        if low <= probability < high:
            return label
    return None


def update_calibration_curve() -> dict[str, Any]:
    """
    Recompute calibration curves from all prediction_log data.

    Writes a global curve (``bet_type`` empty string) plus one curve per
    distinct non-empty ``bet_type`` present in the log.
    """
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT model_prob, actual_outcome, bet_type FROM prediction_log "
        "WHERE model_prob IS NOT NULL AND actual_outcome IS NOT NULL"
    ).fetchall()
    conn.close()

    if not rows:
        return {}

    row_dicts = [dict(r) for r in rows]
    distinct_types = sorted(
        {(r["bet_type"] or "").strip() for r in row_dicts if (r["bet_type"] or "").strip()}
    )
    segments: list[tuple[str, list[dict]]] = [(_GLOBAL_BET_TYPE, row_dicts)]
    for bt in distinct_types:
        subset = [r for r in row_dicts if (r["bet_type"] or "").strip() == bt]
        if subset:
            segments.append((bt, subset))

    all_results: dict[str, Any] = {}

    for bet_type_key, segment in segments:
        type_results: dict[str, Any] = {}
        conn = db.get_conn()
        conn.execute("DELETE FROM calibration_curve WHERE bet_type = ?", (bet_type_key,))
        for low, high, label in PROBABILITY_BUCKETS:
            in_bucket = [r for r in segment if low <= r["model_prob"] < high]
            if not in_bucket:
                continue

            predicted_avg = sum(r["model_prob"] for r in in_bucket) / len(in_bucket)
            actual_rate = sum(r["actual_outcome"] for r in in_bucket) / len(in_bucket)
            sample_size = len(in_bucket)

            if predicted_avg > 0:
                correction_factor = actual_rate / predicted_avg
            else:
                correction_factor = 1.0

            type_results[label] = {
                "predicted_avg": round(predicted_avg, 6),
                "actual_hit_rate": round(actual_rate, 6),
                "sample_size": sample_size,
                "correction_factor": round(correction_factor, 4),
            }

            conn.execute(
                """
                INSERT INTO calibration_curve
                    (bet_type, probability_bucket, predicted_avg, actual_hit_rate,
                     sample_size, correction_factor)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    bet_type_key,
                    label,
                    predicted_avg,
                    actual_rate,
                    sample_size,
                    correction_factor,
                ),
            )
        conn.commit()
        conn.close()
        all_results[bet_type_key or "global"] = type_results

    return all_results


def get_calibration_correction(probability: float, bet_type: str | None = None) -> float:
    """
    Correction factor for a given probability.

    Uses the curve for ``bet_type`` when the bucket has enough samples; otherwise
    falls back to the global curve (``bet_type`` aggregate).
    Returns 1.0 when neither curve has sufficient samples for that bucket.
    """
    label = _bucket_label(probability)
    if label is None:
        return 1.0

    bt = (bet_type or "").strip()

    def _fetch_correction(conn, btype: str) -> float | None:
        row = conn.execute(
            """
            SELECT correction_factor, sample_size FROM calibration_curve
            WHERE bet_type = ? AND probability_bucket = ?
            """,
            (btype, label),
        ).fetchone()
        if row and row["sample_size"] >= MIN_SAMPLE_FOR_CORRECTION:
            return float(row["correction_factor"])
        return None

    conn = db.get_conn()
    try:
        if bt:
            corr = _fetch_correction(conn, bt)
            if corr is not None:
                return corr
        corr = _fetch_correction(conn, _GLOBAL_BET_TYPE)
        if corr is not None:
            return corr
        return 1.0
    finally:
        conn.close()


def fetch_calibration_curves_grouped() -> dict[str, Any]:
    """Return all calibration_curve rows grouped by ``bet_type`` for APIs."""
    conn = db.get_conn()
    rows = conn.execute(
        """
        SELECT bet_type, probability_bucket, predicted_avg, actual_hit_rate,
               sample_size, correction_factor, updated_at
        FROM calibration_curve
        ORDER BY bet_type, probability_bucket
        """
    ).fetchall()
    conn.close()

    by_market: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        d = dict(r)
        key = d["bet_type"] if d["bet_type"] is not None else ""
        by_market.setdefault(key, []).append(
            {
                "probability_bucket": d["probability_bucket"],
                "predicted_avg": d["predicted_avg"],
                "actual_hit_rate": d["actual_hit_rate"],
                "sample_size": d["sample_size"],
                "correction_factor": d["correction_factor"],
                "updated_at": d["updated_at"],
            }
        )

    return {
        "bet_types": sorted(by_market.keys(), key=lambda x: (x != "", x)),
        "curves": by_market,
        "min_sample_for_correction": MIN_SAMPLE_FOR_CORRECTION,
    }
