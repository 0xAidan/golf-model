"""Tests for the externalized prompt loader (defect register Q6).

Guarantees:
- Each migrated prompt's runtime output still contains the exact backing
  template content (with {...} braces unescaped).
- Placeholders like {tournament}/{event_name} still render when .format()ed.
- load_prompt raises a clear error for unknown templates.
"""

from pathlib import Path

import pytest

from src import prompts as P


PROMPTS_ROOT = Path(__file__).resolve().parent.parent / "prompts" / "v1"


def _read_template(name: str) -> str:
    text = (PROMPTS_ROOT / f"{name}.md").read_text(encoding="utf-8")
    if text.endswith("\n"):
        text = text[:-1]
    return text


# ---------------------------------------------------------------------------
# load_prompt contract
# ---------------------------------------------------------------------------


def test_load_prompt_returns_file_contents():
    got = P.load_prompt("pre_tournament_analysis")
    assert got == _read_template("pre_tournament_analysis")


def test_load_prompt_caches():
    a = P.load_prompt("pre_tournament_analysis")
    b = P.load_prompt("pre_tournament_analysis")
    assert a is b  # same cached string object


def test_load_prompt_missing_raises_clear_error():
    with pytest.raises(FileNotFoundError) as exc:
        P.load_prompt("nonexistent")
    msg = str(exc.value)
    assert "nonexistent" in msg
    assert "prompts/v1/nonexistent.md" in msg


def test_load_prompt_unknown_version_raises():
    with pytest.raises(FileNotFoundError):
        P.load_prompt("pre_tournament_analysis", version="v999")


# ---------------------------------------------------------------------------
# Each prompt's runtime output includes the template's literal content
# (static lines that contain no placeholders) — proves the loader is wired
# up and rendering from disk, not from a stale string literal.
# ---------------------------------------------------------------------------


def _assert_template_lines_present(rendered: str, template_name: str) -> None:
    template = _read_template(template_name)
    # Use a handful of representative static lines (no braces) as anchors.
    for line in template.splitlines():
        stripped = line.strip()
        if not stripped or "{" in line or "}" in line:
            continue
        # Only check substantive lines to avoid spurious matches like "-".
        if len(stripped) < 15:
            continue
        assert stripped in rendered, (
            f"Expected template line from {template_name}.md to appear in "
            f"rendered output:\n  {stripped!r}"
        )


def test_pre_tournament_analysis_renders_template():
    out = P.pre_tournament_analysis("Masters", "Augusta National",
                                    field_data=[{"player": "a"}])
    assert "Masters" in out
    assert "Augusta National" in out
    _assert_template_lines_present(out, "pre_tournament_analysis")


def test_post_tournament_review_renders_template():
    out = P.post_tournament_review("Masters",
                                   predictions=[{"p": 1}],
                                   actual_results=[{"r": 1}],
                                   bets_placed=[{"b": 1}])
    assert "Masters" in out
    _assert_template_lines_present(out, "post_tournament_review")


def test_hypothesis_generation_renders_template():
    out = P.hypothesis_generation({"ok": 1}, [{"pat": 1}], [{"exp": 1}])
    _assert_template_lines_present(out, "hypothesis_generation")


def test_outlier_investigation_renders_template():
    out = P.outlier_investigation("Scottie Scheffler", "Masters", 3, "T45")
    assert "Scottie Scheffler" in out
    assert "Masters" in out
    _assert_template_lines_present(out, "outlier_investigation")


def test_weather_impact_assessment_renders_template():
    out = P.weather_impact_assessment("Open", "St Andrews",
                                      weather_data={"wind": 20},
                                      field=[{"p": "a"}])
    assert "Open" in out
    assert "St Andrews" in out
    _assert_template_lines_present(out, "weather_impact_assessment")


def test_intel_analysis_renders_template():
    out = P.intel_analysis(raw_intel=[{"t": "news"}])
    _assert_template_lines_present(out, "intel_analysis")


def test_course_profiling_renders_template():
    out = P.course_profiling("Augusta National")
    assert "Augusta National" in out
    _assert_template_lines_present(out, "course_profiling")


def test_system_default_prompt_matches_file():
    system = _read_template("system_default")
    # Rendered via wrap_for_provider when system_message is None.
    wrapped = P.wrap_for_provider("hi")
    assert wrapped["messages"][0]["content"] == system


# ---------------------------------------------------------------------------
# Placeholder rendering still works (the {tournament}-style tokens in the
# task description map to {event_name}/{course_name}/etc in our templates).
# ---------------------------------------------------------------------------


def test_placeholders_are_substituted_not_literal():
    tournament = "Sentry Tournament of Champions"
    course = "Kapalua Plantation"
    out = P.pre_tournament_analysis(tournament, course, field_data=[])
    assert tournament in out
    assert course in out
    # The raw {event_name} token must NOT leak into output.
    assert "{event_name}" not in out
    assert "{course_name}" not in out


def test_template_json_braces_are_unescaped_in_output():
    """Templates use {{ and }} for literal braces; .format() must emit { and }."""
    out = P.pre_tournament_analysis("E", "C", field_data=[])
    # The JSON schema in the template ends with a literal "}".
    assert out.rstrip().endswith("}")
    # And the double-brace {{ from the template must have collapsed to single {.
    assert "{{" not in out
    assert "}}" not in out


# ---------------------------------------------------------------------------
# Disabled prompt still returns None (preserved contract)
# ---------------------------------------------------------------------------


def test_betting_decision_still_disabled():
    assert P.betting_decision(value_bets=[{"b": 1}]) is None
