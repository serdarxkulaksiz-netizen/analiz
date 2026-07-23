"""Extractor interface (plan.md Halka 2).

Raw evidence goes out as labeled blocks; interpretation belongs to the LLM
(parse-minimal, plan.md A5/B3.6). This is the only ring that changes when a
new platform (web -> mobile -> hybrid) is added.

`bank` and `jenkins_console_log` are job-level context (plan.md A4.1): the
bank stamps the Findings, and the Jenkins console.log becomes the job-level
`=== CONSOLE.LOG ===` block (it is not one of the five per-scenario evidence
classes, A5.1).
"""

from abc import ABC, abstractmethod

from app.domain.findings import Findings
from app.source.models import RawScenario


class Extractor(ABC):
    """Turns one failed scenario's raw evidence into the Findings contract."""

    @abstractmethod
    def extract(
        self,
        scenario: RawScenario,
        *,
        bank: str = "",
        jenkins_console_log: str = "",
    ) -> Findings:
        """Build Findings (labeled blocks + minimal fields) from raw evidence."""
