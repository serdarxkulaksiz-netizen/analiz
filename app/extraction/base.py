"""Extractor interface (plan.md Halka 2).

Raw evidence goes out as labeled blocks; interpretation belongs to the LLM
(parse-minimal, plan.md A5/B3.6). This is the only ring that changes when a
new platform (web -> mobile -> ios) is added.
"""

from abc import ABC, abstractmethod

from app.domain.findings import Findings
from app.source.models import RawScenario


class Extractor(ABC):
    """Turns one failed scenario's raw evidence into the Findings contract."""

    @abstractmethod
    def extract(self, scenario: RawScenario) -> Findings:
        """Build Findings (labeled blocks + minimal fields) from raw evidence."""
