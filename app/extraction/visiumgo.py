"""VisiumGoExtractor — real evidence extractor (STUB).

# TODO(work-pc): implement on the work computer once real test.log / DOM /
# browser.log samples are visible (plan.md A16). Rules (plan.md A5, B3.6):
#   - build the shared Evidence instances via `self._registry.build_for(...)`,
#     collect their labeled blocks / screenshot paths / missing list
#   - minimally identify failed_step + error_message from test.log; the HATA
#     block is that error_message (approved decision); CONSOLE.LOG is the
#     job-level Jenkins log
#   - NO field-extracting, component-specific parsers — the LLM interprets
#   - each Evidence's content selector does coarse size management (passthrough)
"""

from app.domain.findings import Findings
from app.evidence.registry import EvidenceRegistry
from app.extraction.base import Extractor
from app.source.models import RawScenario


class VisiumGoExtractor(Extractor):
    """Parse-minimal extractor for real VisiumGo evidence (stub)."""

    def __init__(self, registry: EvidenceRegistry) -> None:
        self._registry = registry

    def extract(
        self,
        scenario: RawScenario,
        *,
        bank: str = "",
        jenkins_console_log: str = "",
    ) -> Findings:
        # TODO(work-pc): assemble Findings from real raw evidence via
        # self._registry.build_for(scenario). Keep it parse-minimal.
        raise NotImplementedError(
            "VisiumGoExtractor is a stub; implement on the work PC "
            f"(scenario='{scenario.scenario_name}'). "
            "Use EXTRACTOR_PROVIDER=mock until then."
        )
