"""Prompt builder contract tests (plan.md A8)."""

from app.config import Settings
from app.domain.enums import Platform, StepStatus
from app.domain.findings import BLOCK_ERROR, EvidenceBlock, Findings, Step
from app.prompting.builder import PromptBuilder


def _sample_findings() -> Findings:
    return Findings(
        platform=Platform.WEB,
        bank="demo",
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
        missing_evidence=["BrowserLogEvidence"],
    )


def test_prompt_contains_evidence_and_constraints(settings: Settings) -> None:
    builder = PromptBuilder(settings.prompt_template_path, settings.confidence_buckets)
    prompt = builder.build(_sample_findings())

    # identity/context lines (MockLLMProvider relies on the Senaryo: prefix)
    assert "Platform: web" in prompt
    assert "Banka: demo" in prompt
    assert "Senaryo: Login - geçerli kullanıcı" in prompt
    # organized evidence
    assert "Giriş butonuna tıkla" in prompt
    assert "NoSuchElementException" in prompt
    assert "=== HATA ===" in prompt
    assert "- Login sayfasını aç: PASSED" in prompt
    # missing-evidence notification
    assert "BrowserLogEvidence" in prompt
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


def test_confidence_buckets_come_from_config(settings: Settings) -> None:
    builder = PromptBuilder(settings.prompt_template_path, settings.confidence_buckets)
    prompt = builder.build(_sample_findings())

    assert "0.1 / 0.25 / 0.5 / 0.75 / 0.99" in prompt


def test_no_unfilled_placeholders(settings: Settings) -> None:
    builder = PromptBuilder(settings.prompt_template_path, settings.confidence_buckets)
    prompt = builder.build(_sample_findings())

    for placeholder in (
        "$platform",
        "$bank",
        "$scenario_name",
        "$failed_step",
        "$error_message",
        "$steps",
        "$missing_evidence",
        "$evidence_blocks",
        "$confidence_buckets",
    ):
        assert placeholder not in prompt
