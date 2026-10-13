"""EvidenceExtractor — the single, source-agnostic extractor."""

from app.domain.findings import (
    AttachmentReport,
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
        rule_errors: list[str] = []
        for evidence in evidences:
            name = type(evidence).evidence_name
            try:
                block = evidence.to_block()
            except RuleError as exc:
                rule_errors.append(f"{name}: {exc}")
                block = None
            if block is not None:
                evidence_blocks.append(block)

        order = {name: index for index, name in enumerate(profile.evidence_to_llm)}
        evidence_blocks.sort(key=lambda block: order.get(block.evidence_name, len(order)))

        report = _build_report(
            scenario,
            profile,
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
    *,
    job_log: JobLog,
    rule_errors: list[str] | None = None,
) -> EvidenceReport:
    """Record what arrived and what reached the prompt."""
    attachments = []
    for attachment in scenario.attachments:
        evidence_name = evidence_name_for(attachment)
        attachments.append(
            AttachmentReport(
                file_name=attachment.file_name,
                evidence_name=evidence_name,
                goes_to_llm=evidence_name in profile.evidence_to_llm,
                download_error=attachment.download_error,
                chars=len(attachment.content),
            )
        )
    build_log_name = BuildLogEvidence.evidence_name
    return EvidenceReport(
        attachments=attachments,
        scenario_error=scenario.fetch_error,
        error_text=scenario.error_text,
        failed_step=scenario.failed_step,
        rule_errors=rule_errors or [],
        job_log=JobLogReport(
            goes_to_llm=build_log_name in profile.evidence_to_llm,
            chars=len(job_log.text),
            error=job_log.error,
        ),
    )
