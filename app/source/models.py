"""Raw job data models — the Source layer's output (plan.md A4).

Attachment-based, source-agnostic shape: both MockSource and VisiumGoSource
produce the SAME `RawScenario`, so the extraction ring is identical regardless
of origin (the mock/real difference lives entirely in the Source).

Evidence is NOT pre-sorted here into typed fields; each raw file travels as an
`Attachment` carrying its `mime_type` + `device_id`, and the Evidence registry
maps it downstream (parse-minimal, no file-name `if`s).
"""

from pydantic import BaseModel

from app.domain.enums import Platform
from app.domain.findings import Step


class Attachment(BaseModel):
    """One raw file attached to a scenario (plan.md A4.3).

    `mime_type` + `device_id` identify what it is (the Evidence registry maps
    it). Text files (html/logs) carry `content`; binary files (png) carry only
    `stored_path` (where the download was saved), `content` stays empty.
    """

    file_name: str
    mime_type: str
    device_id: str
    content: str = ""
    stored_path: str = ""


class RawScenario(BaseModel):
    """One failed scenario's raw evidence bundle (plan.md A4).

    `platform` is set from the job/request, not guessed. Any attachment may be
    absent ("missing evidence" is tolerated downstream, A5.4).
    """

    scenario_name: str
    platform: Platform
    scenario_id: str = ""
    error_text: str = ""
    steps: list[Step] = []
    attachments: list[Attachment] = []
    retry_info: str = ""


class JobData(BaseModel):
    """A finished job run's report: which scenarios failed, with raw evidence."""

    bank: str
    job_id: str = ""
    run_id: str = ""
    platform: Platform
    job_name: str = ""
    run_result: dict = {}  # state / totals summary (raw, from VisiumGo)
    total_scenario_count: int = 0
    failed_scenarios: list[RawScenario] = []
    # Jenkins console.log: fetch method not yet known (plan.md A4) — the
    # contract slot exists, filled on the work PC.
    jenkins_console_log: str = ""
    # Raw run response for observability (plan.md A4 / A12).
    raw_run_response: dict = {}
