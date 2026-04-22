"""Tests for src.atomic_io.atomic_write_json."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest import mock

import pytest

from src.atomic_io import atomic_write_json


def test_writes_valid_json(tmp_path: Path) -> None:
    target = tmp_path / "snapshot.json"
    data = {"a": 1, "nested": {"b": [1, 2, 3]}}

    atomic_write_json(target, data)

    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == data
    leftovers = [p for p in tmp_path.iterdir() if ".tmp." in p.name]
    assert leftovers == []


def test_creates_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "snap.json"
    atomic_write_json(target, {"x": 1})
    assert target.exists()


def test_failure_mid_write_preserves_previous_content(tmp_path: Path) -> None:
    target = tmp_path / "snap.json"
    atomic_write_json(target, {"version": 1})
    original = target.read_text(encoding="utf-8")

    real_replace = __import__("os").replace

    def boom(src: str, dst: str) -> None:  # noqa: ARG001
        raise RuntimeError("simulated crash before rename")

    with mock.patch("src.atomic_io.os.replace", side_effect=boom):
        with pytest.raises(RuntimeError):
            atomic_write_json(target, {"version": 2})

    assert target.read_text(encoding="utf-8") == original
    leftovers = [p for p in tmp_path.iterdir() if ".tmp." in p.name]
    assert leftovers == []
    assert real_replace  # sanity


def test_failure_with_no_prior_file_leaves_no_file(tmp_path: Path) -> None:
    target = tmp_path / "snap.json"

    with mock.patch("src.atomic_io.os.replace", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            atomic_write_json(target, {"x": 1})

    assert not target.exists()
    leftovers = [p for p in tmp_path.iterdir() if ".tmp." in p.name]
    assert leftovers == []


def test_concurrent_writers_do_not_corrupt(tmp_path: Path) -> None:
    target = tmp_path / "snap.json"
    payloads = [{"writer": i, "data": list(range(50))} for i in range(2)]
    barrier = threading.Barrier(len(payloads))
    errors: list[BaseException] = []

    def worker(payload: dict) -> None:
        try:
            barrier.wait(timeout=5)
            for _ in range(20):
                atomic_write_json(target, payload)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(p,)) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert target.exists()
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded in payloads
    leftovers = [p for p in tmp_path.iterdir() if ".tmp." in p.name]
    assert leftovers == []
