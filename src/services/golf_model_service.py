"""Central orchestration service for the golf model pipeline."""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional

from src import db
from src.card import generate_card
from src.config_loader import ProfileNotFoundError, resolve_profile
from src.csv_parser import ingest_folder
from src.datagolf import backfill_rounds, sync_tournament
from src.models.composite import compute_composite
from src.odds import fetch_odds_api, get_best_odds, load_manual_odds
from src.value import find_value_bets

try:
    from src.rolling_stats import compute_rolling_metrics, get_field_from_metrics
except ImportError:  # pragma: no cover - optional dependency during tests
    compute_rolling_metrics = None  # type: ignore
    get_field_from_metrics = None  # type: ignore

LOGGER = logging.getLogger("golfmodel.service")


@dataclass
class AnalysisConfig:
    tournament: str
    course: Optional[str] = None
    folder: Optional[str] = None
    odds_path: Optional[str] = None
    no_odds: Optional[bool] = None
    output_dir: Optional[str] = None
    sync: Optional[bool] = None
    backfill_years: Optional[List[int]] = None
    tour: Optional[str] = None
    course_num: Optional[int] = None
    ai: Optional[bool] = None
    profile: Optional[str] = None

    def merge(self, overrides: Dict[str, Any]) -> "AnalysisConfig":
        data = asdict(self)
        data.update({k: v for k, v in overrides.items() if v is not None})
        return AnalysisConfig(**data)


@dataclass
class AnalysisResult:
    tournament_id: int
    composite: List[dict]
    value_bets: Dict[str, List[dict]]
    weights: Dict[str, Any]
    card_path: str
    run_id: int
    sync_summary: Optional[dict] = None
    csv_summary: Optional[dict] = None
    odds_summary: Optional[dict] = None
    ai_summary: Optional[dict] = None


class GolfModelService:
    def __init__(self, project_root: Optional[Path] = None, logger: Optional[logging.Logger] = None):
        self.project_root = Path(project_root or Path(__file__).resolve().parents[2])
        self.logger = logger or LOGGER

    # ── Public API ──────────────────────────────────────────

    def run_analysis(self, config: AnalysisConfig) -> AnalysisResult:
        config = self._apply_profile(config)
        config = self._normalize_config(config)
        self._log("run.start", config=asdict(config))

        tournament_id = db.get_or_create_tournament(config.tournament, config.course)
        run_id = db.log_run_start(
            tournament_id=tournament_id,
            profile_name=config.profile,
            inputs=asdict(config),
        )
        run_started_at = time.time()

        try:
            sync_summary = self._maybe_backfill_and_sync(tournament_id, config)
            csv_summary = self._maybe_ingest_csv(tournament_id, config)

            players = db.get_all_players(tournament_id)
            if not players:
                raise RuntimeError(
                    "No player metrics found. Run Data Golf sync or provide CSVs."
                )

            weights = db.get_active_weights()
            composite = compute_composite(
                tournament_id,
                weights,
                course_name=config.course,
            )
            if not composite:
                raise RuntimeError("Composite model returned no players.")

            odds_summary, value_bets = self._maybe_fetch_odds(
                tournament_id, composite, config
            )

            ai_summary = self._maybe_run_ai(
                tournament_id, composite, value_bets, config
            )

            card_path = generate_card(
                config.tournament,
                config.course or "Unknown",
                composite,
                value_bets,
                output_dir=config.output_dir,
            )

            run_duration = time.time() - run_started_at
            dg_hash = (sync_summary or {}).get("payload_hash")
            db.log_run_finish(
                run_id=run_id,
                status="success",
                players_scored=len(composite),
                value_bets=sum(len(v) for v in value_bets.values()),
                card_path=card_path,
                sync_metrics=(sync_summary or {}).get("total_metrics"),
                dg_payload_hash=dg_hash,
                ai_enabled=1 if ai_summary else 0,
                ai_cost_usd=(ai_summary or {}).get("cost_usd"),
                api_spend_usd=(sync_summary or {}).get("api_spend_usd"),
                duration_seconds=run_duration,
            )

            self._log(
                "run.complete",
                run_id=run_id,
                players=len(composite),
                value_bets=sum(len(v) for v in value_bets.values()),
                card_path=card_path,
            )

            return AnalysisResult(
                tournament_id=tournament_id,
                composite=composite,
                value_bets=value_bets,
                weights=weights,
                card_path=card_path,
                run_id=run_id,
                sync_summary=sync_summary,
                csv_summary=csv_summary,
                odds_summary=odds_summary,
                ai_summary=ai_summary,
            )
        except Exception as exc:
            db.log_run_finish(run_id=run_id, status="error", error=str(exc))
            self._log("run.error", run_id=run_id, error=str(exc))
            raise

    # ── Internals ───────────────────────────────────────────

    def _apply_profile(self, config: AnalysisConfig) -> AnalysisConfig:
        if not config.profile:
            return config
        try:
            overrides = resolve_profile(config.profile, asdict(config))
        except ProfileNotFoundError as exc:
            raise RuntimeError(str(exc)) from exc
        merged = config.merge(overrides)
        merged.profile = config.profile
        return merged

    def _normalize_config(self, config: AnalysisConfig) -> AnalysisConfig:
        updates = {}
        if config.folder is None:
            updates["folder"] = "data/csvs"
        if config.output_dir is None:
            updates["output_dir"] = "output"
        if config.tour is None:
            updates["tour"] = "pga"
        if updates:
            return replace(config, **updates)
        return config

    def _maybe_backfill_and_sync(self, tournament_id: int, config: AnalysisConfig) -> Optional[dict]:
        if config.backfill_years:
            self._log("backfill.start", years=config.backfill_years, tour=config.tour)
            backfill_rounds(tours=[config.tour], years=config.backfill_years)
            self._log("backfill.complete", years=config.backfill_years)

        if not self._should_sync(config):
            return None

        self._log("sync.start", tour=config.tour)
        summary = sync_tournament(tournament_id, tour=config.tour)
        payload_hash = summary.get("payload_hash")
        if not payload_hash and summary:
            summary["payload_hash"] = None
        self._log(
            "sync.complete",
            metrics=summary.get("total_metrics", 0),
            payload_hash=summary.get("payload_hash"),
            errors=summary.get("errors", []),
        )

        if compute_rolling_metrics and get_field_from_metrics:
            field = get_field_from_metrics(tournament_id)
            if field:
                self._log("rolling.compute", players=len(field), course_num=config.course_num)
                rolling = compute_rolling_metrics(
                    tournament_id, field, course_num=config.course_num
                )
                summary["rolling_metrics"] = rolling
        return summary

    def _maybe_ingest_csv(self, tournament_id: int, config: AnalysisConfig) -> Optional[dict]:
        if not config.folder:
            return None
        folder_path = Path(config.folder)
        if not folder_path.is_absolute():
            folder_path = (self.project_root / config.folder).resolve()
        if not folder_path.exists() or not folder_path.is_dir():
            return None
        csv_files = [f for f in folder_path.glob("*.csv")]
        if not csv_files:
            return None
        self._log("csv.ingest", folder=str(folder_path), files=len(csv_files))
        summary = ingest_folder(str(folder_path), tournament_id)
        return summary

    def _maybe_fetch_odds(
        self,
        tournament_id: int,
        composite: List[dict],
        config: AnalysisConfig,
    ) -> tuple[dict, Dict[str, List[dict]]]:
        if self._skip_odds(config):
            return {"status": "skipped"}, {}

        all_odds: List[dict] = []
        odds_summary: Dict[str, Any] = {"sources": []}
        for market in ["outrights", "top_5", "top_10", "top_20"]:
            try:
                api_odds = fetch_odds_api(market)
            except Exception as exc:
                odds_summary.setdefault("errors", []).append(str(exc))
                continue
            if api_odds:
                odds_summary["sources"].append({"market": market, "count": len(api_odds)})
                all_odds.extend(api_odds)

        if config.odds_path:
            manual = load_manual_odds(config.odds_path)
            if manual:
                odds_summary["manual_file"] = config.odds_path
                all_odds.extend(manual)

        if not all_odds:
            return {"status": "no_odds"}, {}

        value_bets: Dict[str, List[dict]] = {}
        odds_by_market: Dict[str, List[dict]] = {}
        for entry in all_odds:
            odds_by_market.setdefault(entry["market"], []).append(entry)

        for market, market_odds in odds_by_market.items():
            best = get_best_odds(market_odds)
            bet_type = "outright" if market == "outrights" else market.replace("top_", "top")
            vb = find_value_bets(composite, best, bet_type=bet_type, tournament_id=tournament_id)
            value_bets[bet_type] = vb

        return odds_summary, value_bets

    def _maybe_run_ai(
        self,
        tournament_id: int,
        composite: List[dict],
        value_bets: Dict[str, List[dict]],
        config: AnalysisConfig,
    ) -> Optional[dict]:
        if not self._should_run_ai(config):
            return None

        try:
            from src.ai_brain import (
                apply_ai_adjustments,
                is_ai_available,
                make_betting_decisions,
                pre_tournament_analysis,
            )
            from src.course_profile import load_course_profile
        except ImportError as exc:  # pragma: no cover
            self._log("ai.error", error=str(exc))
            return None

        if not is_ai_available():
            self._log("ai.skipped", reason="unavailable")
            return None

        course_profile = None
        if config.course:
            course_profile = load_course_profile(config.course)

        pre_analysis = pre_tournament_analysis(
            tournament_id=tournament_id,
            composite_results=composite,
            course_profile=course_profile,
            tournament_name=config.tournament,
            course_name=config.course or "",
        )
        composite = apply_ai_adjustments(composite, pre_analysis)

        decisions = {}
        if value_bets:
            decisions = make_betting_decisions(
                tournament_id=tournament_id,
                value_bets_by_type=value_bets,
                pre_analysis=pre_analysis,
                composite_results=composite,
                tournament_name=config.tournament,
                course_name=config.course or "",
            )
        summary = {
            "pre_analysis": pre_analysis,
            "decisions": decisions,
            "cost_usd": decisions.get("cost_usd") if isinstance(decisions, dict) else None,
        }
        return summary

    def _should_sync(self, config: AnalysisConfig) -> bool:
        if config.sync is not None:
            return config.sync
        return bool(os.environ.get("DATAGOLF_API_KEY"))

    def _skip_odds(self, config: AnalysisConfig) -> bool:
        if config.no_odds is None:
            return False
        return bool(config.no_odds)

    def _should_run_ai(self, config: AnalysisConfig) -> bool:
        if config.ai is None:
            return False
        return bool(config.ai)

    def _log(self, event: str, **kwargs):
        payload = {"event": event, **kwargs}
        self.logger.info(json.dumps(payload, default=str))
