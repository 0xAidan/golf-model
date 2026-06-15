#!/usr/bin/env python3
"""Import season picks from markdown cards and provenance JSON."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.card_import import import_cards_from_dirs


def main() -> int:
    parser = argparse.ArgumentParser(description="Import betting cards into pick inventory")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--apply", action="store_true", help="Write picks to DB (default dry-run)")
    parser.add_argument(
        "--from-dir",
        action="append",
        dest="from_dirs",
        default=[],
        help="Directory to scan (repeatable)",
    )
    parser.add_argument("--git-archaeology", action="store_true", help="Reserved for future git recovery")
    args = parser.parse_args()

    del args.git_archaeology

    search_dirs = [Path(path) for path in args.from_dirs]
    if not search_dirs:
        search_dirs = [
            ROOT / "data" / "local_recovery" / "md_cards",
            ROOT / "output",
        ]

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    manifest = import_cards_from_dirs(search_dirs, year=args.year, dry_run=not args.apply)
    out_dir = ROOT / "data" / "local_recovery"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"manifest_{args.year}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "year": manifest.year,
        "dry_run": not args.apply,
        "events": manifest.events,
        "errors": manifest.errors,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"Manifest written to {out_path}")
    hard_errors = [err for err in manifest.errors if "provenance" not in err and "unresolved_event" not in err]
    return 0 if not hard_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
