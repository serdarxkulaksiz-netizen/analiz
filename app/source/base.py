"""Source interface — pluggable data origin."""

from abc import ABC, abstractmethod
from typing import Protocol

from app.source.models import Attachment, JobData, RawScenario, RunSummary


class DownloadPlan(Protocol):
    """What this layer needs in order to decide what to fetch."""

    def wants(self, attachment: Attachment) -> bool:
        """Should this attachment be downloaded at all?"""
        ...

    @property
    def wants_build_log(self) -> bool:
        """Should the job-level log endpoint be called?"""
        ...

    @property
    def run_level(self) -> bool:
        """Is the run itself the subject, so scenario rows are not read?"""
        ...


class Source(ABC):
    """Fetches a finished job's failure evidence."""

    @abstractmethod
    async def resolve_run(self, job_id: str, run_id: str = "") -> RunSummary:
        """Resolve WHICH run to analyze — cheap, no evidence fetched."""

    @abstractmethod
    async def fetch_job(self, run: RunSummary, plan: DownloadPlan) -> JobData:
        """Which scenarios failed and what each one says — WITHOUT file contents.

        Cheap on purpose: every failed scenario is described (name, error, step)
        but no attachment is read. Those facts are what the caller groups by, and
        grouping decides which scenarios are worth reading files for.
        """

    @abstractmethod
    async def load_attachments(
        self, run_id: str, scenario: RawScenario, plan: DownloadPlan
    ) -> RawScenario:
        """Read this scenario's attachments, returning it with their contents."""

    @abstractmethod
    async def aclose(self) -> None:
        """Release whatever this source holds open (pooled connections)."""
