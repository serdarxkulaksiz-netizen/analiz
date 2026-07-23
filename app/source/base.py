"""Source interface (plan.md Halka 1) — pluggable data origin."""

from abc import ABC, abstractmethod

from app.domain.enums import Platform
from app.source.models import JobData


class Source(ABC):
    """Fetches a finished job's failure evidence for a given bank."""

    @abstractmethod
    async def fetch_job(self, bank: str, job_id: str, platform: Platform) -> JobData:
        """Return the job report and raw evidence for every failed scenario.

        `platform` is INPUT (plan.md A4.2), not guessed: it stamps the returned
        scenarios and selects the expected evidence set downstream.
        """
