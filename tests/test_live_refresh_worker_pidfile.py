"""Tests for live-refresh worker pidfile hardening (P0-3 follow-up)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workers import live_refresh_worker as worker


def test_clear_stale_pidfile_removes_dead_pid(tmp_path):
    pidfile = tmp_path / "worker.pid"
    pidfile.write_text("999999999\n")  # almost certainly not a live pid
    worker._clear_stale_pidfile(str(pidfile))
    assert not pidfile.exists()


def test_clear_stale_pidfile_keeps_live_pid(tmp_path):
    pidfile = tmp_path / "worker.pid"
    pidfile.write_text(f"{os.getpid()}\n")  # this test process is alive
    worker._clear_stale_pidfile(str(pidfile))
    # Should NOT remove a pidfile pointing at a live process.
    assert pidfile.exists()


def test_clear_stale_pidfile_handles_garbage(tmp_path):
    pidfile = tmp_path / "worker.pid"
    pidfile.write_text("not-a-pid")
    worker._clear_stale_pidfile(str(pidfile))
    assert not pidfile.exists()


def test_clear_stale_pidfile_missing_is_noop(tmp_path):
    pidfile = tmp_path / "absent.pid"
    worker._clear_stale_pidfile(str(pidfile))  # must not raise
    assert not pidfile.exists()
