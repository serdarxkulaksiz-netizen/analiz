"""EvidenceExtractor — the single, source-agnostic extractor (plan.md A5).

Because MockSource and VisiumGoSource produce the SAME `RawScenario` shape,
extraction is identical regardless of origin — so there is ONE extractor (the
mock/real difference lives entirely in the Source).

It assembles Findings from the Evidence layer (registry-mapped, config-flagged)
plus the scenario's own `error_text` / `steps`. Per the approved decision, the
`=== HATA ===` block is `error_text`, and `=== CONSOLE.LOG ===` is the
job-level Jenkins log. It does NO field-extracting parsing (parse-minimal).
"""

from app.domain.enums import StepStatus
from app.domain.findings import (
    BLOCK_CONSOLE,
    BLOCK_ERROR,
    EvidenceBlock,
    Findings,
)
from app.evidence.registry import EvidenceRegistry
from app.extraction.base import Extractor
from app.source.models import RawScenario


class EvidenceExtractor(Extractor):
    """Maps a RawScenario's attachments + fields into the Findings contract."""

    def __init__(self, registry: EvidenceRegistry) -> None:
        self._registry = registry

    def extract(
        self,
        scenario: RawScenario,
        *,
        bank: str = "",
        jenkins_console_log: str = "",
    ) -> Findings:
        evidences = self._registry.build_for(scenario)

        evidence_blocks: list[EvidenceBlock] = []
        screenshot_paths: list[str] = []
        for evidence in evidences:
            block = evidence.to_block()
            if block is not None:
                evidence_blocks.append(block)
            if evidence.screenshot_path:
                screenshot_paths.append(evidence.screenshot_path)

        missing_evidence = self._registry.missing_names(scenario.platform, evidences)

        # Findings fields taken straight from the scenario (no parsing).
        error_message = scenario.error_text
        failed_step = next(
            (step.name for step in scenario.steps if step.status is StepStatus.FAILED),
            "",
        )

        # HATA block = the scenario's error_text (approved decision).
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
            steps=scenario.steps,
            evidence_blocks=evidence_blocks,
            missing_evidence=missing_evidence,
            screenshot_paths=screenshot_paths,
            retry_info=scenario.retry_info,
        )
