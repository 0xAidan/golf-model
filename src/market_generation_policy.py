"""Persisted allowlist for future market generation, independent of model weights.

Reads never create files or touch the prediction database. Every accepted change
has an immutable revision; only a small current pointer is atomically replaced.
Runs capture one revision at their start. An unreadable policy fails closed for
market selections while leaving rankings and shared data ingestion available.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = "market-generation-policy/v1"
SUPPORTED_MARKETS = (
    ("72h", "Tournament matchups"),
    ("18h", "Round matchups"),
    ("group", "3-ball groups"),
    ("outright", "Outright winner"),
    ("top5", "Top 5"),
    ("top10", "Top 10"),
    ("top20", "Top 20"),
    ("frl", "First-round leader"),
)
SUPPORTED_IDS = tuple(key for key, _ in SUPPORTED_MARKETS)
PLACEMENT_IDS = frozenset({"outright", "top5", "top10", "top20", "frl"})
_ALIASES = {
    "win": "outright", "outrights": "outright", "top_5": "top5",
    "top_10": "top10", "top_20": "top20", "matchup": "72h",
    "tournament_matchups": "72h", "round_matchups": "18h",
    "3ball": "group", "3_balls": "group", "three_ball": "group",
}
NOTE = (
    "Applies to new prediction runs across API, CLI and workers. Runs already in progress "
    "keep their captured policy. Existing mode, model and feature restrictions still apply. "
    "Enabled markets also require provider quotes. Rankings and saved history remain available. "
    "This does not place bets."
)


class PolicyValidationError(ValueError):
    pass


class PolicyUnavailableError(RuntimeError):
    pass


class PolicyRevisionConflict(RuntimeError):
    def __init__(self, current: dict[str, Any]):
        self.current = current
        super().__init__("Market policy changed. Reload before saving.")


def _root() -> Path:
    override = os.environ.get("GOLF_MARKET_GENERATION_POLICY_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    from src.runtime_paths import get_data_dir

    return get_data_dir() / "market-generation-policy"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _validate_markets(markets: Any) -> list[str]:
    if not isinstance(markets, list) or any(not isinstance(key, str) for key in markets):
        raise PolicyValidationError("enabled_markets must be a list of supported market IDs.")
    if len(markets) != len(set(markets)):
        raise PolicyValidationError("enabled_markets must not contain duplicate IDs.")
    if any(key not in SUPPORTED_IDS for key in markets):
        raise PolicyValidationError("enabled_markets contains an unsupported market ID.")
    return [key for key in SUPPORTED_IDS if key in markets]


def _view(document: dict[str, Any] | None) -> dict[str, Any]:
    auth_configured = bool(
        os.environ.get("MARKET_GENERATION_API_KEY", "").strip()
        or os.environ.get("DASHBOARD_API_KEY", "").strip()
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "ready",
        "configured": document is not None,
        "auth_configured": auth_configured,
        "editing_available": auth_configured,
        "revision": document["revision"] if document else "unconfigured",
        "enabled_markets": document["enabled_markets"] if document else list(SUPPORTED_IDS),
        "updated_at": document["created_at"] if document else None,
        "supported_markets": [
            {"id": key, "label": label, "supported": True} for key, label in SUPPORTED_MARKETS
        ] + [
            {"id": key, "label": label, "supported": False, "reason": reason}
            for key, label, reason in (
                ("make_cut", "Make cut", "The current live odds adapter does not support this market."),
                ("miss_cut", "Miss cut", "The current live odds adapter does not support this market."),
                ("top15", "Top 15", "Probability and settlement handling are not enabled for this market."),
            )
        ],
        "applies_to": "future_generation",
        "note": NOTE,
    }


def _read_document(root: Path) -> dict[str, Any] | None:
    pointer = root / "current.json"
    try:
        raw_pointer = pointer.read_bytes()
    except FileNotFoundError:
        if (root / "revisions").is_dir() and any((root / "revisions").iterdir()):
            raise PolicyUnavailableError("The current policy pointer is missing.")
        return None
    if len(raw_pointer) > 1024:
        raise PolicyUnavailableError("Invalid policy pointer.")
    current = json.loads(raw_pointer)
    revision = current.get("revision")
    if not isinstance(revision, str) or len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision):
        raise PolicyUnavailableError("Invalid policy revision.")
    raw = (root / "revisions" / f"{revision}.json").read_bytes()
    if len(raw) > 8192 or hashlib.sha256(raw).hexdigest() != revision:
        raise PolicyUnavailableError("Policy revision verification failed.")
    document = json.loads(raw)
    if document.get("schema_version") != SCHEMA_VERSION:
        raise PolicyUnavailableError("Unsupported policy schema.")
    document["enabled_markets"] = _validate_markets(document.get("enabled_markets"))
    if not isinstance(document.get("created_at"), str):
        raise PolicyUnavailableError("Invalid policy date.")
    document["revision"] = revision
    return document


def get_market_generation_policy() -> dict[str, Any]:
    """Read the current verified policy, or return an explicit fail-closed state."""
    try:
        return _view(_read_document(_root()))
    except (OSError, ValueError, TypeError, AttributeError, PolicyUnavailableError):
        view = _view(None)
        view.update({
            "state": "unavailable", "configured": True, "revision": "unavailable",
            "editing_available": False,
            "enabled_markets": [],
            "error": {"code": "policy_unavailable", "message": "Market generation is paused because its policy could not be verified."},
        })
        return view


def _atomic_pointer(root: Path, revision: str) -> None:
    descriptor, name = tempfile.mkstemp(prefix=".current-", dir=root)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_bytes({"revision": revision}))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, root / "current.json")
        descriptor = os.open(root, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_durable_directory(path: Path) -> None:
    """Persist each directory entry before creating a child beneath it.

    Sync the parent even when another writer won mkdir: its newly visible
    entry may not have reached disk yet. Existing directory modes stay intact.
    """
    if path.is_dir():
        _sync_directory(path.parent)
        return
    if path.parent == path:
        raise NotADirectoryError(str(path))
    _ensure_durable_directory(path.parent)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        if not path.is_dir():
            raise
    _sync_directory(path.parent)


def update_market_generation_policy(*, enabled_markets: Any, expected_revision: Any) -> dict[str, Any]:
    """Accept a complete allowlist with optimistic concurrency and immutable history."""
    enabled = _validate_markets(enabled_markets)
    if not isinstance(expected_revision, str) or not expected_revision:
        raise PolicyValidationError("expected_revision is required.")
    root = _root()
    _ensure_durable_directory(root)
    revisions = root / "revisions"
    _ensure_durable_directory(revisions)
    with (root / ".lock").open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            try:
                prior = _read_document(root)
            except (OSError, ValueError, TypeError, AttributeError, PolicyUnavailableError) as exc:
                raise PolicyUnavailableError("The existing policy could not be verified; no update was made.") from exc
            current = _view(prior)
            if expected_revision != current["revision"]:
                raise PolicyRevisionConflict(current)
            document = {
                "schema_version": SCHEMA_VERSION,
                "enabled_markets": enabled,
                "previous_revision": current["revision"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "change_id": str(uuid4()),
            }
            raw = _canonical_bytes(document)
            revision = hashlib.sha256(raw).hexdigest()
            with (revisions / f"{revision}.json").open("xb") as handle:
                os.chmod(handle.name, 0o600)
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            _sync_directory(revisions)
            _atomic_pointer(root, revision)
            return _view({**document, "revision": revision})
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def market_enabled(market: str, policy: dict[str, Any] | None = None) -> bool:
    """Unknown/unsupported markets are never enabled by the generation policy."""
    captured = policy if policy is not None else get_market_generation_policy()
    return _ALIASES.get(market, market) in captured.get("enabled_markets", [])


def placement_generation_enabled(policy: dict[str, Any]) -> bool:
    return bool(PLACEMENT_IDS.intersection(policy.get("enabled_markets", [])))
