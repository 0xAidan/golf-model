#!/usr/bin/env python3
"""Promote a verified frontend build without removing old hashed chunks."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.spa_delivery import BuildValidationError, promote_frontend_build, validate_frontend_build


def _release_identifier(explicit_release: str | None) -> str:
    if explicit_release:
        return explicit_release
    for variable in ("RELEASE_SHA", "GITHUB_SHA", "GIT_COMMIT"):
        value = os.environ.get(variable)
        if value:
            return value
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    raise BuildValidationError("a release SHA is required when Git metadata is unavailable")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_dir", type=Path, help="temporary Vite output directory")
    parser.add_argument(
        "--live-dir",
        type=Path,
        default=REPO_ROOT / "frontend" / "dist",
        help="served frontend artifact directory",
    )
    parser.add_argument("--release", help="release SHA recorded in the manifest")
    parser.add_argument("--verify-only", action="store_true", help="validate without publishing")
    args = parser.parse_args()

    try:
        references = validate_frontend_build(args.build_dir)
        if args.verify_only:
            print(f"frontend build verified ({len(references)} local references)")
            return 0
        release = _release_identifier(args.release)
        promote_frontend_build(args.build_dir, args.live_dir, release=release)
    except BuildValidationError as error:
        print(f"frontend promotion failed: {error}", file=sys.stderr)
        return 1

    print(f"promoted frontend release {release} to {args.live_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
