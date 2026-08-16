#!/usr/bin/env python3
"""Side-copy restore test from Backblaze. Does not replace the live database."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.backup import verify_backup_integrity  # noqa: E402
from src.offsite_backup import download_latest_offsite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Download newest B2 backup and quick_check it")
    parser.add_argument("--dest", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    dest = args.dest or str(Path(tempfile.mkdtemp(prefix="golf-b2-drill-")) / "latest.db.gz")
    download = download_latest_offsite(dest)
    report = {"download": download, "integrity": None, "ok": False}
    if download.get("ok"):
        report["integrity"] = verify_backup_integrity(dest)
        report["ok"] = bool(report["integrity"].get("ok"))
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"ok={report['ok']} dest={dest} error={download.get('error') or download.get('reason')}")
        if report["integrity"]:
            print(f"integrity={report['integrity']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
