"""EvidenceExtractor — the single, source-agnostic extractor.

Because MockSource and VisiumGoSource produce the SAME `RawScenario` shape,
extraction is identical regardless of origin — so there is ONE extractor (the
mock/real difference lives entirely in the Source).

The run's job_id selects an analysis Profile, which decides which evidence
types become prompt blocks and how each one's content is shaped
(content rules). The `=== HATA ===` block is `error_text`. The job-level build
log is injected as a synthetic `build` attachment so it flows through the same
profile + rule machinery as every other evidence. No field-extracting parsing
(parse-minimal).
"""

from app.domain.enums import StepStatus
from app.domain.findings import (
    BLOCK_ERROR,
    AttachmentReport,
    BlockReport,
    EvidenceBlock,
    EvidenceReport,
    Findings,
)
from app.evidence.profiles import Profile, ProfileRegistry
from app.evidence.registry import EvidenceRegistry, evidence_name_for
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
        job_id: str = "",
        forced_profile: str = "",
        build_log: str = "",
    ) -> Findings:
        profile = self._profiles.get(job_id=job_id, forced=forced_profile)

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
        trimmed_labels: set[str] = set()
        excluded_from_store: list[str] = []
        for evidence in evidences:
            block = evidence.to_block()
            if block is not None:
                evidence_blocks.append(block)
                if evidence.was_trimmed:
                    trimmed.append(type(evidence).evidence_name)
                    trimmed_labels.add(block.label)
            if evidence.screenshot_path:
                screenshot_paths.append(evidence.screenshot_path)
            if not evidence.goes_to_store:
                excluded_from_store.append(type(evidence).evidence_name)

        # An evidence the profile asked for but that never arrived produces NO
        # block: it leaves the prompt with its header. What was
        # asked for and what actually arrived is recorded in `evidence_report`,
        # which is where that question belongs — not in the prompt.

        # Findings fields taken straight from the scenario (no parsing).
        error_message = scenario.error_text
        failed_step = next(
            (step.name for step in scenario.steps if step.status is StepStatus.FAILED),
            "",
        )

        # HATA block = the scenario's error_text (approved decision).
        if error_message:
            evidence_blocks.append(EvidenceBlock(label=BLOCK_ERROR, content=error_message))

        report = _build_report(scenario_for_evidence, profile, evidence_blocks, trimmed_labels)

        return Findings(
            scenario_name=scenario.scenario_name,
            failed_step=failed_step,
            error_message=error_message,
            steps=scenario.steps,
            evidence_blocks=evidence_blocks,
            screenshot_paths=screenshot_paths,
            retry_info=scenario.retry_info,
            profile_name=profile.name,
            prompt_template=profile.prompt,
            extra_context=profile.extra_context,
            excluded_from_store=excluded_from_store,
            evidence_report=report,
            truncated=bool(trimmed),
            truncated_note=(
                f"profil '{profile.name}' kuralları uygulandı: {', '.join(trimmed)} "
                "(ham içerik database/ altında tam duruyor)"
                if trimmed
                else ""
            ),
        )


def _build_report(
    scenario: RawScenario,
    profile: Profile,
    blocks: list[EvidenceBlock],
    trimmed_labels: set[str],
) -> EvidenceReport:
    """Record what arrived and what reached the prompt.

    Answers, from one real run and without reproducing it by hand: did the
    evidence arrive at all, did it map to an Evidence class, did the profile
    send it, and did its content rules actually cut anything.
    """
    attachments = [
        AttachmentReport(
            file_name=attachment.file_name,
            mime_type=attachment.mime_type,
            device_id=attachment.device_id,
            evidence_name=evidence_name_for(attachment),
            goes_to_llm=evidence_name_for(attachment) in profile.evidence_to_llm,
            download_skipped=attachment.download_skipped,
            chars=len(attachment.content),
        )
        for attachment in scenario.attachments
    ]
    return EvidenceReport(
        attachments=attachments,
        blocks=[
            BlockReport(
                label=block.label,
                chars=len(block.content),
                available=bool(block.content),
                trimmed=block.label in trimmed_labels,
            )
            for block in blocks
        ],
        unmatched=[row.file_name for row in attachments if not row.evidence_name],
        skipped=[row.file_name for row in attachments if row.download_skipped],
    )
