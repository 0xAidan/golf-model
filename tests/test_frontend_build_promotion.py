from __future__ import annotations

import json
from pathlib import Path

from src.spa_delivery import promote_frontend_build


def _write_build(build_dir: Path, asset_name: str) -> None:
    (build_dir / "assets").mkdir(parents=True)
    (build_dir / "fonts").mkdir()
    (build_dir / "assets" / asset_name).write_text("export default true", encoding="utf-8")
    (build_dir / "fonts" / "operator.woff2").write_bytes(b"font")
    (build_dir / "favicon.svg").write_text("<svg />", encoding="utf-8")
    (build_dir / "index.html").write_text(
        f'<script src="/assets/{asset_name}"></script><link href="/favicon.svg" rel="icon">',
        encoding="utf-8",
    )


def test_promoting_release_b_keeps_release_a_lazy_chunk_available(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    release_a = tmp_path / "release-a"
    release_b = tmp_path / "release-b"
    _write_build(release_a, "lazy-a-123.js")
    _write_build(release_b, "lazy-b-456.js")

    promote_frontend_build(release_a, live_dir, release="release-a")
    promote_frontend_build(release_b, live_dir, release="release-b")

    assert (live_dir / "assets" / "lazy-a-123.js").read_text(encoding="utf-8") == "export default true"
    assert (live_dir / "fonts" / "operator.woff2").read_bytes() == b"font"
    assert "lazy-b-456.js" in (live_dir / "index.html").read_text(encoding="utf-8")


def test_promotion_retains_two_previous_release_manifests(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"

    for release in ("release-a", "release-b", "release-c", "release-d"):
        build_dir = tmp_path / release
        _write_build(build_dir, f"{release}-123.js")
        promote_frontend_build(build_dir, live_dir, release=release)

    manifests = sorted((live_dir / "releases").glob("*.json"))

    assert [path.stem for path in manifests] == ["release-b", "release-c", "release-d"]
    assert json.loads((live_dir / "releases" / "release-d.json").read_text(encoding="utf-8"))["release"] == "release-d"
