"""EvidenceExtractor — the single, source-agnostic extractor (plan.md A5).

Because MockSource and VisiumGoSource produce the SAME `RawScenario` shape,
extraction is identical regardless of origin — so there is ONE extractor (the
mock/real difference lives entirely in the Source).

The run's job_id / `parameter1` select an analysis Profile, which decides which
evidence types become prompt blocks and how each one's content is shaped
(content rules). The `=== HATA ===` block is `error_text`. The job-level Jenkins
log is injected as a synthetic `jenkins` attachment so it flows through the same
profile + rule machinery as every other evidence. No field-extracting parsing
(parse-minimal).
"""

from app.domain.enums import StepStatus
from app.domain.findings import BLOCK_ERROR, EvidenceBlock, Findings
from app.evidence.profiles import ProfileRegistry
from app.evidence.registry import EvidenceRegistry
from app.evidence.rules import RuleContext
from app.extraction.base import Extractor
from app.source.models import Attachment, RawScenario

#: device_id of the synthetic attachment carrying the job-level Jenkins log.
JENKINS_DEVICE_ID = "jenkins"


class EvidenceExtractor(Extractor):
    """Maps a RawScenario's attachments + fields into the Findings contract."""

    def __init__(self, registry: EvidenceRegistry, profiles: ProfileRegistry) -> None:
        self._registry = registry
        self._profiles = profiles

    def extract(
        self,
        scenario: RawScenario,
        *,
        parameter1: str = "default",
        parameter2: str = "default",
        job_id: str = "",
        jenkins_console_log: str = "",
    ) -> Findings:
        profile = self._profiles.get(job_id=job_id, parameter1=parameter1)

        # The job-level Jenkins log becomes a normal attachment, so the profile
        # can include/exclude it and its rules can slice it per scenario.
        scenario_for_evidence = scenario
        if jenkins_console_log:
            scenario_for_evidence = scenario.model_copy(
                update={
                    "attachments": [
                        *scenario.attachments,
                        Attachment(
                            file_name="jenkins-console.log",
                            mime_type="text/plain",
                            device_id=JENKINS_DEVICE_ID,
                            content=jenkins_console_log,
                        ),
                    ]
                }
            )

        ctx = RuleContext(
            scenario_name=scenario.scenario_name, error_text=scenario.error_text
        )
        evidences = self._registry.build_for(scenario_for_evidence, profile, ctx)

        evidence_blocks: list[EvidenceBlock] = []
        screenshot_paths: list[str] = []
        trimmed: list[str] = []
        excluded_from_store: list[str] = []
        for evidence in evidences:
            block = evidence.to_block()
            if block is not None:
                evidence_blocks.append(block)
                if evidence.was_trimmed:
                    trimmed.append(type(evidence).evidence_name)
            if evidence.screenshot_path:
                screenshot_paths.append(evidence.screenshot_path)
            if not evidence.goes_to_store:
                excluded_from_store.append(type(evidence).evidence_name)

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

        return Findings(
            parameter1=parameter1,
            parameter2=parameter2,
            scenario_name=scenario.scenario_name,
            failed_step=failed_step,
            error_message=error_message,
            steps=scenario.steps,
            evidence_blocks=evidence_blocks,
            screenshot_paths=screenshot_paths,
            retry_info=scenario.retry_info,
            profile_name=profile.name,
            extra_context=profile.extra_context,
            excluded_from_store=excluded_from_store,
            truncated=bool(trimmed),
            truncated_note=(
                f"profil '{profile.name}' kuralları uygulandı: {', '.join(trimmed)} "
                "(ham içerik database/ altında tam duruyor)"
                if trimmed
                else ""
            ),
        )
