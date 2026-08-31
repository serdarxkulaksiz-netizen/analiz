"""Content rule tests — each rule type, including the A/B/C/D job needs."""

import pytest

from app.evidence.rules import RuleContext, build_rule

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


def test_keep_scenario_section_without_match_keeps_text() -> None:
    out = _apply(
        {"type": "keep_scenario_section", "start": "Scenario: {scenario_name}"},
        "hiç eşleşme yok",
    )
    assert out == "hiç eşleşme yok"  # never silently empties


# --- line rules --------------------------------------------------------------


def test_keep_last_and_first_lines() -> None:
    text = "\n".join(str(i) for i in range(10))
    assert _apply({"type": "keep_last_lines", "n": 3}, text) == "7\n8\n9"
    assert _apply({"type": "keep_first_lines", "n": 2}, text) == "0\n1"
    # Shorter than n -> untouched
    assert _apply({"type": "keep_last_lines", "n": 99}, text) == text


def test_drop_and_keep_matching() -> None:
    text = "INFO ok\nDEBUG noise\nERROR patladı"
    assert _apply({"type": "drop_matching", "patterns": ["DEBUG"]}, text) == (
        "INFO ok\nERROR patladı"
    )
    assert _apply({"type": "keep_matching", "patterns": ["ERROR"]}, text) == (
        "ERROR patladı"
    )


def test_max_chars_and_collapse_whitespace() -> None:
    assert _apply({"type": "max_chars", "n": 5}, "0123456789").startswith("01234")
    assert _apply({"type": "max_chars", "n": 99}, "kısa") == "kısa"
    assert _apply({"type": "collapse_whitespace"}, "a      b\n\n\n\nc") == "a b\n\nc"


# --- markup rules (job D) ----------------------------------------------------

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


def test_select_nth_takes_first_linearlayout_with_subtree() -> None:
    # Job D: "4 LinearLayout gelecek, ilkini al"
    out = _apply(
        {"type": "select_nth", "match": {"tag": "LinearLayout"}, "index": 0}, _HTML
    )
    assert "Tamam" in out  # first one's subtree
    assert "İptal" not in out and "second" not in out
    assert "<script>" not in out


def test_select_nth_second_element() -> None:
    out = _apply(
        {"type": "select_nth", "match": {"tag": "LinearLayout"}, "index": 1}, _HTML
    )
    assert "İptal" in out and "Tamam" not in out


def test_select_nth_by_class() -> None:
    html = '<div class="a">bir</div><div class="target">iki</div>'
    out = _apply(
        {"type": "select_nth", "match": {"tag": "div", "class": "target"}}, html
    )
    assert "iki" in out and "bir" not in out


def test_select_nth_without_match_keeps_text() -> None:
    out = _apply({"type": "select_nth", "match": {"tag": "yoktur"}}, _HTML)
    assert out == _HTML


# --- registry / fail-fast ----------------------------------------------------


def test_unknown_rule_type_raises() -> None:
    with pytest.raises(ValueError, match="Unknown rule type"):
        build_rule({"type": "boyle_bir_kural_yok"})


def test_bad_params_raise() -> None:
    with pytest.raises(ValueError, match="Invalid config"):
        build_rule({"type": "keep_last_lines"})  # missing n
    with pytest.raises(ValueError, match="Invalid config"):
        build_rule({"type": "drop_matching", "patterns": ["[unclosed"]})  # bad regex


def test_rules_apply_in_order() -> None:
    # strip script first, then take the first LinearLayout
    text = _apply({"type": "strip_tags", "tags": ["script", "style"]}, _HTML)
    out = _apply(
        {"type": "select_nth", "match": {"tag": "LinearLayout"}, "index": 0}, text
    )
    assert "Tamam" in out and "İptal" not in out
