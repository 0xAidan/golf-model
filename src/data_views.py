"""SQL analytics views for canonical data contracts."""

from __future__ import annotations

import sqlite3

_VIEW_DDL = """
CREATE VIEW IF NOT EXISTS v_displayed_picks_graded AS
SELECT
    p.id AS pick_id,
    p.tournament_id,
    t.name AS tournament_name,
    t.year AS tournament_year,
    p.model_variant,
    p.source,
    p.bet_type,
    p.player_key,
    p.player_display,
    p.opponent_key,
    p.market_book,
    p.market_odds,
    p.model_prob,
    p.ev,
    p.confidence,
    p.created_at AS pick_created_at,
    po.id AS outcome_id,
    po.hit,
    po.model_hit,
    po.profit,
    po.actual_finish,
    po.entered_at AS graded_at
FROM picks p
LEFT JOIN tournaments t ON t.id = p.tournament_id
LEFT JOIN pick_outcomes po ON po.pick_id = p.id
WHERE p.source IN ('cockpit', 'ui_display', 'lab', 'ui_candidate');

CREATE VIEW IF NOT EXISTS v_tournament_data_health AS
SELECT
    t.id AS tournament_id,
    t.name,
    t.year,
    t.date,
    (SELECT COUNT(*) FROM picks px WHERE px.tournament_id = t.id) AS pick_count,
    (SELECT COUNT(*) FROM pick_outcomes po
     JOIN picks pk ON pk.id = po.pick_id
     WHERE pk.tournament_id = t.id) AS graded_pick_count,
    (SELECT COUNT(*) FROM prediction_log pl WHERE pl.tournament_id = t.id) AS prediction_log_count,
    (SELECT COUNT(*) FROM results r WHERE r.tournament_id = t.id) AS results_count,
    (SELECT COUNT(*) FROM runs rn WHERE rn.tournament_id = t.id) AS run_count,
    CASE WHEN EXISTS (SELECT 1 FROM picks px WHERE px.tournament_id = t.id) THEN 1 ELSE 0 END AS has_picks,
    CASE WHEN EXISTS (SELECT 1 FROM prediction_log pl WHERE pl.tournament_id = t.id) THEN 1 ELSE 0 END AS has_prediction_log,
    CASE WHEN EXISTS (SELECT 1 FROM results r WHERE r.tournament_id = t.id) THEN 1 ELSE 0 END AS has_results
FROM tournaments t;

CREATE VIEW IF NOT EXISTS v_2026_monthly_coverage AS
SELECT
    strftime('%Y-%m', t.date) AS month,
    COUNT(DISTINCT t.id) AS tournaments,
    (SELECT COUNT(*) FROM picks p WHERE p.tournament_id = t.id) AS picks,
    (SELECT COUNT(*) FROM prediction_log pl WHERE pl.tournament_id = t.id) AS prediction_log_rows
FROM tournaments t
WHERE t.year = 2026
GROUP BY month
ORDER BY month;
"""


def ensure_analytics_views(conn: sqlite3.Connection | None = None) -> None:
    """Create or refresh analytics views (idempotent)."""
    close = False
    if conn is None:
        from src import db

        db.ensure_initialized()
        conn = db.get_conn()
        close = True
    try:
        conn.executescript(_VIEW_DDL)
        conn.commit()
    finally:
        if close:
            conn.close()
