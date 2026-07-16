"""MockExtractor — works against MockSource's fixture log format.

Only understands the simple `... STEP <name> | <STATUS>` / `... ERROR ...`
line format that MockSource emits. This is mock plumbing so the chain runs
end-to-end locally; it is NOT the parse-minimal real extractor (that stub is
in `visiumgo.py`, filled on the work PC).
"""

from app.domain.enums import StepStatus
from app.domain.findings import (
    BLOCK_CONSOLE,
    BLOCK_DOM,
    BLOCK_ERROR,
    BLOCK_STEPS,
    EvidenceBlock,
    Findings,
    Step,
)
from app.extraction.base import Extractor
from app.source.models import RawScenario


class MockExtractor(Extractor):
    """Builds Findings from MockSource's deterministic fixture logs."""

    def extract(self, scenario: RawScenario) -> Findings:
        steps: list[Step] = []
        step_lines: list[str] = []
        error_lines: list[str] = []
        failed_step = ""

        for line in scenario.test_log.splitlines():
            if " STEP " in line:
                step_lines.append(line)
                step_part = line.split(" STEP ", 1)[1]
                if " | " not in step_part:
                    continue
                name, status_text = step_part.rsplit(" | ", 1)
                status = StepStatus(status_text.strip())
                steps.append(Step(name=name.strip(), status=status))
                if status is StepStatus.FAILED and not failed_step:
                    failed_step = name.strip()
            elif " ERROR " in line:
                error_lines.append(line)

        error_message = "\n".join(error_lines)

        evidence_blocks = [
            EvidenceBlock(label=BLOCK_STEPS, content="\n".join(step_lines)),
            EvidenceBlock(label=BLOCK_ERROR, content=error_message),
        ]
        if scenario.dom_html:
            evidence_blocks.append(EvidenceBlock(label=BLOCK_DOM, content=scenario.dom_html))
        if scenario.browser_log:
            evidence_blocks.append(
                EvidenceBlock(label=BLOCK_CONSOLE, content=scenario.browser_log)
            )

        return Findings(
            platform=scenario.platform,
            scenario_name=scenario.scenario_name,
            failed_step=failed_step,
            error_message=error_message,
            steps=steps,
            ui_excerpt=scenario.dom_html,
            evidence_blocks=evidence_blocks,
            screenshot_path=scenario.screenshot_path,
            retry_info=scenario.retry_info,
        )
