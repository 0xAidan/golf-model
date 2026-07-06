"""Resolve pick-side player keys onto result-side player keys safely."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Iterable, Mapping

from src.player_normalizer import normalize_name

FUZZY_MATCH_THRESHOLD = 0.91
FUZZY_MATCH_GAP = 0.03
FUZZY_COMPACT_THRESHOLD = 0.96


def resolve_player_key(
    *,
    player_key: str | None,
    player_display: str | None,
    player_dg_id: int | None = None,
    result_keys: Iterable[str],
    result_dg_to_key: Mapping[int, str] | None = None,
) -> dict[str, str | None]:
    """Resolve a pick-side player reference onto a result-side player key.

    Resolution ladder:
      1. direct key match
      2. normalize_name(player_display)
      3. dg_id lookup
      4. conservative fuzzy single-best match
    """

    candidate_keys = tuple(dict.fromkeys(_clean_key(key) for key in result_keys if _clean_key(key)))
    direct_key = _clean_key(player_key)
    display_key = normalize_name(player_display or "")

    if direct_key and direct_key in candidate_keys:
        return {"key": direct_key, "method": "direct"}

    if display_key and display_key in candidate_keys:
        return {"key": display_key, "method": "normalize_name"}

    if player_dg_id is not None and result_dg_to_key:
        resolved_key = result_dg_to_key.get(int(player_dg_id))
        if resolved_key:
            return {"key": resolved_key, "method": "dg_id"}

    fuzzy_source = display_key or direct_key
    if fuzzy_source:
        fuzzy_key = _resolve_conservative_fuzzy(fuzzy_source, candidate_keys)
        if fuzzy_key:
            return {"key": fuzzy_key, "method": "fuzzy"}

    return {"key": None, "method": "unresolved"}


def _resolve_conservative_fuzzy(source_key: str, candidate_keys: Iterable[str]) -> str | None:
    matches: list[tuple[float, str]] = []
    for candidate in candidate_keys:
        if not _is_viable_fuzzy_candidate(source_key, candidate):
            continue
        score = SequenceMatcher(None, source_key, candidate).ratio()
        if score >= FUZZY_MATCH_THRESHOLD:
            matches.append((score, candidate))

    if not matches:
        return None

    matches.sort(key=lambda item: (-item[0], item[1]))
    best_score, best_key = matches[0]
    if len(matches) == 1:
        return best_key

    second_score = matches[1][0]
    if best_score - second_score < FUZZY_MATCH_GAP:
        return None
    return best_key


def _is_viable_fuzzy_candidate(source_key: str, candidate_key: str) -> bool:
    source_tokens = [token for token in source_key.split("_") if token]
    candidate_tokens = [token for token in candidate_key.split("_") if token]
    if not source_tokens or not candidate_tokens:
        return False

    if source_tokens[0][0] != candidate_tokens[0][0]:
        return False

    if source_tokens[-1] == candidate_tokens[-1]:
        return True

    source_compact = "".join(source_tokens)
    candidate_compact = "".join(candidate_tokens)
    return SequenceMatcher(None, source_compact, candidate_compact).ratio() >= FUZZY_COMPACT_THRESHOLD


def _clean_key(raw_key: str | None) -> str:
    return str(raw_key or "").strip().lower()
