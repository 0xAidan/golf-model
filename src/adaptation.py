"""
Market performance tracking and graduated adaptation.

Tracks wins, losses, and ROI by market type with rolling windows.
Provides graduated response: raise EV thresholds, reduce stakes,
or suppress markets based on rolling performance.
"""

from src import db


def compute_roi_pct(wagered: float, returned: float) -> float | None:
    """Compute ROI percentage. Returns None if no wagers."""
    if wagered is None or wagered <= 0:
        return None
    return round((returned - wagered) / wagered * 100.0, 2)
