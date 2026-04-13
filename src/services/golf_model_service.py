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
from src.field_selection import filter_rows_to_field
from src.player_normalizer import normalize_name, display_name
from src.run_provenance import write_run_provenance
from src.strategy_resolution import build_pipeline_strategy_config

logger = logging.getLogger("golf_model_service")

MAJOR_EVENT_NAMES = (
    "masters",
    "pga championship",
    "u.s. open",
    "us open",
    "the open",
    "open championship",
)


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
        apply_ai_adjustments: bool = True,
        strategy_meta_override: dict | None = None,
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
        result["course_num"] = course_num

        # Step 2: Create/get tournament
        tid = db.get_or_create_tournament(tournament_name, course_name)
        result["tournament_id"] = tid

        # Step 3: Backfill round data if needed
        if enable_backfill:
            self._backfill_rounds(backfill_years, tournament_name=tournament_name)

        # Step 4: Sync DG predictions, decompositions, field
        sync_result = self._sync_tournament_data(tid, event_id=event_id)
        result["sync"] = sync_result
        result["event_id"] = event_id

        # Step 5: Resolve strict verified field keys for this event
        field_keys, field_source = self._resolve_field_keys(tid, sync_result)
        result["field_size"] = len(field_keys)
        result["field_source"] = field_source
        print(f"  Field size: {len(field_keys)} players")

        if field_keys:
            print("  Fetching DG skill ratings & rankings...")
            self._sync_skill_data(tid, field_keys)

        field_validation = self._validate_field_data(
            tid,
            tournament_name,
            field_keys,
            field_source=field_source,
            expected_event_id=event_id,
        )
        result["field_validation"] = field_validation
        result["eligibility"] = {
            "verified": bool(field_validation.get("strict_field_verified")),
            "field_source": field_source,
            "field_event_id": str(event_id or ""),
            "field_player_count": len(field_keys),
            "failed_invariants": field_validation.get("failed_invariants", []),
            "summary": field_validation.get("summary"),
        }

        if not field_validation.get("strict_field_verified"):
            result["status"] = "error"
            result["verification_error"] = self._build_field_verification_error(
                event_id=event_id,
                field_source=field_source,
                failed_invariants=field_validation.get("failed_invariants", []),
            )
            result["errors"].append(result["verification_error"]["summary"])
            return result

        if field_validation.get("has_cross_tour_field_risk"):
            warning = (
                "Field data coverage warning: "
                f"{len(field_validation.get('players_with_thin_rounds', []))} players with thin round history, "
                f"{len(field_validation.get('players_missing_dg_skill', []))} players missing DG skill data."
            )
            result["warnings"].append(warning)
            logger.warning(warning)

        # Step 6: Compute rolling stats
        print("  Computing rolling stats...")
        rolling = self._compute_rolling_stats(tid, field_keys, course_num)
        result["rolling_stats"] = rolling
        result["total_rounds"] = db.get_rounds_count()

        # Step 7: Load course profile
        print("  Loading course profile...")
        profile = self._load_course_profile(course_name, sync_result.get("decompositions_raw"))

        # Step 7a: Resolve strategy from model registry (same chain as run_predictions CLI)
        if strategy_source == "registry":
            resolved = self._resolve_strategy()
            if resolved:
                strategy, meta = resolved
                self.strategy_config = build_pipeline_strategy_config(strategy)
                meta = dict(meta or {})
                meta.setdefault("runtime_settings", self.strategy_config)
                result["strategy_meta"] = meta
                logger.info("Strategy resolved: %s (source: %s)", meta.get("strategy_name"), meta.get("strategy_source"))
        elif strategy_source == "config" and self.strategy_config:
            pipeline_meta = self._strategy_meta_from_pipeline(self.strategy_config)
            if strategy_meta_override:
                merged_meta = dict(strategy_meta_override)
                merged_meta.setdefault("runtime_settings", pipeline_meta.get("runtime_settings"))
                result["strategy_meta"] = merged_meta
            else:
                result["strategy_meta"] = pipeline_meta

        # Step 8: Run composite model
        print("  Running composite model...")
        weights = self._get_weights(course_num)
        result["pipeline_weights"] = weights
        composite = self._run_composite(tid, weights, course_name)
        composite, composite_field_audit = self._filter_composite_to_field(composite, field_keys)
        result["composite_results"] = composite
        field_validation.update({
            "scored_players": len(composite),
            "score_extras": composite_field_audit.get("extra_player_keys", []),
            "score_missing": composite_field_audit.get("missing_player_keys", []),
        })
        result["field_validation"] = field_validation

        if not composite:
            result["status"] = "error"
            result["verification_error"] = {
                "code": "no_players_scored_after_field_filter",
                "summary": "No players remained after strict field filtering.",
                "details": (
                    "The model ran, but no composite rows passed confirmed field eligibility. "
                    "This prevents unverified rankings from being displayed."
                ),
                "action": "Check Data Golf field-updates availability and event_id alignment, then rerun refresh.",
                "retryable": True,
            }
            result["errors"].append(result["verification_error"]["summary"])
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
                if apply_ai_adjustments:
                    composite = self._apply_ai_adjustments(composite, ai_pre_analysis)
                    composite, _ = self._filter_composite_to_field(composite, field_keys)
                    result["composite_results"] = composite
                    print("    → AI adjustments applied")
                else:
                    print("    → AI narrative only (composite scores unchanged)")

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

        # Step 10a: Matchups and 3-ball (live focus: plus-ROI areas)
        matchup_bets = []
        matchup_diagnostics = {
            "market_counts": {},
            "selection_counts": {"selected_rows": 0},
            "reason_codes": {},
            "state": "not_requested",
            "errors": [],
        }
        if mode in ("full", "matchups-only", "round-matchups"):
            matchup_bets, matchup_diagnostics = self._fetch_matchup_value_bets(composite, tid, mode=mode)
            if matchup_bets:
                print(f"    → {len(matchup_bets)} matchup value plays")
        result["matchup_bets"] = matchup_bets
        result["matchup_diagnostics"] = matchup_diagnostics
        if mode in ("full", "matchups-only"):
            threeball_bets = self._fetch_3ball_value_bets(composite, tid)
            if threeball_bets:
                value_bets.setdefault("3ball", []).extend(threeball_bets)
                print(f"    → {len(threeball_bets)} 3-ball value plays")
        result["value_bets"] = value_bets

        # Step 10b: Exposure filtering (when enabled) and diversification
        try:
            from src.feature_flags import is_enabled
            if is_enabled("exposure_caps"):
                from src.exposure import filter_by_exposure
                from src.kelly import get_bankroll_state
                state = get_bankroll_state()
                bankroll = state["balance"] if state else None
                value_bets, exp_warnings = filter_by_exposure(value_bets, bankroll=bankroll)
                for warning in exp_warnings:
                    print(f"    ⚠ {warning}")
        except Exception as exc:
            logger.warning("Exposure filtering error: %s", exc)

        from src.portfolio import enforce_diversification
        from src.confidence import get_field_strength

        field_strength = get_field_strength(composite)
        value_bets = enforce_diversification(value_bets, field_strength=field_strength)
        result["value_bets"] = value_bets
        value_count_after = sum(
            1 for bets in value_bets.values()
            for b in bets if b.get("is_value")
        )
        if value_count_after < value_count_before:
            print(
                f"    → {value_count_after} value bets after diversification "
                f"(was {value_count_before}, field={field_strength})"
            )

        # Step 10c: Run quality check before logging anything
        from src.value import compute_run_quality

        run_quality = compute_run_quality(value_bets)
        result["run_quality"] = run_quality
        placement_logging_allowed = run_quality["pass"]

        if not placement_logging_allowed:
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
        if value_bets and placement_logging_allowed:
            self._log_predictions(tid, value_bets)
        elif value_bets and not placement_logging_allowed:
            logger.warning("Skipping prediction logging — run quality check failed")
        matchup_logging_allowed = (
            (matchup_diagnostics or {}).get("state") != "pipeline_error"
            and not (matchup_diagnostics or {}).get("errors")
        )
        if matchup_bets and matchup_logging_allowed:
            self._log_matchup_predictions(tid, matchup_bets)
        elif matchup_bets and not matchup_logging_allowed:
            logger.warning("Skipping matchup logging — matchup diagnostics reported an error")

        # Step 13: Generate card
        print("  Generating betting card...")
        card_path = self._generate_card(
            tournament_name, course_name, composite,
            value_bets, output_dir,
            ai_pre_analysis, ai_decisions,
            matchup_bets=matchup_bets,
            mode=mode,
            strategy_meta=result.get("strategy_meta"),
            ai_scores_adjusted=not (enable_ai and ai_pre_analysis and not apply_ai_adjustments),
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
        result["provenance_path"] = write_run_provenance(
            event_name=tournament_name,
            output_dir=output_dir,
            strategy_meta=result.get("strategy_meta"),
            runtime_settings=self.strategy_config,
            run_quality=result.get("run_quality"),
            value_bets=result.get("value_bets"),
            matchup_diagnostics=result.get("matchup_diagnostics"),
            source="golf_model_service",
        )

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

    def _is_major_event(self, tournament_name: str | None) -> bool:
        if not tournament_name:
            return False
        normalized = tournament_name.strip().lower()
        return any(name in normalized for name in MAJOR_EVENT_NAMES)

    def _backfill_tours_for_event(self, tournament_name: str | None) -> list[str]:
        tours = [self.tour]
        if self.tour == "pga" and self._is_major_event(tournament_name):
            tours.append("alt")
        seen = set()
        ordered = []
        for tour in tours:
            if tour not in seen:
                seen.add(tour)
                ordered.append(tour)
        return ordered

    def _backfill_rounds(self, years: list[int] = None, tournament_name: str = None):
        """Ensure round data exists for required years."""
        from src.datagolf import fetch_historical_rounds, _parse_rounds_response

        if years is None:
            years = [2024, 2025, 2026]

        status = db.get_rounds_backfill_status()
        tours = self._backfill_tours_for_event(tournament_name)
        for tour in tours:
            for year in years:
                found = any(r["tour"] == tour and r["year"] == year for r in status)
                if not found:
                    try:
                        logger.info(f"Backfilling {tour.upper()} {year}...")
                        raw = fetch_historical_rounds(tour=tour, event_id="all", year=year)
                        rows = _parse_rounds_response(raw, tour, year)
                        db.store_rounds(rows)
                        time.sleep(2)
                    except Exception as e:
                        logger.warning(f"Backfill error for {tour.upper()} {year}: {e}")

    def _sync_tournament_data(self, tournament_id: int, event_id: str | None = None) -> dict:
        """Sync predictions, decompositions, field from DG."""
        try:
            from src.datagolf import sync_tournament
            return sync_tournament(tournament_id, tour=self.tour, event_id=event_id)
        except Exception as e:
            logger.warning(f"Sync error: {e}")
            return {"errors": [str(e)]}

    def _resolve_field_keys(self, tournament_id: int, sync_result: dict | None) -> tuple[list[str], str]:
        """Resolve canonical field keys with strict source priority."""
        sync_field_keys = [
            str(player_key).strip().lower()
            for player_key in (sync_result or {}).get("field_player_keys", [])
            if str(player_key).strip()
        ]
        if sync_field_keys:
            # Preserve order while deduping.
            return list(dict.fromkeys(sync_field_keys)), "datagolf_field_updates"

        db_field_keys = [
            str(player_key).strip().lower()
            for player_key in db.get_all_players(tournament_id, confirmed_field_only=True)
            if str(player_key).strip()
        ]
        if db_field_keys:
            return list(dict.fromkeys(db_field_keys)), "db_confirmed_field_cache"
        return [], "missing_confirmed_field"

    def _build_field_verification_error(
        self,
        *,
        event_id: str | None,
        field_source: str,
        failed_invariants: list[str] | None,
    ) -> dict:
        failed = failed_invariants or ["strict_field_missing"]
        if "strict_field_missing" in failed:
            summary = "Field verification failed: no confirmed tournament field available."
            details = (
                "Rankings were withheld to prevent showing players who are not confirmed in this event. "
                "This usually means Data Golf has not published field-updates for the selected event yet."
            )
            action = (
                "Wait for Data Golf field-updates to post for this event (or confirm event_id), then refresh again."
            )
            code = "field_unavailable"
            retryable = True
        else:
            summary = "Field verification failed due to event integrity mismatch."
            details = (
                "The ranking event context did not match verified field metadata, so rankings were withheld."
            )
            action = "Verify event_id/tour context and refresh once the field feed aligns."
            code = "field_integrity_mismatch"
            retryable = True

        return {
            "code": code,
            "summary": summary,
            "details": details,
            "action": action,
            "retryable": retryable,
            "observed_event_id": str(event_id or ""),
            "observed_tour": self.tour,
            "field_source": field_source,
            "failed_invariants": failed,
        }

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

    def _validate_field_data(
        self,
        tournament_id: int,
        tournament_name: str | None,
        field_keys: list[str],
        *,
        field_source: str,
        expected_event_id: str | None,
    ) -> dict:
        """Summarize whether field players have enough recent data, especially in majors."""
        thin_rounds = []
        missing_skill = []
        failed_invariants: list[str] = []

        if not field_keys:
            failed_invariants.append("strict_field_missing")
        if expected_event_id is None or not str(expected_event_id).strip():
            failed_invariants.append("event_id_missing")

        for player_key in field_keys:
            pretty_name = " ".join(part.capitalize() for part in player_key.split("_") if part)
            recent_rounds = db.get_player_recent_rounds_by_key(player_key, limit=24)
            if len(recent_rounds) < 8:
                thin_rounds.append(pretty_name)

            player_metrics = db.get_player_metrics(tournament_id, player_key)
            has_dg_skill = any(m.get("metric_category") == "dg_skill" for m in player_metrics)
            has_dg_ranking = any(m.get("metric_category") == "dg_ranking" for m in player_metrics)
            if not has_dg_skill and not has_dg_ranking:
                missing_skill.append(pretty_name)

        strict_field_verified = "strict_field_missing" not in failed_invariants
        return {
            "major_event": self._is_major_event(tournament_name),
            "cross_tour_backfill_used": "alt" in self._backfill_tours_for_event(tournament_name),
            "players_checked": len(field_keys),
            "players_with_thin_rounds": thin_rounds,
            "players_missing_dg_skill": missing_skill,
            "has_cross_tour_field_risk": bool(thin_rounds or missing_skill),
            "field_source": field_source,
            "expected_event_id": str(expected_event_id or ""),
            "strict_field_verified": strict_field_verified,
            "failed_invariants": failed_invariants,
            "summary": (
                "Field verified via confirmed event field."
                if strict_field_verified
                else "Field verification failed; rankings are withheld to preserve trust."
            ),
        }

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

    def _filter_composite_to_field(self, composite: list[dict], field_keys: list[str]) -> tuple[list[dict], dict]:
        """Drop phantom players so rankings and bets use the strict confirmed field."""
        filtered, audit = filter_rows_to_field(composite, field_keys)
        if audit.get("extra_player_keys"):
            logger.warning(
                "Removed %d non-field players from composite output",
                len(audit["extra_player_keys"]),
            )
        return filtered, audit

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

    def _fetch_matchup_value_bets(self, composite, tid, mode: str = "full") -> tuple[list, dict]:
        """Fetch matchup value bets across all available books.

        **full** and **matchups-only**: 72-hole (tournament) matchups.
        **round-matchups**: per-round H2H first, with tournament fallback when books are sparse.
        """
        try:
            from src.datagolf import fetch_matchup_odds_with_diagnostics
            from src.matchup_value import find_matchup_value_bets
            from src import config

            diagnostics = {
                "market_counts": {},
                "selection_counts": {
                    "input_rows": 0,
                    "selected_rows": 0,
                },
                "reason_codes": {},
                "adaptation_state": "normal",
                "state": "market_available_no_edges",
                "errors": [],
            }
            ev_threshold = self.strategy_config.get("matchup_ev_threshold") if self.strategy_config else None
            if ev_threshold is None:
                ev_threshold = self.strategy_config.get("ev_threshold") if self.strategy_config else None
            if ev_threshold is None:
                ev_threshold = getattr(config, "MATCHUP_EV_THRESHOLD", 0.05)
            if mode == "round-matchups":
                # Prefer true round H2H in live windows, but include tournament lines as fallback.
                markets = [("round_matchups", "round"), ("tournament_matchups", "72-hole fallback")]
            else:
                markets = [("tournament_matchups", "72-hole")]
            aggregated = []
            for market_key, label in markets:
                try:
                    odds, market_diag = fetch_matchup_odds_with_diagnostics(market=market_key, tour=self.tour)
                    diagnostics["market_counts"][market_key] = {
                        "raw_rows": len(odds),
                        "reason_code": market_diag.get("reason_code"),
                    }
                    if not odds:
                        continue
                    bets, selection_diag = find_matchup_value_bets(
                        composite, odds, ev_threshold=ev_threshold, tournament_id=tid,
                        market_type=market_key,
                        return_diagnostics=True,
                    )
                    diagnostics["selection_counts"]["input_rows"] += int(selection_diag.get("input_rows", 0))
                    diagnostics["selection_counts"]["selected_rows"] += int(selection_diag.get("selected_rows", 0))
                    diagnostics["adaptation_state"] = selection_diag.get("adaptation_state", diagnostics["adaptation_state"])
                    for reason, count in (selection_diag.get("reason_codes") or {}).items():
                        diagnostics["reason_codes"][reason] = diagnostics["reason_codes"].get(reason, 0) + int(count)
                    for b in bets:
                        b["market_type"] = market_key
                    aggregated.extend(bets)
                except Exception as e:
                    logger.warning("Matchup fetch %s: %s", label, e)
                    diagnostics["errors"].append(f"{label}: {e}")

            # Deduplicate identical lines that can appear in both markets/fallbacks.
            deduped = {}
            for bet in aggregated:
                key = (
                    bet.get("pick_key"),
                    bet.get("opponent_key"),
                    str(bet.get("book") or "").strip().lower(),
                    str(bet.get("odds")),
                    bet.get("market_type"),
                )
                current = deduped.get(key)
                if current is None or float(bet.get("ev", 0)) > float(current.get("ev", 0)):
                    deduped[key] = bet
            selected = sorted(deduped.values(), key=lambda x: x.get("ev", 0), reverse=True)
            diagnostics["selection_counts"]["selected_rows"] = len(selected)
            total_raw_rows = sum(int((entry or {}).get("raw_rows", 0)) for entry in diagnostics["market_counts"].values())
            if diagnostics["errors"]:
                diagnostics["state"] = "pipeline_error"
            elif total_raw_rows == 0:
                diagnostics["state"] = "no_market_posted_yet"
            elif not selected:
                diagnostics["state"] = "market_available_no_edges"
            else:
                diagnostics["state"] = "edges_available"
            return selected, diagnostics
        except Exception as e:
            logger.warning("Matchup value bets failed: %s", e)
            return [], {
                "market_counts": {},
                "selection_counts": {"input_rows": 0, "selected_rows": 0},
                "reason_codes": {},
                "adaptation_state": "unknown",
                "state": "pipeline_error",
                "errors": [str(e)],
            }

    def _fetch_3ball_value_bets(self, composite, tid) -> list:
        """Fetch 3-ball odds and return value bets across all available books."""
        try:
            from src.datagolf import fetch_matchup_odds
            from src.value import find_3ball_value_bets

            odds = fetch_matchup_odds(market="3_balls", tour=self.tour)
            if not odds:
                return []
            return find_3ball_value_bets(
                composite, odds, tournament_id=tid, enable_for_live=True,
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
            "total_rounds": result.get("total_rounds") or 0,
            "model_version": getattr(src_config, "MODEL_VERSION", "4.2"),
            "strategy": {
                "runtime_settings": meta.get("runtime_settings")
                or {"blend_weights": weights or {}},
            },
        }

    def _strategy_meta_from_pipeline(self, pipeline: dict) -> dict:
        """Card footer / provenance when strategy_config is passed explicitly (e.g. sandbox)."""
        w = pipeline.get("weights") or {}
        return {
            "strategy_source": "sandbox",
            "strategy_name": pipeline.get("name", "custom"),
            "runtime_settings": {
                "blend_weights": {
                    "course_fit": float(w.get("course_fit", 0.45)),
                    "form": float(w.get("form", 0.45)),
                    "momentum": float(w.get("momentum", 0.10)),
                },
                "ev_threshold": pipeline.get("ev_threshold"),
            },
        }

    def _generate_card(self, tournament_name, course_name, composite,
                        value_bets, output_dir, ai_pre_analysis, ai_decisions,
                        matchup_bets: list = None, mode: str = "full",
                        strategy_meta: dict | None = None,
                        ai_scores_adjusted: bool = True) -> str | None:
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
                strategy_meta=strategy_meta,
                ai_scores_adjusted=ai_scores_adjusted,
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
            logger.warning("Run metadata logging failed", exc_info=True)

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
