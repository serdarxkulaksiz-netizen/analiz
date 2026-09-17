"""EvidenceExtractor — the single, source-agnostic extractor."""

from app.domain.findings import (
    AttachmentReport,
    BlockReport,
    EvidenceBlock,
    EvidenceReport,
    Findings,
    JobLogReport,
)
from app.evidence.profiles import Profile
from app.evidence.registry import EvidenceRegistry, evidence_name_for
from app.evidence.rules import RuleContext, RuleError
from app.evidence.types import BuildLogEvidence
from app.extraction.base import Extractor
from app.source.models import JobLog, RawScenario


class EvidenceExtractor(Extractor):
    """Maps a RawScenario's attachments + the job log into the Findings contract."""

    def __init__(self, registry: EvidenceRegistry) -> None:
        self._registry = registry

    def extract(
        self,
        scenario: RawScenario,
        *,
        profile: Profile,
        job_log: JobLog | None = None,
    ) -> Findings:
        job_log = job_log or JobLog()
        ctx = RuleContext(scenario_name=scenario.scenario_name)
        evidences = self._registry.build_for(scenario, profile, ctx)

        log_evidence = self._registry.build_job_log(job_log.text, profile, ctx)
        if log_evidence is not None:
            evidences.append(log_evidence)

        evidence_blocks: list[EvidenceBlock] = []
        trimmed_labels: set[str] = set()
        rule_errors: list[str] = []
        for evidence in evidences:
            name = type(evidence).evidence_name
            try:
                block = evidence.to_block()
                was_trimmed = evidence.was_trimmed
            except RuleError as exc:
                rule_errors.append(f"{name}: {exc}")
                block, was_trimmed = None, False
            if block is not None:
                evidence_blocks.append(block)
                if was_trimmed:
                    trimmed_labels.add(block.label)

        order = {name: index for index, name in enumerate(profile.evidence_to_llm)}
        evidence_blocks.sort(key=lambda block: order.get(block.evidence_name, len(order)))

        report = _build_report(
            scenario,
            profile,
            evidence_blocks,
            trimmed_labels,
            job_log=job_log,
            rule_errors=rule_errors,
        )

        return Findings(
            scenario_name=scenario.scenario_name,
            evidence_blocks=evidence_blocks,
            profile_name=profile.name,
            prompt_template=profile.prompt,
            extra_context=profile.extra_context,
            evidence_report=report,
        )


def _build_report(
    scenario: RawScenario,
    profile: Profile,
    blocks: list[EvidenceBlock],
    trimmed_labels: set[str],
    *,
    job_log: JobLog,
    rule_errors: list[str] | None = None,
) -> EvidenceReport:
    """Record what arrived and what reached the prompt."""
    attachments = [
        AttachmentReport(
            file_name=attachment.file_name,
            mime_type=attachment.mime_type,
            device_id=attachment.device_id,
            evidence_name=evidence_name_for(attachment),
            goes_to_llm=evidence_name_for(attachment) in profile.evidence_to_llm,
            download_skipped=attachment.download_skipped,
            download_error=attachment.download_error,
            chars=len(attachment.content),
            stored_path=attachment.stored_path,
        )
        for attachment in scenario.attachments
    ]
    build_log_name = BuildLogEvidence.evidence_name
    return EvidenceReport(
        attachments=attachments,
        scenario_error=scenario.fetch_error,
        rule_errors=rule_errors or [],
        job_log=JobLogReport(
            wanted=build_log_name in profile.wanted_evidence,
            chars=len(job_log.text),
            goes_to_llm=build_log_name in profile.evidence_to_llm,
            stored_path=job_log.stored_path,
            error=job_log.error,
        ),
        blocks=[
            BlockReport(
                label=block.label,
                chars=len(block.content),
                available=bool(block.content),
                trimmed=block.label in trimmed_labels,
            )
            for block in blocks
        ],
    )
