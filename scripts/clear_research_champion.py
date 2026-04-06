"""Clear the research champion so the model falls back to the default strategy.

Run on the server after deploying:
    python scripts/clear_research_champion.py

This sets is_current = 0 on all research_model_registry rows so that
resolve_runtime_strategy falls through to the default StrategyConfig
(40/40/20 weights, 5% EV threshold) -- the baseline that produced
the 39-22-7 winning record.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import db


def main() -> None:
    db.ensure_initialized()
    conn = db.get_conn()

    rows = conn.execute(
        "SELECT id, scope, source, is_current, strategy_config_json FROM research_model_registry WHERE is_current = 1"
    ).fetchall()

    if not rows:
        print("No active research champion found. Strategy already uses default.")
        return

    for row in rows:
        print(f"Clearing research champion id={row['id']} scope={row['scope']} source={row['source']}")

    conn.execute("UPDATE research_model_registry SET is_current = 0 WHERE is_current = 1")

    live_rows = conn.execute(
        "SELECT id, is_current FROM live_model_registry WHERE is_current = 1"
    ).fetchall()
    if live_rows:
        print(f"Also clearing {len(live_rows)} live_model_registry row(s).")
        conn.execute("UPDATE live_model_registry SET is_current = 0 WHERE is_current = 1")

    conn.commit()
    print("Done. Strategy will now resolve to default StrategyConfig (40/40/20, 5% EV).")


if __name__ == "__main__":
    main()
