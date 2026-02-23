"""
Empirical calibration curve for probability correction.

After each tournament, computes prediction accuracy by probability bucket
and builds correction factors. When we have enough data (50+ predictions
per bucket), these corrections are applied to future probabilities.
"""

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


def update_calibration_curve():
    """
    Recompute calibration curve from all prediction_log data.
    Groups predictions by probability bucket, compares predicted vs actual,
    stores correction factors.
    """
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT model_prob, actual_outcome FROM prediction_log "
        "WHERE model_prob IS NOT NULL AND actual_outcome IS NOT NULL"
    ).fetchall()
    conn.close()

    if not rows:
        return {}

    results = {}
    for low, high, label in PROBABILITY_BUCKETS:
        in_bucket = [r for r in rows if low <= r["model_prob"] < high]
        if not in_bucket:
            continue

        predicted_avg = sum(r["model_prob"] for r in in_bucket) / len(in_bucket)
        actual_rate = sum(r["actual_outcome"] for r in in_bucket) / len(in_bucket)
        sample_size = len(in_bucket)

        if predicted_avg > 0:
            correction_factor = actual_rate / predicted_avg
        else:
            correction_factor = 1.0

        results[label] = {
            "predicted_avg": round(predicted_avg, 6),
            "actual_hit_rate": round(actual_rate, 6),
            "sample_size": sample_size,
            "correction_factor": round(correction_factor, 4),
        }

        conn = db.get_conn()
        conn.execute("DELETE FROM calibration_curve WHERE probability_bucket = ?", (label,))
        conn.execute(
            "INSERT INTO calibration_curve (probability_bucket, predicted_avg, actual_hit_rate, sample_size, correction_factor) "
            "VALUES (?, ?, ?, ?, ?)",
            (label, predicted_avg, actual_rate, sample_size, correction_factor),
        )
        conn.commit()
        conn.close()

    return results


def get_calibration_correction(probability: float) -> float:
    """
    Get correction factor for a given probability.
    Returns 1.0 (no correction) if sample size < MIN_SAMPLE_FOR_CORRECTION.
    """
    conn = db.get_conn()
    for low, high, label in PROBABILITY_BUCKETS:
        if low <= probability < high:
            row = conn.execute(
                "SELECT correction_factor, sample_size FROM calibration_curve "
                "WHERE probability_bucket = ?", (label,)
            ).fetchone()
            conn.close()
            if row and row["sample_size"] >= MIN_SAMPLE_FOR_CORRECTION:
                return row["correction_factor"]
            return 1.0
    conn.close()
    return 1.0
