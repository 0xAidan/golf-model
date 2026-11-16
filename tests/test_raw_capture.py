"""Raw DataGolf odds responses are kept once per distinct payload."""

import gzip
import json
from datetime import datetime, timezone

import pytest

from src import raw_capture


@pytest.fixture
def capture_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RAW_DG_CAPTURE", "1")
    monkeypatch.setenv("RAW_DG_CAPTURE_MIN_FREE_MB", "0")
    return tmp_path / "raw_dg"


def _matchups(odds="-110"):
    return {
        "event_name": "Test Open",
        "market": "tournament_matchups",
        "match_list": [{
            "p1_dg_id": 1, "p2_dg_id": 2, "ties": "void",
            "odds": {"bet365": {"p1": odds, "p2": "-110"}},
        }],
    }


def _index_lines(root, day="2026-11-17"):
    return [json.loads(line) for line in (root / day / "index.jsonl").read_text().splitlines()]


def test_distinct_payload_is_written_once_and_every_fetch_is_indexed(capture_dir):
    params = {"tour": "pga", "market": "tournament_matchups", "odds_format": "american", "key": "SECRET"}
    t1 = datetime(2026, 11, 17, 14, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 17, 14, 5, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 11, 17, 14, 10, 0, tzinfo=timezone.utc)

    first = raw_capture.capture_response("betting-tools/matchups", params, _matchups(), now=t1)
    same = raw_capture.capture_response("betting-tools/matchups", params, _matchups(), now=t2)
    moved = raw_capture.capture_response("betting-tools/matchups", params, _matchups("-125"), now=t3)

    assert first is not None and moved is not None and same is None
    files = sorted((capture_dir / "2026-11-17").glob("*.json.gz"))
    assert len(files) == 2
    with gzip.open(first, "rt") as handle:
        stored = json.load(handle)
    assert stored["response"] == _matchups()
    assert stored["response"]["match_list"][0]["ties"] == "void"
    assert stored["params"] == {"tour": "pga", "market": "tournament_matchups", "odds_format": "american"}

    index = _index_lines(capture_dir)
    assert [line["changed"] for line in index] == [True, False, True]
    assert index[1]["file"] == index[0]["file"]
    assert index[2]["file"] != index[0]["file"]


def test_api_key_never_reaches_disk(capture_dir):
    raw_capture.capture_response(
        "betting-tools/outrights", {"tour": "pga", "market": "win", "key": "SECRET-KEY-VALUE"},
        {"odds": []}, now=datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc),
    )
    for path in capture_dir.rglob("*"):
        if not path.is_file():
            continue
        assert "SECRET-KEY-VALUE" not in path.name
        raw = gzip.open(path, "rt").read() if path.suffix == ".gz" else path.read_text()
        assert "SECRET-KEY-VALUE" not in raw


def test_other_endpoints_and_disabled_capture_write_nothing(capture_dir, monkeypatch):
    assert raw_capture.capture_response("preds/pre-tournament", {"tour": "pga"}, {"x": 1}) is None
    monkeypatch.setenv("RAW_DG_CAPTURE", "0")
    assert raw_capture.capture_response("betting-tools/matchups", {"tour": "pga"}, _matchups()) is None
    assert not capture_dir.exists()


def test_capture_is_off_under_pytest_unless_requested(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("RAW_DG_CAPTURE", raising=False)
    assert raw_capture.capture_enabled() is False


def test_low_disk_and_write_errors_never_raise(capture_dir, monkeypatch):
    monkeypatch.setenv("RAW_DG_CAPTURE_MIN_FREE_MB", str(10**9))
    assert raw_capture.capture_response("betting-tools/matchups", {"tour": "pga"}, _matchups()) is None

    monkeypatch.setenv("RAW_DG_CAPTURE_MIN_FREE_MB", "0")

    def boom(*_args, **_kwargs):
        raise OSError("disk went away")

    monkeypatch.setattr(raw_capture.gzip, "open", boom)
    assert raw_capture.capture_response("betting-tools/matchups", {"tour": "pga"}, _matchups("-140")) is None
