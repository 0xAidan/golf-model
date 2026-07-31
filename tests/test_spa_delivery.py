from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.spa_delivery import BuildValidationError, validate_frontend_build


def test_validate_frontend_build_accepts_existing_local_references(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app-123.js").write_text("console.log('ok')", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg />", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<script src="/assets/app-123.js"></script><link href="/favicon.svg" rel="icon">',
        encoding="utf-8",
    )

    references = validate_frontend_build(tmp_path)

    assert references == {"assets/app-123.js", "favicon.svg"}


def test_validate_frontend_build_rejects_missing_local_reference(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        '<script src="/assets/missing-123.js"></script>',
        encoding="utf-8",
    )

    with pytest.raises(BuildValidationError, match="missing local files"):
        validate_frontend_build(tmp_path)


def test_release_manifest_lists_only_current_build_assets(tmp_path: Path) -> None:
    manifest_path = tmp_path / "release.json"
    manifest_path.write_text(
        json.dumps({"release": "abc123", "assets": ["assets/app-123.js"]}),
        encoding="utf-8",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["release"] == "abc123"
    assert manifest["assets"] == ["assets/app-123.js"]
