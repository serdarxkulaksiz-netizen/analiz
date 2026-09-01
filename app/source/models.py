"""Raw job data models — the Source layer's output (plan.md A4).

Attachment-based, source-agnostic shape: both MockSource and VisiumGoSource
produce the SAME `RawScenario`, so the extraction ring is identical regardless
of origin (the mock/real difference lives entirely in the Source).

Everything the source received is kept (user rule: save everything for now):
`raw_detail` carries the scenario-detail response untouched, and
`raw_results_response` / `raw_run_response` carry the job-level responses.
"""

from pydantic import BaseModel

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

    Any attachment may be absent; the analysis tolerates whatever arrived.
    `raw_detail` is the FULL scenario-detail API response (properties and all),
    persisted for observability — nothing from the source is thrown away.
    """

    scenario_name: str
    scenario_id: str = ""
    error_text: str = ""
    steps: list[Step] = []
    attachments: list[Attachment] = []
    retry_info: str = ""
    raw_detail: dict = {}


class JobData(BaseModel):
    """A finished job run's report: which scenarios failed, with raw evidence."""

    job_id: str = ""
    run_id: str = ""
    job_name: str = ""
    run_result: dict = {}  # state / totals summary (raw, from VisiumGo)
    total_scenario_count: int = 0
    failed_scenarios: list[RawScenario] = []
    # Job-level build log (VisiumGo `/logs` -> `build.log`); empty when the
    # endpoint is not configured.
    build_log: str = ""
    # Raw job-level responses for observability (plan.md A12).
    raw_run_response: dict = {}
    raw_results_response: list = []
