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
from src.strategy_resolution import build_pipeline_strategy_config

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
        mode: str = "full",
        include_weather: bool = False,
        include_post_review: bool = False,
        include_methodology: bool = True,
        strategy_source: str = "registry",
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

        # Resolve output_dir to project output so app can read card regardless of cwd
        if not os.path.isabs(output_dir):
            _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            output_dir = os.path.join(_project_root, output_dir)

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
        print(f"  Field size: {len(field_keys)} players")

        if field_keys:
            print("  Fetching DG skill ratings & rankings...")
            self._sync_skill_data(tid, field_keys)

        # Step 6: Compute rolling stats
        print("  Computing rolling stats...")
        rolling = self._compute_rolling_stats(tid, field_keys, course_num)
        result["rolling_stats"] = rolling

        # Step 7: Load course profile
        print("  Loading course profile...")
        profile = self._load_course_profile(course_name, sync_result.get("decompositions_raw"))

        # Step 7a: Resolve strategy from model registry (same chain as run_predictions CLI)
        if strategy_source == "registry":
            resolved = self._resolve_strategy()
            if resolved:
                strategy, meta = resolved
                self.strategy_config = build_pipeline_strategy_config(strategy)
                result["strategy_meta"] = meta
                logger.info("Strategy resolved: %s (source: %s)", meta.get("strategy_name"), meta.get("strategy_source"))

        # Step 8: Run composite model
        print("  Running composite model...")
        weights = self._get_weights(course_num)
        result["pipeline_weights"] = weights
        composite = self._run_composite(tid, weights, course_name)
        result["composite_results"] = composite

        if not composite:
            result["status"] = "error"
            result["errors"].append("No players scored")
            return result

        print(f"    → {len(composite)} players scored")

        # Step 8a: Weather adjustments (optional)
        if include_weather:
            weather_adj = self._compute_weather(tid, course_name)
            if weather_adj:
                result["weather_adjustments"] = weather_adj

        # Step 9: AI pre-tournament analysis (if enabled)
        ai_pre_analysis = None
        ai_decisions = None

        if enable_ai and self._is_ai_available():
            print("  Running AI pre-tournament analysis...")
            ai_pre_analysis = self._run_ai_pre_analysis(
                tid, composite, profile, tournament_name, course_name
            )
            if ai_pre_analysis:
                composite = self._apply_ai_adjustments(composite, ai_pre_analysis)
                result["composite_results"] = composite
                print("    → AI adjustments applied")

        result["ai_pre_analysis"] = ai_pre_analysis

        # Step 10: Fetch odds and compute value bets
        print("  Fetching odds & computing value bets...")
        all_odds = {}
        value_bets = {}
        if mode in ("full", "placements-only"):
            all_odds = self._fetch_odds()
            value_bets = self._compute_value_bets(composite, all_odds, tid)
        result["value_bets"] = value_bets
        total_vb = sum(len(v) for v in value_bets.values()) if isinstance(value_bets, dict) else 0
        value_count_before = sum(
            1 for bets in value_bets.values()
            for b in bets if b.get("is_value")
        ) if isinstance(value_bets, dict) else 0
        print(f"    → {total_vb} odds entries, {value_count_before} value bets found")

        # Step 10a: Apply portfolio diversification rules
        from src.portfolio import enforce_diversification
        value_bets = enforce_diversification(value_bets)
        result["value_bets"] = value_bets
        value_count_after = sum(
            1 for bets in value_bets.values()
            for b in bets if b.get("is_value")
        )
        if value_count_after < value_count_before:
            print(f"    → {value_count_after} value bets after diversification (was {value_count_before})")

        # Step 10b: Matchups and 3-ball (live focus: plus-ROI areas)
        matchup_bets = []
        if mode in ("full", "matchups-only", "round-matchups"):
            matchup_bets = self._fetch_matchup_value_bets(composite, tid)
            if mode == "round-matchups":
                matchup_bets = [b for b in matchup_bets if b.get("market_type") == "round_matchups"]
            if matchup_bets:
                print(f"    → {len(matchup_bets)} matchup value plays")
        result["matchup_bets"] = matchup_bets
        if mode in ("full", "matchups-only"):
            threeball_bets = self._fetch_3ball_value_bets(composite, tid)
            if threeball_bets:
                value_bets.setdefault("3ball", []).extend(threeball_bets)
                print(f"    → {len(threeball_bets)} 3-ball value plays")
        result["value_bets"] = value_bets

        # Step 10c: Run quality check before logging anything
        from src.value import compute_run_quality

        run_quality = compute_run_quality(value_bets)
        result["run_quality"] = run_quality
        picks_allowed = run_quality["pass"]

        if not picks_allowed:
            print(f"  ⚠️  Run quality check FAILED: {', '.join(run_quality['issues'])}")
            print("      Picks will NOT be logged to avoid corrupting track record.")
            print(f"      Quality score: {run_quality['score']}")
        else:
            print(f"  ✓ Run quality check passed (score: {run_quality['score']})")

        # Step 11: AI betting decisions disabled — all bet selection is now quantitative.
        # See src/prompts.py::betting_decision for rationale.
        ai_decisions = None
        result["ai_decisions"] = ai_decisions

        # Step 12: Log predictions for calibration (skipped if quality check fails)
        if value_bets and picks_allowed:
            self._log_predictions(tid, value_bets)
        elif value_bets and not picks_allowed:
            logger.warning("Skipping prediction logging — run quality check failed")
        if matchup_bets and picks_allowed:
            self._log_matchup_predictions(tid, matchup_bets)

        # Step 13: Generate card
        print("  Generating betting card...")
        card_path = self._generate_card(
            tournament_name, course_name, composite,
            value_bets, output_dir,
            ai_pre_analysis, ai_decisions,
            matchup_bets=matchup_bets,
            mode=mode,
        )
        result["card_filepath"] = card_path

        # Step 13a: Generate methodology document (companion to card; default on)
        if include_methodology and card_path:
            meth_ctx = self._build_methodology_ctx(
                tournament_name=tournament_name,
                course_name=course_name,
                tid=tid,
                composite=composite,
                value_bets=value_bets,
                profile=profile,
                ai_pre_analysis=ai_pre_analysis,
                matchup_bets=matchup_bets,
                weights=weights,
                result=result,
            )
            meth_path = self._generate_methodology(meth_ctx, output_dir)
            result["methodology_filepath"] = meth_path

        # Step 14: Post-tournament review for prior events (optional)
        if include_post_review:
            self._run_post_review(tid, tournament_name, course_name, enable_ai)

        # Step 15: Log run metadata
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

    def _harvest_intel(self, field_keys: list[str],
                       tournament_id: int = None) -> dict | None:
        """Harvest intel for field players (non-blocking, best-effort)."""
        try:
            from workers.intel_harvester import harvest_for_field
            from src.player_normalizer import display_name

            player_names = [display_name(pk) for pk in field_keys[:30]]
            summary = harvest_for_field(
                player_names,
                use_ai=False,
                tournament_id=tournament_id,
            )
            logger.info("Intel harvest: %d items stored", summary.get("items_stored", 0))
            return summary
        except Exception as e:
            logger.warning("Intel harvest failed (non-fatal): %s", e)
            return None

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
        """Merge DB/course weights with resolved strategy blend (matches run_predictions)."""
        base = db.get_weights_for_course(course_num)
        if self.strategy_config and "weights" in self.strategy_config:
            merged = dict(base)
            merged.update(self.strategy_config["weights"])
            return merged
        return base

    def _run_composite(self, tournament_id: int, weights: dict,
                        course_name: str = None) -> list[dict]:
        """Run the composite model; weights already include strategy blend from _get_weights."""
        from src.models.composite import compute_composite
        return compute_composite(
            tournament_id,
            weights,
            course_name=course_name,
            strategy_config=None,
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
        from src.confidence import get_field_strength
        from src.odds import get_best_odds
        from src.value import find_value_bets

        ev_threshold = None
        allowed = None
        if self.strategy_config:
            ev_threshold = self.strategy_config.get("ev_threshold")
            allowed = self.strategy_config.get("allowed_markets")

        value_bets = {}
        _fstr = get_field_strength(composite)
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
            if allowed is not None and bt not in allowed:
                continue
            vb = find_value_bets(
                composite,
                best,
                bet_type=bt,
                tournament_id=tid,
                field_strength=_fstr,
                ev_threshold=ev_threshold,
            )
            value_bets[bt] = vb
        return value_bets

    def _fetch_matchup_value_bets(self, composite, tid) -> list:
        """Fetch tournament and round matchup odds and return value bets (live focus).
        Only includes matchups that have odds at the preferred book (e.g. bet365)."""
        try:
            from src.datagolf import fetch_matchup_odds
            from src.matchup_value import find_matchup_value_bets
            from src.odds import get_preferred_book
            from src import config

            ev_threshold = self.strategy_config.get("matchup_ev_threshold") if self.strategy_config else None
            if ev_threshold is None:
                ev_threshold = self.strategy_config.get("ev_threshold") if self.strategy_config else None
            if ev_threshold is None:
                ev_threshold = getattr(config, "MATCHUP_EV_THRESHOLD", 0.05)
            required_book = get_preferred_book()
            aggregated = []
            for market_key, label in [("tournament_matchups", "72-hole"), ("round_matchups", "round")]:
                try:
                    odds = fetch_matchup_odds(market=market_key, tour=self.tour)
                    if not odds:
                        continue
                    bets = find_matchup_value_bets(
                        composite, odds, ev_threshold=ev_threshold, tournament_id=tid,
                        required_book=required_book, market_type=market_key,
                    )
                    for b in bets:
                        b["market_type"] = market_key
                    aggregated.extend(bets)
                except Exception as e:
                    logger.warning("Matchup fetch %s: %s", label, e)
            return sorted(aggregated, key=lambda x: x.get("ev", 0), reverse=True)
        except Exception as e:
            logger.warning("Matchup value bets failed: %s", e)
            return []

    def _fetch_3ball_value_bets(self, composite, tid) -> list:
        """Fetch 3-ball odds and return value bets (live focus; runs regardless of feature flag).
        Only includes groups where the preferred book (e.g. bet365) has odds for all three players."""
        try:
            from src.datagolf import fetch_matchup_odds
            from src.value import find_3ball_value_bets
            from src.odds import get_preferred_book

            odds = fetch_matchup_odds(market="3_balls", tour=self.tour)
            if not odds:
                return []
            return find_3ball_value_bets(
                composite, odds, tournament_id=tid, enable_for_live=True,
                required_book=get_preferred_book(),
            )
        except Exception as e:
            logger.warning("3-ball value bets failed: %s", e)
            return []

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

    def _log_matchup_predictions(self, tid, matchup_bets):
        """Log matchup predictions for calibration tracking."""
        try:
            from src.learning import log_matchup_predictions_for_tournament
            log_matchup_predictions_for_tournament(tid, matchup_bets)
        except Exception as e:
            logger.warning(f"Matchup prediction logging error: {e}")

    def _build_methodology_ctx(
        self,
        *,
        tournament_name: str,
        course_name: str | None,
        tid: int,
        composite: list,
        value_bets: dict,
        profile,
        ai_pre_analysis,
        matchup_bets: list | None,
        weights: dict,
        result: dict,
    ) -> dict:
        """Context dict for src.methodology.generate_methodology (same shape as run_predictions)."""
        from src import config as src_config

        meta = result.get("strategy_meta") or {}
        return {
            "tournament_name": tournament_name,
            "course_name": course_name or "Unknown",
            "event_id": str(tid),
            "composite_results": composite,
            "value_bets": value_bets or {},
            "weights": weights or {"course_fit": 0.45, "form": 0.45, "momentum": 0.10},
            "profile": profile,
            "ai_pre_analysis": ai_pre_analysis,
            "matchup_bets": matchup_bets or [],
            "metric_counts": result.get("metric_counts") or {},
            "rounds_by_year": result.get("rounds_by_year") or {},
            "total_rounds": result.get("total_rounds"),
            "model_version": getattr(src_config, "MODEL_VERSION", "4.2"),
            "strategy": {
                "runtime_settings": meta.get("runtime_settings")
                or {"blend_weights": weights or {}},
            },
        }

    def _generate_card(self, tournament_name, course_name, composite,
                        value_bets, output_dir, ai_pre_analysis, ai_decisions,
                        matchup_bets: list = None, mode: str = "full") -> str | None:
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
                matchup_bets=matchup_bets or [],
                mode=mode,
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

    def _resolve_strategy(self) -> tuple | None:
        """Resolve strategy using shared registry chain (live -> research -> active -> default)."""
        try:
            from src.strategy_resolution import resolve_runtime_strategy

            strategy, meta = resolve_runtime_strategy("global")
            return strategy, meta
        except Exception:
            logger.warning("Strategy resolution failed, using defaults", exc_info=True)
            return None

    def _compute_weather(self, tournament_id: int, course_name: str) -> dict | None:
        """Fetch forecast and compute weather adjustments."""
        try:
            from src.models.weather import fetch_forecast, compute_weather_adjustments
            forecast = fetch_forecast(course_name)
            if forecast:
                return compute_weather_adjustments(forecast)
        except Exception:
            logger.warning("Weather adjustments failed (non-fatal)", exc_info=True)
        return None

    def _generate_methodology(self, ctx: dict, output_dir: str) -> str | None:
        """Generate methodology document alongside the betting card."""
        try:
            from src.methodology import generate_methodology

            return generate_methodology(ctx, output_dir=output_dir)
        except Exception:
            logger.warning("Methodology generation failed (non-fatal)", exc_info=True)
            return None

    def _run_post_review(self, tournament_id: int, tournament_name: str,
                          course_name: str, enable_ai: bool):
        """Run post-tournament review and learning for completed events."""
        try:
            from src.learning import run_post_tournament_learning
            run_post_tournament_learning(tournament_id)
            if enable_ai and self._is_ai_available():
                from src.ai_brain import post_tournament_review
                post_tournament_review(
                    tournament_id=tournament_id,
                    tournament_name=tournament_name,
                    course_name=course_name or "",
                )
        except Exception:
            logger.warning("Post-tournament review failed (non-fatal)", exc_info=True)
