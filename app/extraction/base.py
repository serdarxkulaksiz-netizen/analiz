"""Extractor interface."""

from abc import ABC, abstractmethod

from app.domain.findings import Findings
from app.evidence.profiles import Profile
from app.source.models import JobLog, RawScenario


class Extractor(ABC):
    """Turns one failed scenario's raw evidence into the Findings contract."""

    @abstractmethod
    def extract(
        self,
        scenario: RawScenario,
        *,
        profile: Profile,
        job_log: JobLog | None = None,
    ) -> Findings:
        """Build Findings (labeled blocks + minimal fields) from raw evidence."""
