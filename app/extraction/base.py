"""Extractor interface (plan.md Halka 2).

Raw evidence goes out as labeled blocks; interpretation belongs to the LLM
(parse-minimal, plan.md A5/B3.6).

`parameter1` (profile name override) and `job_id` select the analysis profile —
which evidence reaches the prompt and how its content is shaped. `parameter2`
is carried through for the record/prompt context. `build_log` is job-level
context (plan.md A4.1 — VisiumGo `/logs` -> `build.log`) that becomes the
`=== BUILD LOG ===` block when the profile includes it.
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
        parameter1: str = "default",
        parameter2: str = "default",
        job_id: str = "",
        build_log: str = "",
    ) -> Findings:
        """Build Findings (labeled blocks + minimal fields) from raw evidence."""
