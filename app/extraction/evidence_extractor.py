"""EvidenceExtractor — the single, source-agnostic extractor.

Extraction works from `RawScenario` alone, never from a VisiumGo response, so
there is ONE extractor and the API's shape stops at the Source layer.

The Profile — resolved once for the run, before anything was fetched — decides
which evidence types become prompt blocks, in what order, and how each one's
content is shaped (content rules). The job-level build log is built as its own
evidence from its
own endpoint — it is NOT dressed up as an attachment, because VisiumGo's
`attachments[]` array never contained it. No field-extracting parsing
(parse-minimal).
"""

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
from app.source.models import RawScenario


class EvidenceExtractor(Extractor):
    """Maps a RawScenario's attachments + the job log into the Findings contract."""

    def __init__(self, registry: EvidenceRegistry) -> None:
        self._registry = registry

    def extract(
        self,
        scenario: RawScenario,
        *,
        profile: Profile,
        build_log: str = "",
        build_log_error: str = "",
        build_log_path: str = "",
    ) -> Findings:
        ctx = RuleContext(scenario_name=scenario.scenario_name)
        evidences = self._registry.build_for(scenario, profile, ctx)

        # The job log is a peer of the attachment-backed evidences, not one of
        # them: same profile flags, same content rules, different origin.
        job_log = self._registry.build_job_log(build_log, profile, ctx)
        if job_log is not None:
            evidences.append(job_log)

        evidence_blocks: list[EvidenceBlock] = []
        trimmed_labels: set[str] = set()
        rule_errors: list[str] = []
        for evidence in evidences:
            name = type(evidence).evidence_name
            try:
                block = evidence.to_block()
                was_trimmed = evidence.was_trimmed
            except RuleError as exc:
                # The rule failed, so this evidence has NO shaped content and
                # therefore no block. The untrimmed original is not a fallback:
                # it is the thing the profile said not to send.
                rule_errors.append(f"{name}: {exc}")
                block, was_trimmed = None, False
            if block is not None:
                evidence_blocks.append(block)
                if was_trimmed:
                    trimmed_labels.add(block.label)

        # An evidence the profile asked for but that never arrived produces NO
        # block: it leaves the prompt with its header. What was
        # asked for and what actually arrived is recorded in `evidence_report`,
        # which is where that question belongs — not in the prompt.

        # Order follows the profile's `evidence_to_llm` list, not the order
        # VisiumGo happened to return the files in: which evidence the model
        # should read first is a job decision, so config owns it.
        order = {name: index for index, name in enumerate(profile.evidence_to_llm)}
        evidence_blocks.sort(key=lambda block: order.get(block.evidence_name, len(order)))

        report = _build_report(
            scenario,
            profile,
            evidence_blocks,
            trimmed_labels,
            build_log=build_log,
            build_log_error=build_log_error,
            build_log_path=build_log_path,
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
    build_log: str = "",
    build_log_error: str = "",
    build_log_path: str = "",
    rule_errors: list[str] | None = None,
) -> EvidenceReport:
    """Record what arrived and what reached the prompt.

    Answers, from one real run and without reproducing it by hand: did the
    evidence arrive at all, did it map to an Evidence class, did the profile
    send it, and did its content rules actually cut anything.

    `attachments` lists ONLY what VisiumGo's `attachments[]` array carried; the
    job log has its own field because it has its own endpoint.
    """
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
            chars=len(build_log),
            goes_to_llm=build_log_name in profile.evidence_to_llm,
            stored_path=build_log_path,
            error=build_log_error,
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
