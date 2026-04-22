"""Atomic JSON writes for snapshot-style files.

Writes to a sibling temp file in the same directory, fsyncs, then renames
onto the final path. A crash at any point leaves either the previous file
or no file — never a partial/corrupt one.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, data: Any, *, indent: int | None = 2) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    nonce = secrets.token_hex(4)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{nonce}")

    payload = json.dumps(data, indent=indent)

    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def _fsync_dir(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except (OSError, PermissionError):
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
