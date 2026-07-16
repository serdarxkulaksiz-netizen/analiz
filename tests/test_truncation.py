"""Size-management tests: passthrough default, priority order, visible flag."""

from app.domain.enums import Platform
from app.domain.findings import (
    BLOCK_CONSOLE,
    BLOCK_DOM,
    BLOCK_ERROR,
    EvidenceBlock,
    Findings,
)
from app.extraction.truncation import estimate_tokens, truncate_findings


def _findings() -> Findings:
    return Findings(
        platform=Platform.WEB,
        scenario_name="s",
        failed_step="Giriş butonuna tıkla",
        error_message="NoSuchElementException",
        ui_excerpt="U" * 100,
        evidence_blocks=[
            EvidenceBlock(label=BLOCK_ERROR, content="E" * 100),
            EvidenceBlock(label=BLOCK_DOM, content="D" * 100),
            EvidenceBlock(label=BLOCK_CONSOLE, content="C" * 100),
        ],
    )


def _block(findings: Findings, label: str) -> str:
    return next(b.content for b in findings.evidence_blocks if b.label == label)


def test_estimate_tokens_uses_configured_ratio() -> None:
    assert estimate_tokens("", 4) == 0
    assert estimate_tokens("abcd" * 10, 4) == 10
    assert estimate_tokens("abc", 4) == 1  # rounds up


def test_console_is_cut_first_and_error_never() -> None:
    truncated, note = truncate_findings(_findings(), chars_to_cut=50)

    assert len(_block(truncated, BLOCK_CONSOLE)) == 50
    assert _block(truncated, BLOCK_DOM) == "D" * 100  # untouched
    assert _block(truncated, BLOCK_ERROR) == "E" * 100  # never cut
    assert truncated.failed_step == "Giriş butonuna tıkla"
    assert truncated.error_message == "NoSuchElementException"
    assert BLOCK_CONSOLE in note


def test_dom_is_cut_after_console_exhausted() -> None:
    truncated, note = truncate_findings(_findings(), chars_to_cut=150)

    assert _block(truncated, BLOCK_CONSOLE) == ""
    assert len(_block(truncated, BLOCK_DOM)) == 50
    assert _block(truncated, BLOCK_ERROR) == "E" * 100
    assert BLOCK_CONSOLE in note and BLOCK_DOM in note


def test_ui_excerpt_is_cut_last_error_still_intact() -> None:
    truncated, note = truncate_findings(_findings(), chars_to_cut=250)

    assert _block(truncated, BLOCK_CONSOLE) == ""
    assert _block(truncated, BLOCK_DOM) == ""
    assert len(truncated.ui_excerpt) == 50
    assert _block(truncated, BLOCK_ERROR) == "E" * 100
    assert "ui_excerpt" in note


def test_original_findings_object_is_not_mutated() -> None:
    original = _findings()
    truncate_findings(original, chars_to_cut=300)

    assert _block(original, BLOCK_CONSOLE) == "C" * 100
    assert original.ui_excerpt == "U" * 100
