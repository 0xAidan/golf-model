"""SQL analytics views for canonical data contracts."""

from __future__ import annotations

import sqlite3

_VIEW_DDL = """
CREATE VIEW IF NOT EXISTS v_pick_analytics AS
SELECT
    pl.pick_key,
    pl.event_id,
    t.name AS tournament_name,
    COALESCE(pl.year, t.year) AS year,
    t.date AS tournament_date,
    pl.phase,
    pl.section,
    pl.lane,
    pl.lifecycle,
    pl.bet_type,
    pl.market_family,
    pl.book,
    pl.odds,
    pl.ev,
    pl.model_prob,
    pl.implied_prob,
    pl.is_value,
    pl.player_key,
    pl.player_display,
    pl.opponent_key,
    pl.opponent_display,
    pl.model_variant,
    pl.model_config_hash,
    pl.source_origin,
    pl.snapshot_id,
    pl.generated_at,
    po.id AS outcome_id,
    po.pick_id,
    po.grading_authority,
    po.outcome_locked,
    CASE
        WHEN po.hit = 1 THEN 'win'
        WHEN po.hit = 0 AND COALESCE(po.profit, 0) = 0 AND po.id IS NOT NULL THEN 'push'
        WHEN po.hit = 0 AND po.id IS NOT NULL THEN 'loss'
        ELSE 'ungraded'
    END AS outcome,
    po.hit,
    po.model_hit,
    po.profit,
    po.actual_finish,
    po.entered_at AS graded_at
FROM pick_ledger pl
LEFT JOIN tournaments t ON t.id = pl.tournament_id
LEFT JOIN pick_outcomes po ON po.pick_key = pl.pick_key
WHERE pl.lifecycle != 'pit_reconstructed'
  AND COALESCE(pl.source_origin, '') != 'pit_reconstructed';

CREATE VIEW IF NOT EXISTS v_displayed_picks_graded AS
SELECT
    COALESCE(p.id, po.pick_id) AS pick_id,
    COALESCE(p.tournament_id, pl.tournament_id) AS tournament_id,
    t.name AS tournament_name,
    t.year AS tournament_year,
    COALESCE(p.model_variant, pl.model_variant) AS model_variant,
    COALESCE(p.source, pl.lane) AS source,
    COALESCE(p.bet_type, pl.bet_type) AS bet_type,
    COALESCE(p.player_key, pl.player_key) AS player_key,
    COALESCE(p.player_display, pl.player_display) AS player_display,
    COALESCE(p.opponent_key, pl.opponent_key) AS opponent_key,
    COALESCE(p.market_book, pl.book) AS market_book,
    COALESCE(p.market_odds, pl.odds) AS market_odds,
    COALESCE(p.model_prob, pl.model_prob) AS model_prob,
    COALESCE(p.ev, pl.ev) AS ev,
    p.confidence,
    COALESCE(p.created_at, pl.generated_at) AS pick_created_at,
    po.id AS outcome_id,
    po.pick_key,
    po.hit,
    po.model_hit,
    po.profit,
    po.actual_finish,
    po.grading_authority,
    po.outcome_locked,
    po.entered_at AS graded_at
FROM pick_ledger pl
LEFT JOIN pick_outcomes po ON po.pick_key = pl.pick_key
LEFT JOIN picks p ON p.id = po.pick_id
LEFT JOIN tournaments t ON t.id = COALESCE(p.tournament_id, pl.tournament_id)
WHERE pl.lifecycle IN ('displayed', 'frozen_pre_teeoff', 'graded', 'recovered')
   OR p.source IN ('cockpit', 'ui_display', 'lab', 'ui_candidate');

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
    (SELECT COUNT(*) FROM pick_ledger plx WHERE plx.tournament_id = t.id) AS ledger_pick_count,
    (SELECT COUNT(*) FROM prediction_log pl WHERE pl.tournament_id = t.id) AS prediction_log_count,
    (SELECT COUNT(*) FROM results r WHERE r.tournament_id = t.id) AS results_count,
    (SELECT COUNT(*) FROM runs rn WHERE rn.tournament_id = t.id) AS run_count,
    CASE WHEN EXISTS (SELECT 1 FROM picks px WHERE px.tournament_id = t.id) THEN 1 ELSE 0 END AS has_picks,
    CASE WHEN EXISTS (SELECT 1 FROM pick_ledger plx WHERE plx.tournament_id = t.id) THEN 1 ELSE 0 END AS has_ledger,
    CASE WHEN EXISTS (SELECT 1 FROM prediction_log pl WHERE pl.tournament_id = t.id) THEN 1 ELSE 0 END AS has_prediction_log,
    CASE WHEN EXISTS (SELECT 1 FROM results r WHERE r.tournament_id = t.id) THEN 1 ELSE 0 END AS has_results
FROM tournaments t;

CREATE VIEW IF NOT EXISTS v_2026_monthly_coverage AS
SELECT
    strftime('%Y-%m', t.date) AS month,
    COUNT(DISTINCT t.id) AS tournaments,
    (SELECT COUNT(*) FROM picks p WHERE p.tournament_id = t.id) AS picks,
    (SELECT COUNT(*) FROM pick_ledger pl WHERE pl.tournament_id = t.id) AS ledger_picks,
    (SELECT COUNT(*) FROM prediction_log plg WHERE plg.tournament_id = t.id) AS prediction_log_rows
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
