"""VisiumGoExtractor — real evidence extractor (STUB).

# TODO(work-pc): implement on the work computer once real test.log / DOM /
# browser.log samples are visible (plan.md A13). Rules (plan.md A5, B3.6):
#   - merge logs by timestamp, emit LABELED BLOCKS
#     (=== ADIMLAR ===, === HATA (stack trace) ===, === DOM ===, === CONSOLE.LOG ===)
#   - NO field-extracting, component-specific parsers — the LLM interprets
#   - code only does coarse, conditional, prioritized size management
"""

from app.domain.findings import Findings
from app.extraction.base import Extractor
from app.source.models import RawScenario


class VisiumGoExtractor(Extractor):
    """Parse-minimal extractor for real VisiumGo evidence (stub)."""

    def extract(self, scenario: RawScenario) -> Findings:
        # TODO(work-pc): build Findings from real raw evidence. Keep it
        # parse-minimal: locate the failed step + error message, pass the
        # rest through as labeled raw blocks.
        raise NotImplementedError(
            "VisiumGoExtractor is a stub; implement on the work PC "
            f"(scenario='{scenario.scenario_name}'). "
            "Use EXTRACTOR_PROVIDER=mock until then."
        )
