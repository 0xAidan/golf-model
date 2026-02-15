"""
Unified Golf Model Service

Single orchestration layer used by ALL entry points (CLI, FastAPI, backtester).
Ensures consistent model execution regardless of how it's called.
"""

import os
import time
import logging
from datetime import datetime
from typing import Optional

from src import db
from src.player_normalizer import normalize_name, display_name

logger = logging.getLogger("golf_model_service")


class GolfModelService:
    """Orchestrates the full prediction pipeline."""

    def __init__(self, tour: str = "pga", strategy_config: dict = None):
        self.tour = tour
        self.strategy_config = strategy_config or {}
        db.ensure_initialized()

    def run_analysis(
        self,
        tournament_name: str = None,
        course_name: str = None,
        event_id: str = None,
        course_num: int = None,
        enable_ai: bool = True,
        enable_backfill: bool = True,
        backfill_years: list[int] = None,
        output_dir: str = "output",
    ) -> dict:
        """
        Run the complete prediction pipeline.

        Returns a dict with all results:
          - tournament_id, event_name, course_name
          - composite_results, value_bets
          - ai_pre_analysis, ai_decisions
          - card_filepath
          - run_metadata
        """
        run_start = datetime.now()
        result = {
            "status": "running",
            "errors": [],
            "warnings": [],
        }

        # Step 1: Detect current event if not specified
        event_info = None
        if not tournament_name:
            event_info = self._detect_event()
            if event_info:
                tournament_name = event_info.get("event_name", "Unknown")
                event_id = str(event_info.get("event_id", ""))
                course_name = course_name or event_info.get("course", "").split(";")[0].strip()
                course_keys = event_info.get("course_key", "").split(";")
                for ck in course_keys:
                    try:
                        course_num = course_num or int(ck)
                    except ValueError:
                        pass
            else:
                result["status"] = "error"
                result["errors"].append("Could not detect current event and no tournament specified")
                return result

        result["event_name"] = tournament_name
        result["course_name"] = course_name

        # Step 2: Create/get tournament
        tid = db.get_or_create_tournament(tournament_name, course_name)
        result["tournament_id"] = tid

        # Step 3: Backfill round data if needed
        if enable_backfill:
            self._backfill_rounds(backfill_years)

        # Step 4: Sync DG predictions, decompositions, field
        sync_result = self._sync_tournament_data(tid)
        result["sync"] = sync_result

        # Step 5: Fetch DG skill ratings, rankings, approach skill
        field_keys = db.get_all_players(tid)
        result["field_size"] = len(field_keys)

        if field_keys:
            self._sync_skill_data(tid, field_keys)

        # Step 6: Compute rolling stats
        rolling = self._compute_rolling_stats(tid, field_keys, course_num)
        result["rolling_stats"] = rolling

        # Step 7: Load course profile
        profile = self._load_course_profile(course_name, sync_result.get("decompositions_raw"))

        # Step 8: Run composite model
        weights = self._get_weights(course_num)
        composite = self._run_composite(tid, weights, course_name)
        result["composite_results"] = composite

        if not composite:
            result["status"] = "error"
            result["errors"].append("No players scored")
            return result

        # Step 9: AI pre-tournament analysis (if enabled)
        ai_pre_analysis = None
        ai_decisions = None

        if enable_ai and self._is_ai_available():
            ai_pre_analysis = self._run_ai_pre_analysis(
                tid, composite, profile, tournament_name, course_name
            )
            if ai_pre_analysis:
                composite = self._apply_ai_adjustments(composite, ai_pre_analysis)
                result["composite_results"] = composite

        result["ai_pre_analysis"] = ai_pre_analysis

        # Step 10: Fetch odds and compute value bets
        all_odds = self._fetch_odds()
        value_bets = self._compute_value_bets(composite, all_odds, tid)
        result["value_bets"] = value_bets

        # Step 11: AI betting decisions
        if enable_ai and ai_pre_analysis and self._is_ai_available() and value_bets:
            ai_decisions = self._run_ai_betting_decisions(
                tid, value_bets, ai_pre_analysis, composite,
                tournament_name, course_name
            )
            if ai_decisions:
                self._log_ai_picks(tid, ai_decisions, composite)

        result["ai_decisions"] = ai_decisions

        # Step 12: Log predictions for calibration
        if value_bets:
            self._log_predictions(tid, value_bets)

        # Step 13: Generate card
        card_path = self._generate_card(
            tournament_name, course_name, composite,
            value_bets, output_dir,
            ai_pre_analysis, ai_decisions
        )
        result["card_filepath"] = card_path

        # Step 14: Log run metadata
        run_end = datetime.now()
        result["status"] = "complete"
        result["run_duration_seconds"] = (run_end - run_start).total_seconds()

        self._log_run(tid, result)
        return result

    # ── Internal Steps ──────────────────────────────────────────

    def _detect_event(self) -> dict | None:
        """Detect current/upcoming PGA event from DG schedule."""
        try:
            from src.datagolf import get_current_event_info
            return get_current_event_info(self.tour)
        except Exception as e:
            logger.warning(f"Could not detect event: {e}")
            return None

    def _backfill_rounds(self, years: list[int] = None):
        """Ensure round data exists for required years."""
        from src.datagolf import fetch_historical_rounds, _parse_rounds_response

        if years is None:
            years = [2024, 2025, 2026]

        status = db.get_rounds_backfill_status()
        for year in years:
            found = any(r["tour"] == self.tour and r["year"] == year for r in status)
            if not found:
                try:
                    logger.info(f"Backfilling {self.tour.upper()} {year}...")
                    raw = fetch_historical_rounds(tour=self.tour, event_id="all", year=year)
                    rows = _parse_rounds_response(raw, self.tour, year)
                    db.store_rounds(rows)
                    time.sleep(2)
                except Exception as e:
                    logger.warning(f"Backfill error for {year}: {e}")

    def _sync_tournament_data(self, tournament_id: int) -> dict:
        """Sync predictions, decompositions, field from DG."""
        try:
            from src.datagolf import sync_tournament
            return sync_tournament(tournament_id, tour=self.tour)
        except Exception as e:
            logger.warning(f"Sync error: {e}")
            return {"errors": [str(e)]}

    def _sync_skill_data(self, tournament_id: int, field_keys: list[str]):
        """Fetch and store DG skill ratings, rankings, approach skill."""
        from src.datagolf import (
            store_skill_ratings_as_metrics,
            store_rankings_as_metrics,
            store_approach_skill_as_metrics,
        )

        for label, func in [
            ("skill ratings", store_skill_ratings_as_metrics),
            ("rankings", store_rankings_as_metrics),
            ("approach skill", store_approach_skill_as_metrics),
        ]:
            try:
                time.sleep(2)
                func(tournament_id, field_keys)
            except Exception as e:
                logger.warning(f"{label} error: {e}")

    def _compute_rolling_stats(self, tournament_id: int,
                                field_keys: list[str],
                                course_num: int = None) -> dict:
        """Compute rolling SG stats for the field."""
        try:
            from src.rolling_stats import compute_rolling_metrics
            return compute_rolling_metrics(tournament_id, field_keys, course_num=course_num)
        except Exception as e:
            logger.warning(f"Rolling stats error: {e}")
            return {"error": str(e)}

    def _load_course_profile(self, course_name: str,
                              decomps_raw=None) -> dict | None:
        """Load or auto-generate course profile."""
        if not course_name:
            return None

        try:
            from src.course_profile import (
                load_course_profile,
                generate_profile_from_decompositions,
            )
            profile = load_course_profile(course_name)
            if profile:
                return profile

            if decomps_raw:
                return generate_profile_from_decompositions(decomps_raw)
        except Exception as e:
            logger.warning(f"Course profile error: {e}")
        return None

    def _get_weights(self, course_num: int = None) -> dict:
        """Get model weights, optionally blended with course-specific weights."""
        if self.strategy_config and "weights" in self.strategy_config:
            return self.strategy_config["weights"]
        return db.get_weights_for_course(course_num)

    def _run_composite(self, tournament_id: int, weights: dict,
                        course_name: str = None) -> list[dict]:
        """Run the composite model."""
        from src.models.composite import compute_composite
        return compute_composite(
            tournament_id, weights,
            course_name=course_name,
            strategy_config=self.strategy_config,
        )

    def _is_ai_available(self) -> bool:
        from src.ai_brain import is_ai_available
        return is_ai_available()

    def _run_ai_pre_analysis(self, tournament_id, composite, profile,
                              tournament_name, course_name) -> dict | None:
        """Run AI pre-tournament analysis."""
        try:
            from src.ai_brain import pre_tournament_analysis
            return pre_tournament_analysis(
                tournament_id=tournament_id,
                composite_results=composite,
                course_profile=profile,
                tournament_name=tournament_name,
                course_name=course_name or "",
            )
        except Exception as e:
            logger.warning(f"AI pre-analysis error: {e}")
            return None

    def _apply_ai_adjustments(self, composite, pre_analysis) -> list[dict]:
        """Apply AI adjustments to composite scores."""
        from src.ai_brain import apply_ai_adjustments
        return apply_ai_adjustments(composite, pre_analysis)

    def _fetch_odds(self) -> dict:
        """Fetch live odds from DG sportsbook tools."""
        try:
            from src.datagolf import fetch_all_outright_odds
            result = fetch_all_outright_odds(self.tour)
            return result or {}
        except Exception as e:
            logger.warning(f"Odds fetch error: {e}")
            return {}

    def _compute_value_bets(self, composite, all_odds_by_market, tid) -> dict:
        """Compute value bets for each market."""
        from src.odds import get_best_odds
        from src.value import find_value_bets

        value_bets = {}
        for market_key, odds_list in all_odds_by_market.items():
            if not odds_list:
                continue
            best = get_best_odds(odds_list)
            if market_key == "outrights":
                bt = "outright"
            elif market_key == "frl":
                bt = "frl"
            else:
                bt = market_key.replace("top_", "top")
            vb = find_value_bets(composite, best, bet_type=bt, tournament_id=tid)
            value_bets[bt] = vb
        return value_bets

    def _run_ai_betting_decisions(self, tid, value_bets, pre_analysis,
                                   composite, tournament_name, course_name) -> dict | None:
        """Get AI betting portfolio decisions."""
        try:
            from src.ai_brain import make_betting_decisions
            return make_betting_decisions(
                tournament_id=tid,
                value_bets_by_type=value_bets,
                pre_analysis=pre_analysis,
                composite_results=composite,
                tournament_name=tournament_name,
                course_name=course_name or "",
            )
        except Exception as e:
            logger.warning(f"AI betting decisions error: {e}")
            return None

    def _log_ai_picks(self, tid, ai_decisions, composite):
        """Log AI picks to the picks table for post-tournament scoring."""
        decisions_list = ai_decisions.get("decisions", [])
        if not decisions_list:
            return

        composite_lookup = {r["player_key"]: r for r in composite}
        display_to_key = {r["player_display"].lower(): r["player_key"] for r in composite}

        pick_rows = []
        for d in decisions_list:
            player_name = d.get("player", "")
            pk = normalize_name(player_name)
            if pk not in composite_lookup:
                pk = display_to_key.get(player_name.lower(), pk)

            comp_data = composite_lookup.get(pk, {})

            odds_str = str(d.get("odds", ""))
            try:
                odds_int = int(odds_str.replace("+", ""))
            except (ValueError, TypeError):
                odds_int = None

            ai_bt = d.get("bet_type", "").lower().replace(" ", "_")
            bt_map = {
                "outright": "outright", "outright_win": "outright",
                "top_5": "top5", "top5": "top5",
                "top_10": "top10", "top10": "top10",
                "top_20": "top20", "top20": "top20",
                "frl": "frl", "first_round_leader": "frl",
                "make_cut": "make_cut",
            }
            bet_type = bt_map.get(ai_bt, ai_bt)

            market_implied = None
            if odds_int is not None:
                from src.odds import american_to_implied_prob
                market_implied = american_to_implied_prob(odds_int)

            pick_rows.append({
                "tournament_id": tid,
                "bet_type": bet_type,
                "player_key": pk,
                "player_display": d.get("player", ""),
                "opponent_key": None,
                "opponent_display": None,
                "composite_score": comp_data.get("composite"),
                "course_fit_score": comp_data.get("course_fit"),
                "form_score": comp_data.get("form"),
                "momentum_score": comp_data.get("momentum"),
                "model_prob": d.get("model_ev"),
                "market_odds": odds_str,
                "market_implied_prob": market_implied,
                "ev": d.get("model_ev"),
                "confidence": d.get("confidence"),
                "reasoning": d.get("reasoning", ""),
            })

        if pick_rows:
            try:
                db.store_picks(pick_rows)
            except Exception as e:
                logger.warning(f"Error logging picks: {e}")

    def _log_predictions(self, tid, value_bets):
        """Log predictions for calibration tracking."""
        try:
            from src.learning import log_predictions_for_tournament
            log_predictions_for_tournament(tid, value_bets)
        except Exception as e:
            logger.warning(f"Prediction logging error: {e}")

    def _generate_card(self, tournament_name, course_name, composite,
                        value_bets, output_dir, ai_pre_analysis, ai_decisions) -> str | None:
        """Generate markdown betting card."""
        try:
            from src.card import generate_card
            return generate_card(
                tournament_name,
                course_name or "Unknown",
                composite,
                value_bets,
                output_dir=output_dir,
                ai_pre_analysis=ai_pre_analysis,
                ai_decisions=ai_decisions,
            )
        except Exception as e:
            logger.warning(f"Card generation error: {e}")
            return None

    def _log_run(self, tournament_id: int, result: dict):
        """Log run metadata to the runs table (if it exists)."""
        try:
            conn = db.get_conn()
            # Check if runs table exists
            table_check = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='runs'"
            ).fetchone()
            if table_check:
                import json
                conn.execute(
                    """INSERT INTO runs (tournament_id, status, result_json, created_at)
                       VALUES (?, ?, ?, datetime('now'))""",
                    (tournament_id, result.get("status", "unknown"),
                     json.dumps({
                         "field_size": result.get("field_size"),
                         "duration_s": result.get("run_duration_seconds"),
                         "errors": result.get("errors", []),
                     })),
                )
                conn.commit()
            conn.close()
        except Exception:
            pass  # Non-critical
