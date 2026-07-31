"""Build validation and atomic promotion for the operator SPA."""

from __future__ import annotations

import html.parser
import json
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Iterable

from fastapi.staticfiles import StaticFiles


class BuildValidationError(ValueError):
    """Raised when a frontend build cannot be safely promoted."""


class _LocalReferenceParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: set[str] = set()

    def handle_starttag(
        self,
        _tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        for attribute, value in attrs:
            if attribute not in {"href", "src"} or not value:
                continue
            reference = _normalise_local_reference(value)
            if reference is not None:
                self.references.add(reference)


class ImmutableStaticFiles(StaticFiles):
    """Serve fingerprinted assets with a cache lifetime safe for old releases."""

    def file_response(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _normalise_local_reference(value: str) -> str | None:
    reference = value.strip()
    if not reference or reference.startswith(("#", "//", "data:", "mailto:", "tel:")):
        return None
    if "://" in reference:
        return None

    path = reference.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
    normalised = PurePosixPath(path.lstrip("/"))
    if not path or normalised.is_absolute() or ".." in normalised.parts:
        raise BuildValidationError(f"unsafe local reference: {value}")
    return normalised.as_posix()


def _atomic_write(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
        temporary.write(content)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, destination)


def validate_frontend_build(build_dir: Path) -> set[str]:
    """Validate index.html and return every local src/href it references."""

    index_path = build_dir / "index.html"
    if not index_path.is_file():
        raise BuildValidationError(f"missing build entrypoint: {index_path}")

    parser = _LocalReferenceParser()
    parser.feed(index_path.read_text(encoding="utf-8"))
    missing = sorted(reference for reference in parser.references if not (build_dir / reference).is_file())
    if missing:
        raise BuildValidationError(f"index.html references missing local files: {', '.join(missing)}")
    return parser.references


def _copy_file_atomically(source: Path, destination: Path) -> None:
    _atomic_write(destination, source.read_bytes())


def _copy_build_root_files(build_dir: Path, live_dir: Path) -> None:
    for source in build_dir.iterdir():
        if not source.is_file() or source.name == "index.html":
            continue
        _copy_file_atomically(source, live_dir / source.name)


def _copy_static_directories(build_dir: Path, live_dir: Path) -> None:
    for source_directory in build_dir.iterdir():
        if not source_directory.is_dir() or source_directory.name == "assets":
            continue
        for source in source_directory.rglob("*"):
            if source.is_file():
                destination = live_dir / source_directory.name / source.relative_to(source_directory)
                _copy_file_atomically(source, destination)


def _copy_fingerprinted_assets(build_dir: Path, live_dir: Path) -> None:
    source_assets = build_dir / "assets"
    if not source_assets.is_dir():
        return
    for source in source_assets.rglob("*"):
        if source.is_file():
            destination = live_dir / "assets" / source.relative_to(source_assets)
            _copy_file_atomically(source, destination)


def _write_release_manifest(
    live_dir: Path,
    release: str,
    references: Iterable[str],
) -> None:
    if not release or "/" in release or "\\" in release:
        raise BuildValidationError("release identifier must be a non-empty filename")

    payload = {
        "release": release,
        "assets": sorted(reference for reference in references if reference.startswith("assets/")),
    }
    manifest_path = live_dir / "releases" / f"{release}.json"
    _atomic_write(manifest_path, json.dumps(payload, sort_keys=True, indent=2).encode("utf-8"))

    manifests = sorted(
        (live_dir / "releases").glob("*.json"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    for stale_manifest in manifests[3:]:
        stale_manifest.unlink()


def promote_frontend_build(build_dir: Path, live_dir: Path, *, release: str) -> None:
    """Safely publish a verified Vite build without deleting old asset chunks."""

    references = validate_frontend_build(build_dir)
    live_dir.mkdir(parents=True, exist_ok=True)
    _copy_fingerprinted_assets(build_dir, live_dir)
    _copy_build_root_files(build_dir, live_dir)
    _copy_static_directories(build_dir, live_dir)
    _write_release_manifest(live_dir, release, references)
    _atomic_write(live_dir / "index.html", (build_dir / "index.html").read_bytes())


def current_release(live_dir: Path) -> str | None:
    """Return the release recorded by the most recent successful promotion."""

    manifests = sorted(
        (live_dir / "releases").glob("*.json"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    if not manifests:
        return None
    try:
        release = json.loads(manifests[0].read_text(encoding="utf-8")).get("release")
    except (OSError, json.JSONDecodeError):
        return None
    return release if isinstance(release, str) else None


def release_headers(release: str | None) -> dict[str, str]:
    """Headers shared by the SPA document and version endpoint."""

    return {"X-Release-SHA": release} if release else {}
