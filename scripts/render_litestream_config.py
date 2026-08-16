#!/usr/bin/env python3
"""Render deploy/litestream/litestream.yml with env vars into a runtime file."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = _REPO_ROOT / "deploy" / "litestream" / "litestream.yml"
DEFAULT_OUT = Path("/run/golf-litestream.yml")


def render() -> str:
    db_path = (
        os.environ.get("GOLF_DB_PATH")
        or str(Path(os.environ.get("GOLF_DATA_DIR") or (_REPO_ROOT / "data")) / "golf.db")
    )
    replacements = {
        "${GOLF_DB_PATH}": db_path,
        "${B2_BUCKET_NAME}": os.environ.get("B2_BUCKET_NAME") or "",
        "${B2_S3_ENDPOINT}": os.environ.get("B2_S3_ENDPOINT") or "s3.us-west-000.backblazeb2.com",
        "${B2_APPLICATION_KEY_ID}": os.environ.get("B2_APPLICATION_KEY_ID") or "",
        "${B2_APPLICATION_KEY}": os.environ.get("B2_APPLICATION_KEY") or "",
    }
    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    if not (os.environ.get("B2_BUCKET_NAME") and os.environ.get("B2_APPLICATION_KEY_ID") and os.environ.get("B2_APPLICATION_KEY")):
        print("B2 credentials missing; not rendering Litestream config", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(), encoding="utf-8")
    os.chmod(out, 0o600)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
