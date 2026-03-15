"""Tests for DataGolf throttle and cache behavior."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_datagolf_request_manager_caches_responses():
    from src.datagolf import DataGolfRequestManager

    manager = DataGolfRequestManager(max_requests=2, window_seconds=60, cooldown_seconds=300)
    manager.set_cached("endpoint:{}", {"ok": True}, ttl_seconds=30, now=100.0)

    assert manager.get_cached("endpoint:{}", now=110.0) == {"ok": True}
    assert manager.get_cached("endpoint:{}", now=131.0) is None


def test_datagolf_request_manager_reports_required_wait():
    from src.datagolf import DataGolfRequestManager

    manager = DataGolfRequestManager(max_requests=2, window_seconds=60, cooldown_seconds=300)

    assert manager.reserve_slot(now=100.0) == 0.0
    assert manager.reserve_slot(now=110.0) == 0.0
    assert manager.reserve_slot(now=120.0) > 0.0

    manager.mark_rate_limited(now=120.0)
    assert manager.reserve_slot(now=121.0) > 0.0
