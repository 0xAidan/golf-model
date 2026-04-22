#!/usr/bin/env python3
"""
Golf Model — Unified Launcher

One script to rule them all. Usage:

    python start.py                  # Interactive menu
    python start.py analyze          # Run analysis for this week's event
    python start.py dashboard        # Start the web dashboard
    python start.py agent            # Start the autonomous research agent
    python start.py backfill         # Run historical data backfill
    python start.py backtest         # Run a backtest simulation
    python start.py setup            # Run first-time setup wizard
    python start.py status           # Show system status
    python start.py autoresearch-optuna   # Optuna MO walk-forward (see scripts/run_autoresearch_optuna.py)
"""

import os
import sys
import argparse
import json
from datetime import datetime

# Ensure project root is on path
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass


def cmd_analyze(args):
    """Run analysis for the current/specified tournament."""
    from src.db import ensure_initialized
    ensure_initialized()

    from src.services.golf_model_service import GolfModelService
    service = GolfModelService(tour=args.tour)

    print(f"\nRunning analysis (tour={args.tour})...\n")
    result = service.run_analysis(
        tournament_name=args.tournament,
        course_name=args.course,
        enable_ai=not args.no_ai,
        enable_backfill=not args.no_backfill,
    )

    if result.get("status") == "complete":
        print(f"\nAnalysis complete for: {result.get('event_name', 'Unknown')}")
        print(f"  Field size: {result.get('field_size', 'N/A')}")
        vb = result.get("value_bets", {})
        total_bets = sum(len(v) for v in vb.values()) if isinstance(vb, dict) else 0
        print(f"  Value bets found: {total_bets}")
        if result.get("output_file"):
            print(f"  Betting card: {result['output_file']}")
    else:
        print(f"\nAnalysis result: {result.get('status', 'unknown')}")
        if result.get("error"):
            print(f"  Error: {result['error']}")


def cmd_dashboard(args):
    """Start the FastAPI web dashboard."""
    import subprocess
    port = args.port or 8000
    quiet_logs = os.environ.get("QUIET_DEV_ACCESS_LOGS", "0").strip().lower() in {"1", "true", "yes", "on"}
    print(f"\nStarting dashboard on http://localhost:{port}")
    if quiet_logs:
        print("Quiet access logs enabled (QUIET_DEV_ACCESS_LOGS=1).")
    print("Press Ctrl+C to stop\n")
    reload_enabled = os.environ.get("UVICORN_RELOAD", "0").strip().lower() in {"1", "true", "yes", "on"}
    cmd = [
        sys.executable, "-m", "uvicorn", "app:app",
        "--host", "0.0.0.0",
        "--port", str(port),
    ]
    if reload_enabled:
        cmd.append("--reload")
    if quiet_logs:
        cmd.extend(["--no-access-log"])
    subprocess.run(cmd, cwd=ROOT)


def cmd_ui(args):
    """Start the UI in build mode or dev mode."""
    import subprocess

    frontend_root = os.path.join(ROOT, "frontend")
    port = args.port or 8000

    if getattr(args, "dev", False):
        if os.path.isdir(frontend_root) and not getattr(args, "skip_frontend_install", False):
            print("\nInstalling frontend dependencies...\n")
            subprocess.run(["npm", "install"], cwd=frontend_root, check=True)

        print(f"\nStarting backend on http://127.0.0.1:{port}")
        print(f"Starting frontend dev server on http://127.0.0.1:{args.frontend_port}")
        print("Press Ctrl+C to stop both\n")

        backend_command = [
            sys.executable, "-m", "uvicorn", "app:app",
            "--host", "0.0.0.0",
            "--port", str(port),
        ]
        if not getattr(args, "no_reload", False):
            backend_command.append("--reload")

        frontend_command = [
            "npm", "run", "dev", "--",
            "--host", "127.0.0.1",
            "--port", str(args.frontend_port),
        ]

        backend_process = subprocess.Popen(backend_command, cwd=ROOT)
        frontend_process = subprocess.Popen(frontend_command, cwd=frontend_root)

        try:
            frontend_process.wait()
        except KeyboardInterrupt:
            pass
        finally:
            for process in (frontend_process, backend_process):
                if process.poll() is None:
                    process.terminate()
        return

    if os.path.isdir(frontend_root):
        if not getattr(args, "skip_frontend_install", False):
            print("\nInstalling frontend dependencies...\n")
            subprocess.run(["npm", "install"], cwd=frontend_root, check=True)

        print("\nBuilding frontend dashboard...\n")
        subprocess.run(["npm", "run", "build"], cwd=frontend_root, check=True)

    print(f"\nStarting UI on http://localhost:{port}")
    print("Press Ctrl+C to stop\n")
    dashboard_command = [
        sys.executable, "-m", "uvicorn", "app:app",
        "--host", "0.0.0.0",
        "--port", str(port),
    ]
    if not getattr(args, "no_reload", False):
        dashboard_command.append("--reload")
    subprocess.run(dashboard_command, cwd=ROOT, check=True)


def cmd_agent(args):
    """Start the autonomous research agent."""
    from src.db import ensure_initialized
    ensure_initialized()

    from workers.research_agent import start_agent
    print("\nStarting Autonomous Research Agent...")
    print("This runs continuously. Press Ctrl+C to stop.\n")
    start_agent()


def cmd_backfill(args):
    """Run historical data backfill."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.backfill import run_full_backfill
    years = [int(y) for y in args.years.split(",")] if args.years else [2024, 2025, 2026]
    tours = [args.tour]

    print(f"\nBackfilling {', '.join(tours)} for years: {years}")
    print("This may take several minutes per year...\n")

    summary = run_full_backfill(
        tours=tours, years=years,
        include_weather=not args.no_weather,
        include_odds=True,
        include_predictions=True,
    )
    print(f"\nBackfill complete. Events: {summary.get('events_processed', 0)}")


def cmd_backtest(args):
    """Run a backtest simulation."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.strategy import StrategyConfig, simulate_strategy

    strategy = StrategyConfig(name=args.name or "cli_backtest")
    if args.min_ev:
        strategy.min_ev = float(args.min_ev)
    if args.window:
        strategy.stat_window = int(args.window)

    years = [int(y) for y in args.years.split(",")] if args.years else [2024, 2025]
    print(f"\nRunning backtest: {strategy.name}")
    print(f"  Years: {years}")
    print(f"  Min EV: {strategy.min_ev}")
    print(f"  Stat window: {strategy.stat_window}\n")

    result = simulate_strategy(strategy, years=years)
    result.compute_metrics()

    print("\nBacktest Results:")
    print(f"  Events simulated: {result.events_simulated}")
    print(f"  Total bets: {result.total_bets}")
    print(f"  Wins: {result.wins}")
    print(f"  ROI: {result.roi_pct:.1f}%")
    print(f"  CLV avg: {result.clv_avg:.4f}")
    print(f"  Sharpe: {result.sharpe:.3f}")


def cmd_setup(args):
    """Run the first-time setup wizard."""
    from setup_wizard import run_wizard
    run_wizard()


def _parse_years_arg(years: str | None) -> list[int] | None:
    if not years:
        return None
    return [int(y.strip()) for y in years.split(",") if y.strip()]


def cmd_research_run(args):
    """Run one bounded manual research cycle."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.research_cycle import run_research_cycle

    years = _parse_years_arg(getattr(args, "years", None))
    result = run_research_cycle(
        max_candidates=args.max_candidates,
        years=years,
        source="manual",
        scope=args.scope,
    )

    print("\nResearch cycle complete.")
    print(f"  Cycle key: {result['cycle_key']}")
    print(f"  Proposals created: {result['proposals_created']}")
    print(f"  Proposals evaluated: {result['proposals_evaluated']}")


def cmd_research_list(args):
    """List research proposals."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.proposals import list_proposals

    rows = list_proposals(status=args.status, limit=args.limit)
    if not rows:
        print("\nNo research proposals found.")
        return

    print()
    for row in rows:
        print(f"[{row['id']}] {row['status']}  {row['name']}  ({row['scope']})")


def cmd_research_show(args):
    """Show one research proposal."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.proposals import get_proposal

    proposal = get_proposal(args.id)
    print()
    for key in [
        "id", "name", "hypothesis", "status", "scope", "cycle_key",
        "artifact_markdown_path", "artifact_manifest_path", "converted_experiment_id",
    ]:
        print(f"{key}: {proposal.get(key)}")


def cmd_research_approve(args):
    """Approve an evaluated proposal."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.proposals import approve_proposal

    approve_proposal(args.id, reviewer=args.reviewer, notes=args.notes)
    print(f"\nApproved proposal {args.id}.")


def cmd_research_reject(args):
    """Reject an evaluated proposal."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.proposals import reject_proposal

    reject_proposal(args.id, reviewer=args.reviewer, notes=args.notes)
    print(f"\nRejected proposal {args.id}.")


def cmd_research_convert(args):
    """Convert an approved proposal into an experiment."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.proposals import convert_proposal_to_experiment

    experiment_id = convert_proposal_to_experiment(args.id)
    print(f"\nConverted proposal {args.id} into experiment {experiment_id}.")


def cmd_status(args):
    """Show system status."""
    from src.db import ensure_initialized, get_conn
    ensure_initialized()

    conn = get_conn()

    print("\n  GOLF MODEL — SYSTEM STATUS")
    print("  " + "=" * 40)

    # Database stats
    tables = [
        "tournaments", "rounds", "metrics", "results", "picks",
        "prediction_log", "runs", "historical_odds", "historical_predictions",
        "tournament_weather", "experiments", "intel_events",
        "pit_rolling_stats", "outlier_investigations",
    ]
    print("\n  Database Tables:")
    for table in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"    {table}: {count:,} rows")
        except Exception:
            print(f"    {table}: (not created)")

    # API keys
    print("\n  API Keys:")
    for key in ["DATAGOLF_API_KEY", "OPENAI_API_KEY", "ODDS_API_KEY"]:
        val = os.environ.get(key, "")
        status = f"set ({val[:8]}...)" if val else "NOT SET"
        print(f"    {key}: {status}")

    # Active strategy
    try:
        row = conn.execute("SELECT roi_pct, adopted_at FROM active_strategy WHERE scope='global'").fetchone()
        if row:
            print(f"\n  Active Strategy: ROI {row[0]:.1f}% (adopted {row[1]})")
        else:
            print("\n  Active Strategy: default (no experiments promoted yet)")
    except Exception:
        print("\n  Active Strategy: default")

    # Recent runs
    try:
        runs = conn.execute("""
            SELECT t.name, r.status, r.created_at
            FROM runs r JOIN tournaments t ON r.tournament_id = t.id
            ORDER BY r.created_at DESC LIMIT 3
        """).fetchall()
        if runs:
            print("\n  Recent Runs:")
            for r in runs:
                print(f"    {r[2]} | {r[0]} | {r[1]}")
    except Exception:
        pass

    print()


def _write_markdown(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def cmd_select_baseline(args):
    """Select the best baseline strategy from evaluated research proposals."""
    from src.db import ensure_initialized, get_conn
    ensure_initialized()

    from backtester.strategy import StrategyConfig
    from backtester.weighted_walkforward import compute_blended_score
    from backtester.model_registry import (
        get_live_weekly_model,
        get_live_weekly_model_record,
        set_research_champion,
    )

    scope = args.scope
    limit = args.limit
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT id, name, source, status, strategy_config_json, summary_metrics_json,
               guardrail_results_json, created_at
        FROM research_proposals
        WHERE scope = ?
          AND status IN ('evaluated', 'approved', 'converted')
          AND summary_metrics_json IS NOT NULL
        ORDER BY id DESC
        LIMIT ?
        """,
        (scope, limit),
    ).fetchall()
    conn.close()

    live_strategy = get_live_weekly_model(scope)
    live_record = get_live_weekly_model_record(scope) or {}
    candidates = []
    for row in rows:
        try:
            strategy = StrategyConfig.from_json(row["strategy_config_json"])
            summary = json.loads(row["summary_metrics_json"] or "{}")
            guardrails = json.loads(row["guardrail_results_json"] or "{}")
            score = compute_blended_score(summary, guardrails)
        except Exception:
            continue
        candidates.append(
            {
                "proposal_id": row["id"],
                "name": row["name"],
                "source": row["source"],
                "status": row["status"],
                "strategy": strategy,
                "summary": summary,
                "guardrails": guardrails,
                "blended_score": score,
                "created_at": row["created_at"],
            }
        )

    if not candidates:
        print("\nNo evaluated proposals found; keeping current baseline.")
        return

    candidates.sort(
        key=lambda item: (
            item["blended_score"],
            item["summary"].get("weighted_roi_pct", -999),
            item["summary"].get("weighted_clv_avg", -999),
        ),
        reverse=True,
    )
    winner = candidates[0]
    baseline_summary = {
        "name": live_strategy.name,
        "source": "live",
        "record_id": live_record.get("id"),
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(ROOT, "output", "backtests")
    md_path = os.path.join(out_dir, f"baseline_selector_{timestamp}.md")
    json_path = os.path.join(out_dir, f"baseline_selector_{timestamp}.json")
    report = [
        "# Baseline Selector Report",
        "",
        f"- Scope: `{scope}`",
        f"- Current live baseline: `{baseline_summary['name']}` (record id: {baseline_summary['record_id']})",
        f"- Candidates scanned: {len(candidates)}",
        "",
        "## Winner",
        "",
        f"- Proposal id: {winner['proposal_id']}",
        f"- Name: `{winner['name']}`",
        f"- Strategy: `{winner['strategy'].name}`",
        f"- Blended score: {winner['blended_score']}",
        f"- Weighted ROI: {winner['summary'].get('weighted_roi_pct', 0)}%",
        f"- Weighted CLV: {winner['summary'].get('weighted_clv_avg', 0)}",
        f"- Guardrails: {winner['guardrails'].get('verdict', 'unknown')}",
        "",
        "## Top Candidates",
        "",
    ]
    for idx, item in enumerate(candidates[:10], start=1):
        report.append(
            f"{idx}. `{item['strategy'].name}` (proposal {item['proposal_id']}) "
            f"score={item['blended_score']}, "
            f"roi={item['summary'].get('weighted_roi_pct', 0)}%, "
            f"clv={item['summary'].get('weighted_clv_avg', 0):.4f}, "
            f"guardrails={item['guardrails'].get('verdict', 'unknown')}"
        )
    report.append("")

    _write_markdown(md_path, "\n".join(report))
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "scope": scope,
                "generated_at": datetime.now().isoformat(),
                "current_live": baseline_summary,
                "winner": {
                    "proposal_id": winner["proposal_id"],
                    "name": winner["name"],
                    "strategy_name": winner["strategy"].name,
                    "blended_score": winner["blended_score"],
                    "summary_metrics": winner["summary"],
                    "guardrail_results": winner["guardrails"],
                },
                "top_candidates": [
                    {
                        "proposal_id": item["proposal_id"],
                        "strategy_name": item["strategy"].name,
                        "blended_score": item["blended_score"],
                        "summary_metrics": item["summary"],
                        "guardrail_results": item["guardrails"],
                    }
                    for item in candidates[:10]
                ],
            },
            handle,
            indent=2,
        )

    if args.set_research_champion:
        set_research_champion(
            winner["strategy"],
            scope=scope,
            source="manual_baseline_selector",
            proposal_id=winner["proposal_id"],
            notes=f"Selected by start.py select-baseline at {datetime.now().isoformat()}",
        )
        print("\nSelected winner has been set as research champion.")

    print("\nBaseline selection complete.")
    print(f"  Winner: {winner['strategy'].name} (proposal {winner['proposal_id']})")
    print(f"  Blended score: {winner['blended_score']}")
    print(f"  Markdown report: {md_path}")
    print(f"  JSON report: {json_path}")


def cmd_autoresearch_batch(args):
    """Run multiple bounded autoresearch cycles and aggregate results."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.research_cycle import run_research_cycle

    years = _parse_years_arg(getattr(args, "years", None))
    cycles = max(1, int(args.cycles))
    all_results = []
    print(f"\nRunning bounded autoresearch batch: {cycles} cycle(s)")
    for idx in range(cycles):
        result = run_research_cycle(
            max_candidates=args.max_candidates,
            years=years,
            source="manual_autoresearch_batch",
            scope=args.scope,
            seed=42 + idx,
        )
        all_results.append(result)
        winner = result.get("winner") or {}
        print(
            f"  Cycle {idx + 1}/{cycles}: "
            f"{winner.get('strategy_name', 'no winner')} "
            f"(score={winner.get('blended_score', 'n/a')})"
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(ROOT, "output", "research")
    md_path = os.path.join(out_dir, f"autoresearch_batch_{timestamp}.md")
    json_path = os.path.join(out_dir, f"autoresearch_batch_{timestamp}.json")

    winners = [r.get("winner") for r in all_results if r.get("winner")]
    winners_sorted = sorted(winners, key=lambda x: x.get("blended_score", -999), reverse=True)
    lines = [
        "# Autoresearch Batch Summary",
        "",
        f"- Scope: `{args.scope}`",
        f"- Cycles run: {cycles}",
        f"- Max candidates/cycle: {args.max_candidates}",
        f"- Years: {years or 'default'}",
        "",
        "## Winners by Cycle",
        "",
    ]
    for idx, result in enumerate(all_results, start=1):
        winner = result.get("winner") or {}
        lines.append(
            f"{idx}. `{winner.get('strategy_name', 'n/a')}` "
            f"(score={winner.get('blended_score', 'n/a')}, "
            f"decision={result.get('promotion_decision', 'n/a')})"
        )
    lines.append("")
    lines.append("## Best Overall Candidate")
    lines.append("")
    if winners_sorted:
        best = winners_sorted[0]
        lines.append(f"- Strategy: `{best.get('strategy_name', 'n/a')}`")
        lines.append(f"- Proposal id: {best.get('proposal_id', 'n/a')}")
        lines.append(f"- Blended score: {best.get('blended_score', 'n/a')}")
        lines.append(f"- Guardrails: {best.get('guardrail_results', {}).get('verdict', 'n/a')}")
    else:
        lines.append("- No winner produced in this batch.")
    lines.append("")
    _write_markdown(md_path, "\n".join(lines))

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "scope": args.scope,
                "cycles": cycles,
                "max_candidates": args.max_candidates,
                "years": years,
                "results": all_results,
                "best_winner": winners_sorted[0] if winners_sorted else None,
                "generated_at": datetime.now().isoformat(),
            },
            handle,
            indent=2,
        )

    print("\nAutoresearch batch complete.")
    print(f"  Summary markdown: {md_path}")
    print(f"  Summary json: {json_path}")


def cmd_autoresearch(args):
    """Run the keep/discard autoresearch loop locally."""
    from src.db import ensure_initialized
    ensure_initialized()
    import subprocess

    script = os.path.join(ROOT, "scripts", "run_autoresearch_loop.py")
    proc = subprocess.run(
        [
            sys.executable,
            script,
            "--iterations",
            str(max(1, int(args.iterations))),
            "--seed",
            str(int(args.seed)),
            "--timeout-seconds",
            str(max(30, int(args.timeout_seconds))),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    print("\nAutoresearch loop finished.")
    print(proc.stdout.strip() or proc.stderr.strip())


def cmd_autoresearch_optuna(args):
    """Delegate to scripts/run_autoresearch_optuna.py (Optuna MO or scalar + walk-forward)."""
    import subprocess

    script = os.path.join(ROOT, "scripts", "run_autoresearch_optuna.py")
    cmd = [
        sys.executable,
        script,
        "--n-trials",
        str(max(1, int(args.n_trials))),
        "--years",
        args.years,
        "--study-name",
        args.study_name,
        "--scope",
        args.scope,
        "--n-jobs",
        str(max(1, int(args.n_jobs))),
    ]
    if getattr(args, "scalar", False):
        cmd.append("--scalar")
        cmd.extend(["--scalar-metric", getattr(args, "scalar_metric", "blended_score")])
    proc = subprocess.run(cmd, cwd=ROOT)
    raise SystemExit(proc.returncode)


def interactive_menu():
    """Show an interactive menu for users who just run 'python start.py'."""
    print()
    print("=" * 60)
    print("    GOLF MODEL — Professional Golf Prediction Engine")
    print("=" * 60)
    print()
    print("  Choose an option:")
    print()
    print("  1. Run Analysis (this week's tournament)")
    print("  2. Open Web Dashboard")
    print("  3. Launch Full UI (one command)")
    print("  4. Start Research Agent")
    print("  5. Run Backfill")
    print("  6. Run Backtest")
    print("  7. System Status")
    print("  8. Setup Wizard")
    print("  0. Exit")
    print()

    choice = input("  Enter choice (0-8): ").strip()

    class FakeArgs:
        tour = "pga"
        tournament = None
        course = None
        no_ai = False
        no_backfill = False
        port = 8000
        skip_frontend_install = False
        no_reload = False
        years = None
        no_weather = False
        name = None
        min_ev = None
        window = None

    args = FakeArgs()

    if choice == "1":
        cmd_analyze(args)
    elif choice == "2":
        cmd_dashboard(args)
    elif choice == "3":
        cmd_ui(args)
    elif choice == "4":
        cmd_agent(args)
    elif choice == "5":
        cmd_backfill(args)
    elif choice == "6":
        cmd_backtest(args)
    elif choice == "7":
        cmd_status(args)
    elif choice == "8":
        cmd_setup(args)
    elif choice == "0":
        print("  Goodbye!")
        sys.exit(0)
    else:
        print("  Invalid choice. Try again.")
        interactive_menu()


def main():
    parser = argparse.ArgumentParser(
        description="Golf Model — Unified Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Run analysis")
    p_analyze.add_argument("--tour", default="pga")
    p_analyze.add_argument("--tournament", default=None)
    p_analyze.add_argument("--course", default=None)
    p_analyze.add_argument("--no-ai", action="store_true")
    p_analyze.add_argument("--no-backfill", action="store_true")

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Start web dashboard")
    p_dash.add_argument("--port", type=int, default=8000)

    # ui
    p_ui = subparsers.add_parser("ui", help="Install/build frontend and start the dashboard")
    p_ui.add_argument("--port", type=int, default=8000)
    p_ui.add_argument("--frontend-port", type=int, default=5173)
    p_ui.add_argument("--dev", action="store_true")
    p_ui.add_argument("--skip-frontend-install", action="store_true")
    p_ui.add_argument("--no-reload", action="store_true")

    # agent
    subparsers.add_parser("agent", help="Start research agent")

    # backfill
    p_bf = subparsers.add_parser("backfill", help="Run data backfill")
    p_bf.add_argument("--tour", default="pga")
    p_bf.add_argument("--years", default=None, help="Comma-separated years")
    p_bf.add_argument("--no-weather", action="store_true")

    # backtest
    p_bt = subparsers.add_parser("backtest", help="Run backtest")
    p_bt.add_argument("--name", default=None)
    p_bt.add_argument("--years", default=None)
    p_bt.add_argument("--min-ev", default=None)
    p_bt.add_argument("--window", default=None)

    # setup
    subparsers.add_parser("setup", help="Run setup wizard")

    # status
    subparsers.add_parser("status", help="Show system status")

    # research-run
    p_rr = subparsers.add_parser("research-run", help="Run one manual research cycle")
    p_rr.add_argument("--max-candidates", type=int, default=5)
    p_rr.add_argument("--years", default=None, help="Comma-separated years")
    p_rr.add_argument("--scope", default="global")

    # research-list
    p_rl = subparsers.add_parser("research-list", help="List research proposals")
    p_rl.add_argument("--status", default=None)
    p_rl.add_argument("--limit", type=int, default=20)

    # research-show
    p_rs = subparsers.add_parser("research-show", help="Show a research proposal")
    p_rs.add_argument("--id", type=int, required=True)

    # research-approve
    p_ra = subparsers.add_parser("research-approve", help="Approve a proposal")
    p_ra.add_argument("--id", type=int, required=True)
    p_ra.add_argument("--reviewer", default="manual")
    p_ra.add_argument("--notes", default=None)

    # research-reject
    p_rj = subparsers.add_parser("research-reject", help="Reject a proposal")
    p_rj.add_argument("--id", type=int, required=True)
    p_rj.add_argument("--reviewer", default="manual")
    p_rj.add_argument("--notes", default=None)

    # research-convert
    p_rc = subparsers.add_parser("research-convert", help="Convert a proposal to an experiment")
    p_rc.add_argument("--id", type=int, required=True)

    # select-baseline
    p_sb = subparsers.add_parser("select-baseline", help="Select best baseline from evaluated proposals")
    p_sb.add_argument("--scope", default="global")
    p_sb.add_argument("--limit", type=int, default=200)
    p_sb.add_argument("--set-research-champion", action="store_true")

    # autoresearch-batch
    p_ab = subparsers.add_parser("autoresearch-batch", help="Run N bounded autoresearch cycles")
    p_ab.add_argument("--scope", default="global")
    p_ab.add_argument("--cycles", type=int, default=3)
    p_ab.add_argument("--max-candidates", type=int, default=3)
    p_ab.add_argument("--years", default=None, help="Comma-separated years")

    # autoresearch
    p_ar = subparsers.add_parser("autoresearch", help="Run keep/discard autoresearch loop")
    p_ar.add_argument("--iterations", type=int, default=10)
    p_ar.add_argument("--seed", type=int, default=42)
    p_ar.add_argument("--timeout-seconds", type=int, default=120)

    p_ao = subparsers.add_parser("autoresearch-optuna", help="Run Optuna MO or scalar walk-forward study")
    p_ao.add_argument("--n-trials", type=int, default=10)
    p_ao.add_argument("--years", default="2024,2025", help="Comma-separated benchmark years")
    p_ao.add_argument("--study-name", dest="study_name", default="golf_mo_default")
    p_ao.add_argument("--scope", default="global")
    p_ao.add_argument("--n-jobs", type=int, default=1)
    p_ao.add_argument("--scalar", action="store_true", help="Single-objective (blended_score or ROI)")
    p_ao.add_argument(
        "--scalar-metric",
        default="blended_score",
        choices=("blended_score", "weighted_roi_pct"),
        help="When --scalar is set",
    )

    args = parser.parse_args()

    if args.command is None:
        interactive_menu()
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "dashboard":
        cmd_dashboard(args)
    elif args.command == "ui":
        cmd_ui(args)
    elif args.command == "agent":
        cmd_agent(args)
    elif args.command == "backfill":
        cmd_backfill(args)
    elif args.command == "backtest":
        cmd_backtest(args)
    elif args.command == "setup":
        cmd_setup(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "research-run":
        cmd_research_run(args)
    elif args.command == "research-list":
        cmd_research_list(args)
    elif args.command == "research-show":
        cmd_research_show(args)
    elif args.command == "research-approve":
        cmd_research_approve(args)
    elif args.command == "research-reject":
        cmd_research_reject(args)
    elif args.command == "research-convert":
        cmd_research_convert(args)
    elif args.command == "select-baseline":
        cmd_select_baseline(args)
    elif args.command == "autoresearch-batch":
        cmd_autoresearch_batch(args)
    elif args.command == "autoresearch":
        cmd_autoresearch(args)
    elif args.command == "autoresearch-optuna":
        cmd_autoresearch_optuna(args)


if __name__ == "__main__":
    main()
