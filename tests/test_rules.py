"""Content rule tests — each rule type, including the A/B/C/D job needs."""

import pytest
from pydantic import ValidationError

from app.evidence.rules import RuleContext, RuleError, build_rule

_CTX = RuleContext(scenario_name="Senaryo B")


def _apply(config: dict, text: str, ctx: RuleContext = _CTX) -> str:
    return build_rule(config).apply(text, ctx)


# --- keep_scenario_section (job C: slice a job-level log per scenario) -------

_JOB_LOG = """[jenkins] build started
Scenario: Senaryo A
  A adım 1
  A adım 2 FAILED
Scenario: Senaryo B
  B adım 1
  B adım 2 FAILED
Scenario: Senaryo C
  C adım 1"""


def test_keep_scenario_section_slices_only_own_part() -> None:
    out = _apply(
        {
            "type": "keep_scenario_section",
            "start": "Scenario: {scenario_name}",
            "end": "Scenario: ",
        },
        _JOB_LOG,
    )
    assert "Senaryo B" in out and "B adım 2 FAILED" in out
    assert "Senaryo A" not in out and "Senaryo C" not in out


def test_keep_scenario_section_without_a_match_raises() -> None:
    """A marker that does not match is a fact somebody has to see.

    Returning the whole text looked harmless and was not: every scenario of the
    run then carried the entire job log (measured: 38.889 characters × 40
    scenarios) while `profiles.json` still read "sliced per scenario". The error
    names the marker it looked for and how much it could not cut.
    """
    with pytest.raises(RuleError) as caught:
        _apply(
            {"type": "keep_scenario_section", "start": "Scenario: {scenario_name}"},
            "hiç eşleşme yok",
        )

    message = str(caught.value)
    assert "keep_scenario_section" in message  # which rule failed
    assert "Scenario: Senaryo B" in message  # what it looked for
    assert "karakter" in message  # and how much stayed unsliced


def test_collapse_whitespace_squeezes_indentation() -> None:
    """Markup dumps are mostly indentation; it is not evidence."""
    assert _apply({"type": "collapse_whitespace"}, "a      b\n\n\n\nc") == "a b\n\nc"


# --- markup rules ----------------------------------------------------

_HTML = """<html><body>
<script>var x = 1; if (a<b) {}</script>
<style>.a{color:red}</style>
<LinearLayout id="first"><Button>Tamam</Button></LinearLayout>
<LinearLayout id="second"><Button>İptal</Button></LinearLayout>
<LinearLayout id="third"/>
<LinearLayout id="fourth"></LinearLayout>
</body></html>"""


def test_strip_tags_removes_tag_with_subtree() -> None:
    out = _apply({"type": "strip_tags", "tags": ["script", "style"]}, _HTML)
    assert "var x" not in out and "color:red" not in out
    assert "<LinearLayout" in out  # rest survives
    assert "Tamam" in out


def test_strip_tags_handles_void_tags_without_eating_rest() -> None:
    out = _apply({"type": "strip_tags", "tags": ["br"]}, "<p>a<br>b</p>")
    assert "a" in out and "b" in out and "<br>" not in out


# --- registry / fail-fast ----------------------------------------------------


def test_unknown_rule_type_raises() -> None:
    with pytest.raises(ValueError, match="Unknown rule type"):
        build_rule({"type": "boyle_bir_kural_yok"})


def test_bad_params_raise() -> None:
    with pytest.raises(ValueError, match="Invalid config"):
        build_rule({"type": "strip_tags"})  # missing tags
    with pytest.raises(ValueError, match="Invalid config"):
        build_rule({"type": "strip_tags", "tags": ["script"], "n": 5})  # unknown param


def test_rules_apply_in_order() -> None:
    """The profile lists rules in order, and order changes the result."""
    stripped = _apply({"type": "strip_tags", "tags": ["script", "style"]}, _HTML)
    out = _apply({"type": "collapse_whitespace"}, stripped)

    assert "var x = 1" not in out  # the script went first
    assert "Tamam" in out and "İptal" in out  # the content survived
    assert "\n\n\n" not in out  # and the holes it left were squeezed


def test_rule_context_rejects_unknown_fields() -> None:
    """An unknown field must fail loudly, not be swallowed.

    Regression: the extractor used to pass `error_text=` to RuleContext, which
    has no such field. Pydantic ignored it silently, so the value never reached
    any rule and nothing complained (found by mypy, not by tests).
    """
    with pytest.raises(ValidationError):
        RuleContext(scenario_name="S", error_text="bu alan yok")


_REAL_BUILD_LOG = """beforeScenario:63 - [2]  > Scenario [Senaryo A] started
  A adım 1
beforeScenario:63 - [2]  > Scenario [Senaryo B] started
  B adım 1
  B adım 2 FAILED
beforeScenario:63 - [2]  > Scenario [Senaryo C] started
  C adım 1"""


def test_keep_scenario_section_uses_the_build_log_format_by_default() -> None:
    """Config asks for the rule; the markers live with the code that knows them.

    They describe VisiumGo's build.log FORMAT, which is the same for every job —
    repeating them in each profile only invites a typo that silently sends the
    whole job log for that one job.
    """
    out = _apply({"type": "keep_scenario_section"}, _REAL_BUILD_LOG)

    assert "B adım 2 FAILED" in out
    assert "A adım 1" not in out and "C adım 1" not in out


def test_keep_scenario_section_markers_can_still_be_overridden() -> None:
    """A job whose log looks different stays a config change, not a code change."""
    other_format = "### baslangic Senaryo B ###\nB satırı\n### baslangic Senaryo C ###\nC satırı"

    out = _apply(
        {
            "type": "keep_scenario_section",
            "start": "### baslangic {scenario_name} ###",
            "end": "### baslangic",
        },
        other_format,
    )

    assert "B satırı" in out and "C satırı" not in out


def test_empty_end_marker_keeps_everything_after_the_start() -> None:
    out = _apply({"type": "keep_scenario_section", "end": ""}, _REAL_BUILD_LOG)

    assert "B adım 2 FAILED" in out
    assert "C adım 1" in out  # explicit "" = to the end of the file
    assert "A adım 1" not in out
