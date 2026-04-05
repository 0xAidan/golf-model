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


def test_main_dispatches_ui(monkeypatch):
    """The unified launcher should route ui to the one-command dashboard handler."""
    import start

    called = {}

    def fake_cmd(args):
        called["command"] = args.command
        called["port"] = args.port

    monkeypatch.setattr(start, "cmd_ui", fake_cmd, raising=False)
    monkeypatch.setattr(start, "interactive_menu", lambda: (_ for _ in ()).throw(AssertionError("should not open menu")))
    monkeypatch.setattr(sys, "argv", ["start.py", "ui", "--port", "8123"])

    start.main()

    assert called["command"] == "ui"
    assert called["port"] == 8123


def test_cmd_ui_builds_frontend_then_starts_dashboard(monkeypatch):
    """The one-command UI launcher should prepare the frontend before starting FastAPI."""
    import start

    calls = []

    def fake_run(command, cwd=None, **kwargs):
        calls.append((command, cwd))
        return 0

    class Args:
        port = 8000
        skip_frontend_install = False
        no_reload = False

    monkeypatch.setattr("subprocess.run", fake_run)

    start.cmd_ui(Args())

    assert calls[0][0] == ["npm", "install"]
    assert calls[0][1] == os.path.join(start.ROOT, "frontend")
    assert calls[1][0] == ["npm", "run", "build"]
    assert calls[1][1] == os.path.join(start.ROOT, "frontend")
    assert calls[2][0][:4] == [sys.executable, "-m", "uvicorn", "app:app"]
    assert calls[2][1] == start.ROOT


def test_cmd_ui_dev_starts_backend_and_vite(monkeypatch):
    """Dev mode should run FastAPI and Vite together for design-mode work."""
    import start

    run_calls = []
    popen_calls = []
    waits = []
    terminated = []

    def fake_run(command, cwd=None, **kwargs):
        run_calls.append((command, cwd))
        return 0

    class FakeProcess:
        def __init__(self, command, cwd=None):
            self.command = command
            self.cwd = cwd
            self.returncode = None

        def wait(self):
            waits.append((self.command, self.cwd))
            raise KeyboardInterrupt

        def poll(self):
            return None

        def terminate(self):
            terminated.append((self.command, self.cwd))

    def fake_popen(command, cwd=None, **kwargs):
        popen_calls.append((command, cwd))
        return FakeProcess(command, cwd)

    class Args:
        port = 8000
        frontend_port = 5173
        skip_frontend_install = False
        no_reload = False
        dev = True

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("subprocess.Popen", fake_popen)

    start.cmd_ui(Args())

    assert run_calls == [(["npm", "install"], os.path.join(start.ROOT, "frontend"))]
    assert popen_calls[0][0][:4] == [sys.executable, "-m", "uvicorn", "app:app"]
    assert popen_calls[0][1] == start.ROOT
    assert popen_calls[1][0][:3] == ["npm", "run", "dev"]
    assert popen_calls[1][1] == os.path.join(start.ROOT, "frontend")
    assert waits[0][0][:3] == ["npm", "run", "dev"]
    assert len(terminated) == 2
