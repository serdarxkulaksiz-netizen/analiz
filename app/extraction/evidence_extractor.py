"""EvidenceExtractor — the single, source-agnostic extractor (plan.md A5).

Because MockSource and VisiumGoSource produce the SAME `RawScenario` shape,
extraction is identical regardless of origin — so there is ONE extractor (the
mock/real difference lives entirely in the Source).

The run's job_id / `parameter1` select an analysis Profile, which decides which
evidence types become prompt blocks and how each one's content is shaped
(content rules). The `=== HATA ===` block is `error_text`. The job-level build
log is injected as a synthetic `build` attachment so it flows through the same
profile + rule machinery as every other evidence. No field-extracting parsing
(parse-minimal).
"""

from app.domain.enums import StepStatus
from app.domain.findings import (
    BLOCK_ERROR,
    EVIDENCE_UNAVAILABLE,
    EvidenceBlock,
    Findings,
)
from app.evidence.profiles import ProfileRegistry
from app.evidence.registry import EvidenceRegistry, evidence_class_by_name
from app.evidence.rules import RuleContext
from app.extraction.base import Extractor
from app.source.models import Attachment, RawScenario

#: device_id of the synthetic attachment carrying the job-level build log.
BUILD_LOG_DEVICE_ID = "build"


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
        build_log: str = "",
    ) -> Findings:
        profile = self._profiles.get(job_id=job_id, parameter1=parameter1)

        # The job-level build log becomes a normal attachment, so the profile
        # can include/exclude it and its rules can slice it per scenario.
        scenario_for_evidence = scenario
        if build_log:
            scenario_for_evidence = scenario.model_copy(
                update={
                    "attachments": [
                        *scenario.attachments,
                        Attachment(
                            file_name="build.log",
                            mime_type="text/plain",
                            device_id=BUILD_LOG_DEVICE_ID,
                            content=build_log,
                        ),
                    ]
                }
            )

        ctx = RuleContext(scenario_name=scenario.scenario_name)
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

        # An evidence the profile asked for but that never arrived (or arrived
        # empty) still gets its block — with a "not available" placeholder — so
        # the LLM sees the gap instead of the block vanishing silently.
        present_labels = {block.label for block in evidence_blocks}
        for name in profile.evidence_to_llm:
            cls = evidence_class_by_name(name)
            label = getattr(cls, "block_label", "")  # screenshots have none
            if label and label not in present_labels:
                evidence_blocks.append(
                    EvidenceBlock(label=label, content=EVIDENCE_UNAVAILABLE)
                )
                present_labels.add(label)

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
