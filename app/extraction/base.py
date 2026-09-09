"""Extractor interface.

Raw evidence goes out as labeled blocks; interpretation belongs to the LLM
(parse-minimal).

`job_id` selects the analysis profile — which evidence reaches the prompt and
how its content is shaped; `forced_profile` overrules it (the caller knows the
job itself failed, or is a tool that must run with one profile). The request's
`parameter1`/`parameter2` never reach here: they decide nothing. `build_log` is job-level
context — VisiumGo `/logs` -> `build.log`) that becomes the
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
        job_id: str = "",
        forced_profile: str = "",
        build_log: str = "",
    ) -> Findings:
        """Build Findings (labeled blocks + minimal fields) from raw evidence."""
