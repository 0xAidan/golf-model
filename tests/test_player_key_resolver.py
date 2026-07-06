"""Unit tests for safe player-key resolution."""

from src.player_key_resolver import resolve_player_key


def test_resolve_player_key_prefers_direct_match():
    result = resolve_player_key(
        player_key="scottie_scheffler",
        player_display="Scottie Scheffler",
        result_keys=["scottie_scheffler", "rory_mcilroy"],
    )

    assert result == {"key": "scottie_scheffler", "method": "direct"}


def test_resolve_player_key_uses_normalized_display_name():
    result = resolve_player_key(
        player_key="jj_spaun_wrong",
        player_display="J.J. Spaun",
        result_keys=["jj_spaun", "rory_mcilroy"],
    )

    assert result == {"key": "jj_spaun", "method": "normalize_name"}


def test_resolve_player_key_uses_dg_id_when_keys_differ():
    result = resolve_player_key(
        player_key="rasmus_neergaard_petersen",
        player_display="Rasmus Neergaard Petersen",
        player_dg_id=424242,
        result_keys=["rasmus_neergaardpetersen", "rory_mcilroy"],
        result_dg_to_key={424242: "rasmus_neergaardpetersen"},
    )

    assert result == {"key": "rasmus_neergaardpetersen", "method": "dg_id"}


def test_resolve_player_key_uses_conservative_fuzzy_single_best_match():
    result = resolve_player_key(
        player_key="rasmus_neergaard_petersen",
        player_display="Rasmus Neergaard Petersen",
        result_keys=["rasmus_neergaardpetersen", "rory_mcilroy"],
    )

    assert result == {"key": "rasmus_neergaardpetersen", "method": "fuzzy"}


def test_resolve_player_key_refuses_low_confidence_fuzzy_match():
    result = resolve_player_key(
        player_key="ryan_gerard",
        player_display="Ryan Gerard",
        result_keys=["ryan_fox", "rory_mcilroy"],
    )

    assert result == {"key": None, "method": "unresolved"}


def test_resolve_player_key_refuses_ambiguous_fuzzy_match():
    result = resolve_player_key(
        player_key="cameron_yongs",
        player_display="Cameron Yongs",
        result_keys=["cameron_young", "cameron_younge"],
    )

    assert result == {"key": None, "method": "unresolved"}
