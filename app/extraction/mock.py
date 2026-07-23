"""MockExtractor — assembles Findings from Evidence, for local development.

Uses the shared Evidence architecture (registry-built, config-flagged) to
collect the raw labeled blocks, screenshot paths and missing-evidence list.
On top of that it does the *minimal* identification the Findings contract
requires (A6): failed_step / error_message / steps from `test.log`. Per the
approved decision, the `=== HATA ===` block is that identified `error_message`
(no extra parsing), and `=== CONSOLE.LOG ===` is the job-level Jenkins log.

This mock only understands MockSource's `... STEP <name> | <STATUS>` /
`... ERROR ...` fixture format. It is NOT the parse-minimal real extractor
(that stub is in `visiumgo.py`, filled on the work PC).
"""

from app.domain.enums import StepStatus
from app.domain.findings import (
    BLOCK_CONSOLE,
    BLOCK_ERROR,
    EvidenceBlock,
    Findings,
    Step,
)
from app.evidence.registry import EvidenceRegistry
from app.extraction.base import Extractor
from app.source.models import RawScenario


class MockExtractor(Extractor):
    """Builds Findings from Evidence + minimal test.log identification."""

    def __init__(self, registry: EvidenceRegistry) -> None:
        self._registry = registry

    def extract(
        self,
        scenario: RawScenario,
        *,
        bank: str = "",
        jenkins_console_log: str = "",
    ) -> Findings:
        evidence_blocks: list[EvidenceBlock] = []
        screenshot_paths: list[str] = []
        missing_evidence: list[str] = []

        # Raw labeled blocks + screenshots + missing list, from the Evidence layer.
        for evidence in self._registry.build_for(scenario):
            if evidence.is_missing:
                missing_evidence.append(evidence.evidence_name)
                continue
            block = evidence.to_block()
            if block is not None:
                evidence_blocks.append(block)
            if evidence.screenshot_path:
                screenshot_paths.append(evidence.screenshot_path)

        # Minimal identification required by the Findings contract (A6).
        steps, failed_step, error_message = self._read_test_log(scenario.test_log)

        # HATA block = the identified error_message (no extra parsing).
        if error_message:
            evidence_blocks.append(
                EvidenceBlock(label=BLOCK_ERROR, content=error_message)
            )
        # Job-level Jenkins console.log (A4.1), if provided.
        if jenkins_console_log:
            evidence_blocks.append(
                EvidenceBlock(label=BLOCK_CONSOLE, content=jenkins_console_log)
            )

        return Findings(
            platform=scenario.platform,
            bank=bank,
            scenario_name=scenario.scenario_name,
            failed_step=failed_step,
            error_message=error_message,
            steps=steps,
            evidence_blocks=evidence_blocks,
            missing_evidence=missing_evidence,
            screenshot_paths=screenshot_paths,
            retry_info=scenario.retry_info,
        )

    @staticmethod
    def _read_test_log(test_log: str) -> tuple[list[Step], str, str]:
        """Read steps / failed_step / error_message from the fixture format."""
        steps: list[Step] = []
        error_lines: list[str] = []
        failed_step = ""

        for line in test_log.splitlines():
            if " STEP " in line:
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

        return steps, failed_step, "\n".join(error_lines)
