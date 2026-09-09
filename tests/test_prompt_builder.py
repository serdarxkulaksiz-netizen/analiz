"""Prompt builder contract tests (plan.md A8) — per-profile templates."""

from pathlib import Path

import pytest

from app.config import Settings
from app.domain.enums import StepStatus
from app.domain.findings import (
    BLOCK_BUILD,
    BLOCK_DOM,
    BLOCK_ERROR,
    EvidenceBlock,
    Findings,
    Step,
)
from app.prompting.builder import PromptBuilder


def _sample_findings(**overrides: object) -> Findings:
    findings = Findings(
        parameter1="projeX",
        parameter2="tipY",
        scenario_name="Login - geçerli kullanıcı",
        failed_step="Giriş butonuna tıkla",
        error_message="NoSuchElementException: #login-submit",
        steps=[
            Step(name="Login sayfasını aç", status=StepStatus.PASSED),
            Step(name="Giriş butonuna tıkla", status=StepStatus.FAILED),
        ],
        evidence_blocks=[
            EvidenceBlock(label=BLOCK_ERROR, content="NoSuchElementException"),
        ],
    )
    return findings.model_copy(update=overrides)


def _builder(settings: Settings) -> PromptBuilder:
    return PromptBuilder(settings.prompts_dir, settings.confidence_buckets)


def test_prompt_contains_evidence_and_constraints(settings: Settings) -> None:
    prompt = _builder(settings).build(_sample_findings())

    # identity/context lines (MockLLMProvider relies on the Senaryo: prefix)
    assert "Senaryo: Login - geçerli kullanıcı" in prompt
    # parameter1/parameter2 are carried, but deliberately NOT written into the
    # prompt any more: in most runs they literally said "default".
    assert "projeX" not in prompt and "tipY" not in prompt
    # organized evidence
    assert "Giriş butonuna tıkla" in prompt
    assert "NoSuchElementException" in prompt
    assert "=== HATA ===" in prompt
    assert "- Login sayfasını aç: PASSED" in prompt
    # mandatory output contract — all 6 verdict values
    for verdict in (
        "test_maintenance",
        "application_bug",
        "environment_error",
        "transient_error",
        "unknown",
        "inconclusive",
    ):
        assert verdict in prompt
    assert "most_relevant_log_lines" in prompt


def test_every_template_carries_the_shared_contract(settings: Settings) -> None:
    """The JSON schema is written once and appended to all templates.

    Regression guard for the reason it is shared at all: five hand-maintained
    copies drift, and a drifted verdict list breaks parsing silently.
    """
    builder = _builder(settings)
    assert builder.template_names == {"default", "web", "mobile", "hybrid", "buildlog"}

    for name in builder.template_names:
        prompt = builder.build(_sample_findings(prompt_template=name))
        assert "JSON ŞEMASI:" in prompt
        assert "inconclusive" in prompt
        assert "0.1 / 0.25 / 0.5 / 0.75 / 0.99" in prompt


def test_profile_template_decides_which_evidence_fields_appear(settings: Settings) -> None:
    """Each template shows only the evidence its job group actually produces."""
    findings = _sample_findings(
        prompt_template="buildlog",
        evidence_blocks=[EvidenceBlock(label=BLOCK_BUILD, content="BUILD FAILED: gradle")],
    )
    prompt = _builder(settings).build(findings)

    assert "=== BUILD LOG ===\nBUILD FAILED: gradle" in prompt
    assert "=== DOM" not in prompt  # not part of this template at all


def test_missing_evidence_takes_its_header_with_it(settings: Settings) -> None:
    """A block that did not arrive leaves NO trace in the prompt — header included.

    A heading over an empty space is still something the model has to explain
    to itself, and the template then had to spend a paragraph on the marker.
    """
    prompt = _builder(settings).build(_sample_findings(prompt_template="web"))

    assert "=== DOM ===" not in prompt
    assert "=== BROWSER LOG ===" not in prompt
    assert "\n\n\n" not in prompt  # the hole is closed, not left gaping


def test_evidence_block_reaches_its_own_placeholder(settings: Settings) -> None:
    findings = _sample_findings(
        prompt_template="web",
        evidence_blocks=[EvidenceBlock(label=BLOCK_DOM, content="<html>login</html>")],
    )
    prompt = _builder(settings).build(findings)

    assert "<html>login</html>" in prompt


def test_no_unfilled_placeholders(settings: Settings) -> None:
    builder = _builder(settings)
    for name in builder.template_names:
        prompt = builder.build(_sample_findings(prompt_template=name))
        assert "$" not in prompt


def test_unknown_template_name_fails(settings: Settings) -> None:
    builder = _builder(settings)

    # At startup, when a profile names a template that does not exist...
    with pytest.raises(ValueError, match="unknown prompt template"):
        builder.ensure_templates_exist({"default", "yok-boyle-sablon"})
    # ...and defensively at build time too.
    with pytest.raises(ValueError, match="Unknown prompt template"):
        builder.build(_sample_findings(prompt_template="yok-boyle-sablon"))


def test_unknown_placeholder_in_a_template_fails_at_startup(
    settings: Settings, tmp_path: Path
) -> None:
    """A typo'd `$placeholder` would otherwise be sent to the LLM verbatim."""
    (tmp_path / "_contract.txt").write_text("JSON ŞEMASI: {}", encoding="utf-8")
    (tmp_path / "default.txt").write_text("Senaryo: $scenario_name", encoding="utf-8")
    (tmp_path / "bozuk.txt").write_text("DOM: $dom_excerpt", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown placeholder"):
        PromptBuilder(tmp_path, settings.confidence_buckets)


def test_missing_contract_or_default_fails_at_startup(settings: Settings, tmp_path: Path) -> None:
    (tmp_path / "web.txt").write_text("Senaryo: $scenario_name", encoding="utf-8")

    with pytest.raises(ValueError, match="contract"):
        PromptBuilder(tmp_path, settings.confidence_buckets)

    (tmp_path / "_contract.txt").write_text("JSON ŞEMASI: {}", encoding="utf-8")
    with pytest.raises(ValueError, match="default.txt"):
        PromptBuilder(tmp_path, settings.confidence_buckets)
