"""Tests for research CLI wiring in start.py."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_main_dispatches_research_run(monkeypatch):
    """The unified launcher should route research-run to its handler."""
    import start

    called = {}

    def fake_cmd(args):
        called["command"] = args.command
        called["max_candidates"] = args.max_candidates

    monkeypatch.setattr(start, "cmd_research_run", fake_cmd, raising=False)
    monkeypatch.setattr(start, "interactive_menu", lambda: (_ for _ in ()).throw(AssertionError("should not open menu")))
    monkeypatch.setattr(sys, "argv", ["start.py", "research-run", "--max-candidates", "2"])

    start.main()

    assert called["command"] == "research-run"
    assert called["max_candidates"] == 2
