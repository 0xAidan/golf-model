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
"""

import os
import sys
import argparse

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
    print(f"\nStarting dashboard on http://localhost:{port}")
    print("Press Ctrl+C to stop\n")
    subprocess.run([
        sys.executable, "-m", "uvicorn", "app:app",
        "--host", "0.0.0.0",
        "--port", str(port),
        "--reload",
    ], cwd=ROOT)


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

    print(f"\nBacktest Results:")
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
    print("  3. Start Research Agent")
    print("  4. Run Backfill")
    print("  5. Run Backtest")
    print("  6. System Status")
    print("  7. Setup Wizard")
    print("  0. Exit")
    print()

    choice = input("  Enter choice (0-7): ").strip()

    class FakeArgs:
        tour = "pga"
        tournament = None
        course = None
        no_ai = False
        no_backfill = False
        port = 8000
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
        cmd_agent(args)
    elif choice == "4":
        cmd_backfill(args)
    elif choice == "5":
        cmd_backtest(args)
    elif choice == "6":
        cmd_status(args)
    elif choice == "7":
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

    args = parser.parse_args()

    if args.command is None:
        interactive_menu()
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "dashboard":
        cmd_dashboard(args)
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


if __name__ == "__main__":
    main()
