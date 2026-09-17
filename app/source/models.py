"""Raw job data models — the Source layer's output."""

from pathlib import PurePosixPath

from pydantic import BaseModel


class Attachment(BaseModel):
    """One raw file attached to a scenario."""

    file_name: str
    mime_type: str
    device_id: str
    content: str = ""
    stored_path: str = ""
    download_skipped: bool = False
    download_error: str = ""

    @property
    def extension(self) -> str:
        """Lower-cased file extension including the dot ("" if there is none)."""
        return PurePosixPath(self.file_name).suffix.lower()

    @property
    def label(self) -> str:
        """`<device_id><extension>` — the same name VisiumGo's UI shows."""
        return f"{self.device_id}{self.extension}"


class RawScenario(BaseModel):
    """One failed scenario's raw evidence bundle."""

    scenario_name: str
    scenario_id: str = ""
    error_text: str = ""
    attachments: list[Attachment] = []
    fetch_error: str = ""


class RunSummary(BaseModel):
    """Which run will be analyzed, resolved BEFORE any evidence is fetched."""

    run_id: str
    job_id: str = ""
    job_name: str = ""
    state: str = ""
    run_result: dict = {}
    raw: dict = {}
    note: str = ""


class JobLog(BaseModel):
    """The job-level build log: one log for the whole run, own endpoint."""

    text: str = ""
    stored_path: str = ""
    error: str = ""


class JobData(BaseModel):
    """One run's evidence: which scenarios failed, and what came with them."""

    total_scenario_count: int = 0
    failed_scenarios: list[RawScenario] = []
    job_log: JobLog = JobLog()
    raw_results_response: list = []
