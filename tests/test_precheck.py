"""PreCheck tests (plan.md A7): NoOp never short-circuits; rules do — carefully."""

import json
from pathlib import Path

import pytest

from app.domain.findings import EvidenceBlock, Findings
from app.precheck.noop import NoOpPreCheck
from app.precheck.rule_based import RuleBasedPreCheck
from app.precheck.rules import load_rules

_DB_RULE = {
    "name": "db_credentials",
    "match": "ORA-01017|invalid credentials",
    "verdict": "environment_error",
    "confidence": 0.99,
    "suggestion": "Lütfen veritabanı bilgilerinizi güncelleyin.",
    "explanation": "Veritabanı kimlik bilgileri geçersiz.",
    "error_signature": "db-credentials",
}


def _write(tmp_path: Path, rules: list[dict]) -> Path:
    path = tmp_path / "precheck_rules.json"
    path.write_text(json.dumps(rules), encoding="utf-8")
    return path


def _findings(error: str = "", blocks: list[str] | None = None) -> Findings:
    return Findings(
        scenario_name="S",
        error_message=error,
        evidence_blocks=[EvidenceBlock(label="ADIMLAR", content=text) for text in (blocks or [])],
    )


def test_noop_precheck_always_returns_none() -> None:
    assert NoOpPreCheck().check(_findings(error="ORA-01017")) is None


def test_empty_rule_list_never_matches(tmp_path: Path) -> None:
    precheck = RuleBasedPreCheck(load_rules(_write(tmp_path, [])))
    assert precheck.check(_findings(error="ORA-01017")) is None


def test_matching_rule_returns_canned_answer(tmp_path: Path) -> None:
    precheck = RuleBasedPreCheck(load_rules(_write(tmp_path, [_DB_RULE])))

    result = precheck.check(_findings(error="ORA-01017: invalid username/password"))

    assert result is not None
    assert result.verdict.value == "environment_error"
    assert result.confidence == 0.99
    assert result.suggestion == "Lütfen veritabanı bilgilerinizi güncelleyin."
    assert result.scenario_name == "S"  # identity from the scenario
    assert result.error_signature == "db-credentials"  # which rule answered


def test_non_matching_error_goes_to_llm(tmp_path: Path) -> None:
    precheck = RuleBasedPreCheck(load_rules(_write(tmp_path, [_DB_RULE])))
    assert precheck.check(_findings(error="NoSuchElementException: #btn")) is None


def test_search_in_evidence_looks_at_blocks(tmp_path: Path) -> None:
    rule = {**_DB_RULE, "search_in": "evidence"}
    precheck = RuleBasedPreCheck(load_rules(_write(tmp_path, [rule])))

    # Pattern is only in the log block, not in the error message.
    assert precheck.check(_findings(error="genel hata", blocks=["ORA-01017 at db"]))
    # Default (error_message) would not see it.
    default = RuleBasedPreCheck(load_rules(_write(tmp_path, [_DB_RULE])))
    assert default.check(_findings(error="genel hata", blocks=["ORA-01017"])) is None


def test_first_matching_rule_wins(tmp_path: Path) -> None:
    first = {**_DB_RULE, "name": "first", "error_signature": "first"}
    second = {**_DB_RULE, "name": "second", "error_signature": "second"}
    precheck = RuleBasedPreCheck(load_rules(_write(tmp_path, [first, second])))

    result = precheck.check(_findings(error="ORA-01017"))
    assert result is not None and result.error_signature == "first"


def test_name_falls_back_as_signature(tmp_path: Path) -> None:
    rule = {k: v for k, v in _DB_RULE.items() if k != "error_signature"}
    precheck = RuleBasedPreCheck(load_rules(_write(tmp_path, [rule])))
    result = precheck.check(_findings(error="ORA-01017"))
    assert result is not None and result.error_signature == "db_credentials"


# --- fail-fast config validation --------------------------------------------


@pytest.mark.parametrize(
    "bad,expected",
    [
        ({**_DB_RULE, "match": "[unclosed"}, "invalid regex"),
        ({**_DB_RULE, "verdict": "boyle_bir_verdict_yok"}, "unknown verdict"),
        ({**_DB_RULE, "confidence": 0.73}, "confidence must be one of"),
        ({**_DB_RULE, "name": "  "}, "must not be empty"),
    ],
)
def test_bad_rule_fails_at_load(tmp_path: Path, bad: dict, expected: str) -> None:
    with pytest.raises(ValueError, match=expected):
        load_rules(_write(tmp_path, [bad]))


def test_non_list_config_fails(tmp_path: Path) -> None:
    path = tmp_path / "precheck_rules.json"
    path.write_text(json.dumps({"name": "x"}), encoding="utf-8")
    with pytest.raises(ValueError, match="JSON list"):
        load_rules(path)
