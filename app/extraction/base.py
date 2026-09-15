"""Extractor interface.

Raw evidence goes out as labeled blocks; interpretation belongs to the LLM
(parse-minimal).

`job_id` selects the analysis profile — which evidence reaches the prompt and
how its content is shaped; `forced_profile` overrules it (the caller knows the
job itself failed, or is a tool that must run with one profile). The request's
`parameter1`/`parameter2` never reach here: they decide nothing.

`build_log` is job-level context (VisiumGo `/api/runs/{run_id}/logs` ->
`build.log`): it covers the whole run, not one scenario, and becomes a prompt
block when the profile includes `BuildLogEvidence`. `build_log_error` says why
it is missing although the profile asked for it — carried so the evidence row
can answer that on its own, without anyone opening the run row.
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
        build_log_error: str = "",
    ) -> Findings:
        """Build Findings (labeled blocks + minimal fields) from raw evidence."""
