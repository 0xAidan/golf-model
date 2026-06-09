#!/usr/bin/env python3
"""Read-only audit of port 8000 ownership for split-brain detection."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class ListenerInfo:
    pid: int
    cwd: str | None
    cmdline: str | None
    ppid: int | None
    systemd_unit: str | None
    ok: bool
    reason: str


def _read_proc_field(pid: int, name: str) -> str | None:
    path = Path(f"/proc/{pid}/{name}")
    if not path.is_file():
        return None
    try:
        if name == "cwd":
            return os.readlink(path)
        if name == "cmdline":
            raw = path.read_bytes()
            return raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip() or None
        return path.read_text(encoding="utf-8", errors="replace").strip() or None
    except OSError:
        return None


def _systemd_unit_for_pid(pid: int) -> str | None:
    try:
        probe = subprocess.run(
            ["systemctl", "status", str(pid)],
            capture_output=True,
            text=True,
            check=False,
            timeout=2.0,
        )
        for line in (probe.stdout or "").splitlines():
            stripped = line.strip()
            if stripped.startswith("● ") and ".service" in stripped:
                return stripped.split()[1]
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def _listener_pids() -> list[int]:
    try:
        probe = subprocess.run(
            ["ss", "-tlnp", "sport", "=", ":8000"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    pids: set[int] = set()
    for line in (probe.stdout or "").splitlines():
        if "pid=" not in line:
            continue
        for token in line.split("pid=")[1:]:
            digits = ""
            for ch in token:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            if digits:
                pids.add(int(digits))
    return sorted(pids)


def classify_listener(pid: int, *, expected_app_root: str) -> ListenerInfo:
    cwd = _read_proc_field(pid, "cwd")
    cmdline = _read_proc_field(pid, "cmdline")
    ppid_raw = _read_proc_field(pid, "stat")
    ppid = None
    if ppid_raw:
        parts = ppid_raw.split()
        if len(parts) > 3:
            try:
                ppid = int(parts[3])
            except ValueError:
                ppid = None
    unit = _systemd_unit_for_pid(pid)
    expected = str(Path(expected_app_root).resolve())
    if cwd is None:
        return ListenerInfo(pid, cwd, cmdline, ppid, unit, False, "unable to read process cwd")
    resolved_cwd = str(Path(cwd).resolve())
    if resolved_cwd != expected:
        return ListenerInfo(
            pid,
            resolved_cwd,
            cmdline,
            ppid,
            unit,
            False,
            f"listener cwd {resolved_cwd} != expected {expected}",
        )
    if cmdline and "live_refresh_worker" in cmdline:
        return ListenerInfo(
            pid,
            resolved_cwd,
            cmdline,
            ppid,
            unit,
            False,
            "port 8000 owned by live-refresh worker (unexpected)",
        )
    return ListenerInfo(pid, resolved_cwd, cmdline, ppid, unit, True, "expected dashboard listener")


def audit_port_8000(*, expected_app_root: str = "/opt/golf-model") -> dict[str, Any]:
    listeners = [classify_listener(pid, expected_app_root=expected_app_root) for pid in _listener_pids()]
    if not listeners:
        ok = True
    elif len(listeners) == 1 and listeners[0].ok:
        ok = True
    else:
        ok = False
    return {
        "ok": ok,
        "expected_app_root": str(Path(expected_app_root).resolve()),
        "listener_count": len(listeners),
        "listeners": [asdict(item) for item in listeners],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit port 8000 listener ownership.")
    parser.add_argument(
        "--expected-app-root",
        default=os.environ.get("GOLF_APP_ROOT", "/opt/golf-model"),
        help="Canonical deploy root for dashboard listener.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()
    report = audit_port_8000(expected_app_root=args.expected_app_root)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"port_8000 ok={report['ok']} listeners={report['listener_count']}")
        for item in report["listeners"]:
            print(
                f"  pid={item['pid']} cwd={item['cwd']} unit={item['systemd_unit']} "
                f"ok={item['ok']} reason={item['reason']}"
            )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
