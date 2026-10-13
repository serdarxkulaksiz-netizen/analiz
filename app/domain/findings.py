"""Findings contract — the fixed boundary between Extraction and Prompt Building."""

from pydantic import BaseModel


class EvidenceBlock(BaseModel):
    """One evidence, rendered as `=== <label> ===` + content in the prompt."""

    label: str
    content: str
    evidence_name: str = ""


class AttachmentReport(BaseModel):
    """One attachment as extraction saw it — did it map to an Evidence class?"""

    file_name: str = ""
    evidence_name: str = ""
    goes_to_llm: bool = False
    download_error: str = ""
    chars: int = 0


class JobLogReport(BaseModel):
    """The job-level build log as extraction saw it."""

    goes_to_llm: bool = False
    chars: int = 0
    error: str = ""


class EvidenceReport(BaseModel):
    """Extraction's self-diagnosis for one scenario."""

    attachments: list[AttachmentReport] = []
    job_log: JobLogReport = JobLogReport()
    scenario_error: str = ""
    error_text: str = ""
    failed_step: str = ""
    rule_errors: list[str] = []


class Findings(BaseModel):
    """Fixed contract between Extraction and Prompt Building."""

    scenario_name: str
    evidence_blocks: list[EvidenceBlock] = []
    profile_name: str = ""
    prompt_template: str = ""
    extra_context: str = ""
    evidence_report: EvidenceReport = EvidenceReport()

    @property
    def has_evidence_for_llm(self) -> bool:
        """True if there is anything for the model to reason about."""
        return any(block.content for block in self.evidence_blocks)
