"""EvidenceExtractor tests: RawScenario -> Findings (plan.md A5, A6)."""

import pytest

from app.domain.enums import StepStatus
from app.domain.findings import (
    BLOCK_BROWSER,
    BLOCK_BUILD,
    BLOCK_DOM,
    BLOCK_ERROR,
    BLOCK_STEPS,
    Step,
)
from app.extraction.evidence_extractor import EvidenceExtractor
from app.source.models import Attachment, RawScenario


def _att(mime: str, device: str, content: str = "x", path: str = "") -> Attachment:
    return Attachment(
        file_name=f"{device}.file",
        mime_type=mime,
        device_id=device,
        content=content,
        stored_path=path,
    )


def _scenario(**overrides: object) -> RawScenario:
    base = dict(
        scenario_name="Senaryo",
        error_text="NoSuchElementException: #btn",
        steps=[
            Step(name="Adım bir", status=StepStatus.PASSED),
            Step(name="Adım iki", status=StepStatus.FAILED),
        ],
        attachments=[
            _att("text/plain", "test", "test log"),
            _att("text/plain", "browser.default", "browser log"),
            _att("text/html", "browser.default", "<html/>"),
            _att("image/png", "browser.default", "", "web.png"),
        ],
        raw_detail={"properties": {"x": "1"}},
    )
    base.update(overrides)
    return RawScenario(**base)  # type: ignore[arg-type]


def test_default_profile_full_findings(extractor: EvidenceExtractor) -> None:
    findings = extractor.extract(_scenario())

    assert findings.parameter1 == "default"
    assert findings.parameter2 == "default"
    assert findings.failed_step == "Adım iki"  # first FAILED step
    assert findings.error_message == "NoSuchElementException: #btn"
    labels = [b.label for b in findings.evidence_blocks]
    assert BLOCK_STEPS in labels  # test.log
    assert BLOCK_BROWSER in labels
    assert BLOCK_DOM in labels
    assert BLOCK_ERROR in labels  # HATA = error_text
    assert findings.screenshot_paths == ["web.png"]


def test_parameters_are_stamped(extractor: EvidenceExtractor) -> None:
    # parameter2 is free text (recorded only); parameter1 must name a profile.
    findings = extractor.extract(_scenario(), parameter2="tipY")
    assert findings.parameter1 == "default"
    assert findings.parameter2 == "tipY"
    assert findings.profile_name == "default"
    labels = [b.label for b in findings.evidence_blocks]
    assert BLOCK_DOM in labels and BLOCK_BROWSER in labels


def test_unknown_profile_name_raises(extractor: EvidenceExtractor) -> None:
    # Loud failure instead of silently analyzing with the wrong profile.
    with pytest.raises(ValueError, match="Unknown profile"):
        extractor.extract(_scenario(), parameter1="boyle-profil-yok")


def test_missing_evidence_gets_placeholder_block(
    extractor: EvidenceExtractor,
) -> None:
    """Profile wants DOM but it never arrived -> block stays, says so."""
    scenario = _scenario(
        attachments=[_att("text/plain", "test", "test log")]  # no html at all
    )
    findings = extractor.extract(scenario)

    dom = next(b for b in findings.evidence_blocks if b.label == BLOCK_DOM)
    assert "alınamadı" in dom.content
    # Present evidence is untouched.
    steps = next(b for b in findings.evidence_blocks if b.label == BLOCK_STEPS)
    assert steps.content == "test log"


def test_empty_evidence_also_gets_placeholder(extractor: EvidenceExtractor) -> None:
    # Attachment arrived but the download failed -> empty content, same result.
    scenario = _scenario(
        attachments=[
            _att("text/plain", "test", "test log"),
            _att("text/html", "browser.default", ""),
        ]
    )
    findings = extractor.extract(scenario)
    dom = next(b for b in findings.evidence_blocks if b.label == BLOCK_DOM)
    assert "alınamadı" in dom.content


def test_build_log_is_profile_controlled(extractor: EvidenceExtractor) -> None:
    # The default profile does NOT send the job-level build log (it holds all
    # scenarios and would bloat every prompt); a profile must opt in.
    findings = extractor.extract(_scenario(), build_log="build out")
    assert not [b for b in findings.evidence_blocks if b.label == BLOCK_BUILD]
