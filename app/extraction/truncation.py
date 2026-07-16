"""Coarse, conditional, prioritized size management (plan.md A5).

Default is passthrough (threshold 0 = never cut). When the rendered prompt
exceeds the configured token threshold, evidence is trimmed automatically
(async flow is never blocked to ask):

    priority: failed step + error message are NEVER cut;
    CONSOLE.LOG noise goes first (keep the tail — most recent lines),
    then DOM (keep the head), then ui_excerpt.

Any cut raises a visible flag: truncated=True + truncated_note.
"""

import math

from app.domain.findings import BLOCK_CONSOLE, BLOCK_DOM, Findings


def estimate_tokens(text: str, chars_per_token: int) -> int:
    """Rough token estimate; the real ratio is tuned on the work PC (A13)."""
    if not text:
        return 0
    return math.ceil(len(text) / max(1, chars_per_token))


def truncate_findings(findings: Findings, chars_to_cut: int) -> tuple[Findings, str]:
    """Cut roughly `chars_to_cut` characters of evidence, in priority order.

    Returns a modified copy and a human-readable note of what was cut.
    The error block, failed_step and error_message are never touched.
    """
    updated = findings.model_copy(deep=True)
    notes: list[str] = []
    remaining = chars_to_cut

    for label in (BLOCK_CONSOLE, BLOCK_DOM):
        if remaining <= 0:
            break
        for block in updated.evidence_blocks:
            if block.label != label or not block.content:
                continue
            cut = min(len(block.content), remaining)
            if label == BLOCK_CONSOLE:
                # Keep the tail: the most recent console lines matter most.
                block.content = block.content[cut:]
            else:
                # Keep the head of the DOM dump.
                block.content = block.content[: len(block.content) - cut]
            remaining -= cut
            notes.append(f"{label} bloğundan {cut} karakter kırpıldı")

    if remaining > 0 and updated.ui_excerpt:
        cut = min(len(updated.ui_excerpt), remaining)
        updated.ui_excerpt = updated.ui_excerpt[: len(updated.ui_excerpt) - cut]
        remaining -= cut
        notes.append(f"ui_excerpt alanından {cut} karakter kırpıldı")

    return updated, "; ".join(notes)
