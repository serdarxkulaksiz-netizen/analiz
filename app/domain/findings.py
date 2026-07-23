"""Findings contract — the fixed boundary between Extraction and Prompt Building.

plan.md A6: platform-independent structure; field names are frozen.
Evidence block labels (plan.md A5) are architectural constants: raw evidence
travels as labeled blocks, interpretation is left to the LLM (parse-minimal).
"""

from pydantic import BaseModel

from app.domain.enums import Platform, StepStatus

# Labeled evidence block names (plan.md A6) — contract constants, not config.
# BROWSER LOG = browser.default.log; CONSOLE.LOG = Jenkins console.log (job-level).
BLOCK_STEPS = "ADIMLAR"
BLOCK_ERROR = "HATA"
BLOCK_DOM = "DOM"
BLOCK_BROWSER = "BROWSER LOG"
BLOCK_CONSOLE = "CONSOLE.LOG"


class Step(BaseModel):
    """One test step and its outcome (plan.md A6 `steps`)."""

    name: str
    status: StepStatus


class EvidenceBlock(BaseModel):
    """A labeled raw-evidence block, rendered as `=== <label> ===` in the prompt."""

    label: str
    content: str


class Findings(BaseModel):
    """Fixed contract between Halka 2 (Extraction) and Halka 3 (Prompt Building).

    plan.md A6. UI/DOM content is NOT a separate field — it travels inside
    `evidence_blocks` (e.g. the `=== DOM ===` block), so the contract stays
    platform-independent (no web-smelling `dom_excerpt`/`ui_excerpt`).
    """

    platform: Platform
    bank: str = ""
    scenario_name: str
    failed_step: str = ""
    error_message: str = ""
    steps: list[Step] = []
    evidence_blocks: list[EvidenceBlock] = []
    missing_evidence: list[str] = []
    screenshot_paths: list[str] = []
    retry_info: str = ""
