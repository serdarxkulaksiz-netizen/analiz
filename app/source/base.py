"""Source interface — pluggable data origin."""

from abc import ABC, abstractmethod
from typing import Protocol

from app.source.models import Attachment, JobData, RunSummary


class DownloadPlan(Protocol):
    """What this layer needs in order to decide what to fetch."""

    def wants(self, attachment: Attachment) -> bool:
        """Should this attachment be downloaded at all?"""
        ...

    @property
    def wants_build_log(self) -> bool:
        """Should the job-level log endpoint be called?"""
        ...


class Source(ABC):
    """Fetches a finished job's failure evidence."""

    @abstractmethod
    async def resolve_run(self, job_id: str, run_id: str = "") -> RunSummary:
        """Resolve WHICH run to analyze — cheap, no evidence fetched."""

    @abstractmethod
    async def fetch_job(self, run: RunSummary, plan: DownloadPlan) -> JobData:
        """Return the job report and raw evidence for every failed scenario."""
