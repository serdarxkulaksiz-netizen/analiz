"""Analysis orchestration — the whole chain wired together."""

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.config import Settings
from app.domain.enums import AnalysisStatus, RunState, RunStatus
from app.domain.findings import EvidenceReport, Findings
from app.domain.result import AnalysisMeta, AnalysisResult, LLMAnalysis
from app.evidence.plan import AnalysisPlan, plan_for
from app.evidence.profiles import JOB_FAILED_PROFILE_NAME, Profile, ProfileRegistry
from app.extraction.base import Extractor
from app.llm.provider import LLMProvider
from app.parsing.json_parser import try_json
from app.persistence.repository import Repository
from app.persistence.trace import TraceWriter
from app.precheck.base import PreCheck
from app.prompting.builder import PromptBuilder
from app.source.base import Source
from app.source.models import JobLog, RawScenario

STATE_PROFILE_OVERRIDE: dict[str, str] = {RunState.FAILED.value: JOB_FAILED_PROFILE_NAME}

#: How many times a run may be picked up again WITHOUT FINISHING A SINGLE
#: SCENARIO in between. Counting plain restarts would be wrong: two deploys in
#: an afternoon would close a run that was progressing fine. What must not
#: repeat forever is a run that kills the process before it produces anything —
#: that one is the cause, and resuming it would restart the crash at every boot.
#: A run that completed even one more diagnosis has its counter cleared.
MAX_RESUMES = 1

UNFINISHED_STATUSES = frozenset({RunStatus.PENDING.value, RunStatus.RUNNING.value})


def _skipped_reason(
    prompt: str,
    findings: Findings | None,
    no_evidence: bool,
    answered_by: str,
    error_detail: str = "",
) -> str:
    """Why no prompt was built for this scenario ("" when one was).

    The reason carries the error itself, not a pointer to somewhere else: the
    diagnosis row the caller reads is the only place this is written down, so a
    reason that says "look it up" names a place the caller cannot reach.
    """
    if prompt:
        return ""
    if answered_by and answered_by != "llm":
        return f"{answered_by} cevapladı — LLM çağrılmadı"
    if findings is None:
        return f"kanıt çıkarımı hata verdi — prompt kurulamadı ({error_detail})".replace(" ()", "")
    if not no_evidence:
        return f"prompt kurulamadı — {error_detail or 'sebep bildirilmedi'}"

    report = findings.evidence_report
    if report.scenario_error:
        return f"senaryo detayı okunamadı — {report.scenario_error}"
    missing = [
        f"{row.file_name or row.evidence_name}"
        + (f" ({row.download_error})" if row.download_error else "")
        for row in report.attachments
        if row.goes_to_llm and not row.chars
    ]
    if report.job_log.goes_to_llm and not report.job_log.chars:
        missing.append(f"build.log ({report.job_log.error or 'gelmedi'})")
    detail = f"; eksik: {', '.join(missing)}" if missing else ""
    return (
        f"prompt'a girecek kanıt yok — profil {findings.profile_name!r} "
        f"{len(findings.evidence_blocks)} blok üretti{detail}"
    )


class _RuleFailure(Exception):
    """A content rule failed — this scenario stops, the run does not."""


def _running_note(state: str) -> str:
    """Say it when the analyzed run had not finished yet ("" when it had)."""
    if state != RunState.RUNNING.value:
        return ""
    return (
        "koşum hâlâ sürüyordu (state=RUNNING) — kanıtlar eksik olabilir, "
        "teşhis o ana kadar yazılanlara dayanıyor"
    )


def _total_scenarios_note(run_result: dict[str, Any]) -> str:
    """Say it when VisiumGo did not report the run's scenario total."""
    if "totalScenarios" in run_result:
        return ""
    return "runResult.totalScenarios gelmedi — toplam senaryo sayısı bilinmiyor (0 yazıldı)"


def _forced_note(profile_name: str) -> str:
    """Say it out loud when the normal profile resolution was bypassed."""
    if not profile_name:
        return ""
    return f"'{profile_name}' profili kullanıldı (job durumu FAILED)"


def _identity(scenario_id: str, scenario_name: str) -> str:
    """What makes a scenario THIS scenario when rows are matched up.

    The source's own id, because the name is not unique: two examples of one
    Scenario Outline carry the same name, and matching by name would let one
    stand in for the other. The name is the fallback for a scenario whose
    `/results` row carried no id at all — there it is all we were given.
    """
    return scenario_id or scenario_name


def _group_scenarios(scenarios: list[RawScenario]) -> list[list[RawScenario]]:
    """Scenarios that died the same way, grouped so the model is asked once.

    The key is the failing step plus the error message, both exactly as the
    source reported them. A key with an empty half never groups: a scenario the
    source said nothing about would otherwise be merged with every other silent
    one and inherit a diagnosis nobody produced for it.
    """
    groups: dict[tuple[str, str], list[RawScenario]] = {}
    alone: list[list[RawScenario]] = []
    for scenario in scenarios:
        key = (scenario.failed_step.strip(), scenario.error_text.strip())
        if not all(key):
            alone.append([scenario])
            continue
        groups.setdefault(key, []).append(scenario)
    return [*groups.values(), *alone]


def _grouped_note(groups: list[list[RawScenario]], total: int) -> str:
    """Say it when scenarios shared an answer ("" when each got its own)."""
    asked = len(groups)
    if asked == total:
        return ""
    return (
        f"{total} senaryo {asked} gruba indi (aynı adım + aynı hata mesajı); "
        f"her grup için tek cevap üretildi, teşhis grubun tamamına yazıldı"
    )


def _scenario_facts(scenario: RawScenario, profile: Profile) -> Findings:
    """What is known about a scenario before a single file has been read.

    Its own identity and what the source said went wrong — the failing step and
    the error message. Enough for a check that answers from a catalogue, and it
    costs nothing to produce.
    """
    return Findings(
        scenario_name=scenario.scenario_name,
        profile_name=profile.name,
        prompt_template=profile.prompt,
        extra_context=profile.extra_context,
        evidence_report=EvidenceReport(
            error_text=scenario.error_text,
            failed_step=scenario.failed_step,
            scenario_error=scenario.fetch_error,
        ),
    )


def _shared_failure_reason(source: AnalysisResult) -> str:
    """The representative's failure, retold as what it is for a group member.

    Copying the sentence as it stands would make the row say the model answered
    (or failed) for THIS scenario, and it never did. The reason names whose call
    it was and why this one was not made.
    """
    if not source.failure_reason:
        return ""
    return (
        f"{source.scenario_name!r} senaryosunda: {source.failure_reason}. "
        "Aynı adım ve aynı hata mesajı olduğu için bu senaryo ayrıca sorulmadı."
    )


def _resumed_note(resume_count: int, reused: int) -> str:
    """Say it when this run had already been started before ("" when fresh)."""
    if not resume_count:
        return ""
    return (
        f"bu koşum yarıda kalmıştı, süreç yeniden başlayınca devam edildi "
        f"({resume_count}. deneme); önceden tamamlanan {reused} teşhis korundu, "
        "model bunlar için yeniden çağrılmadı"
    )


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


class AnalyzerService:
    """Coordinates Source -> Extraction -> PreCheck -> Prompt -> LLM -> Parse -> Persist."""

    def __init__(
        self,
        settings: Settings,
        repository: Repository,
        trace: TraceWriter,
        source: Source,
        extractor: Extractor,
        prompt_builder: PromptBuilder,
        llm_provider: LLMProvider,
        precheck: PreCheck,
        profiles: ProfileRegistry,
    ) -> None:
        self._settings = settings
        self._repo = repository
        self._trace = trace
        self._source = source
        self._extractor = extractor
        self._profiles = profiles
        self._builder = prompt_builder
        self._llm = llm_provider
        self._precheck = precheck
        self._run_row_lock = asyncio.Lock()
        #: One gate for the whole process, not one per run: the model is shared,
        #: and three overlapping analyses must still make `max_concurrency`
        #: calls in total, not that many each.
        self._llm_slots = asyncio.Semaphore(settings.max_concurrency)

    async def aclose(self) -> None:
        """Release the HTTP connections held by the source and the model."""
        await self._source.aclose()
        await self._llm.aclose()

    def selectable_profiles(self) -> set[str]:
        """Profile names a caller may ask for (job_failed is system-only)."""
        return self._profiles.selectable_names()

    def create_run(self, profil: str, job_id: str, run_id: str = "") -> str:
        """Persist a pending run row and return its analyzer_run_id."""
        analyzer_run_id = str(uuid4())
        now = _utcnow_iso()
        self._repo.save(
            self._settings.table_runs,
            analyzer_run_id,
            {
                "analyzer_run_id": analyzer_run_id,
                "profil": profil,
                "profile_name": "",
                "job_id": job_id,
                "run_id": run_id,
                "status": RunStatus.PENDING.value,
                "resume_count": 0,
                "resume_mark": 0,
                "scenario_count": 0,
                "completed_count": 0,
                "total_scenario_count": 0,
                "job_name": "",
                "build_log_error": "",
                "note": "",
                "created_at": now,
                "updated_at": now,
            },
        )
        return analyzer_run_id

    def recover_interrupted(self) -> list[str]:
        """Settle the runs a process death left hanging; return the ones to resume.

        A run that is still `pending` or `running` in the store cannot be
        running anywhere: this process has just started. Either it is picked up
        again — its finished diagnoses are kept and only the rest is asked — or,
        if picking it up produced nothing last time, it is closed as failed so
        the caller polling it gets an answer instead of a row that says
        "running" forever.

        `resume_mark` is how many diagnoses existed when it was last picked up;
        more than that today means the run is progressing and the give-up
        counter does not apply to it.
        """
        resume: list[str] = []
        for row in self._repo.list(self._settings.table_runs):
            if row.get("status") not in UNFINISHED_STATUSES:
                continue
            completed = int(row.get("completed_count", 0))
            attempts = int(row.get("resume_count", 0))
            if attempts and completed > int(row.get("resume_mark", 0)):
                attempts = 0
            if attempts >= MAX_RESUMES:
                self._update_run(
                    row,
                    status=RunStatus.FAILED.value,
                    note=" · ".join(
                        note
                        for note in (
                            row.get("note", ""),
                            "süreç bu koşum analiz edilirken yine öldü ve bu kez hiçbir "
                            "senaryo tamamlanmadı — devam edilmedi, daha önce tamamlanan "
                            "teşhisler duruyor",
                        )
                        if note
                    ),
                )
                continue
            self._update_run(row, resume_count=attempts + 1, resume_mark=completed)
            resume.append(str(row["analyzer_run_id"]))
        return resume

    def get_run(self, analyzer_run_id: str) -> dict[str, Any] | None:
        """Return the run row plus the diagnoses finished so far."""
        run = self._repo.get(self._settings.table_runs, analyzer_run_id)
        if run is None:
            return None
        results = self._repo.list(
            self._settings.table_analysis_results,
            where={"analyzer_run_id": analyzer_run_id},
        )
        run["results"] = sorted(results, key=lambda row: row.get("scenario_name", ""))
        return run

    def _update_run(self, run: dict[str, Any], **fields: Any) -> None:
        run.update(fields)
        run["updated_at"] = _utcnow_iso()
        self._repo.save(self._settings.table_runs, run["analyzer_run_id"], run)

    async def _increment_completed(self, analyzer_run_id: str) -> None:
        async with self._run_row_lock:
            run = self._repo.get(self._settings.table_runs, analyzer_run_id)
            if run is not None:
                self._update_run(run, completed_count=run.get("completed_count", 0) + 1)

    async def run_analysis(self, analyzer_run_id: str) -> None:
        """THE single trigger entry point (queue-swap boundary)."""
        run = self._repo.get(self._settings.table_runs, analyzer_run_id)
        if run is None:
            return
        try:
            await self._run_job(run)
        except Exception as exc:
            self._update_run(
                run,
                status=RunStatus.FAILED.value,
                note=f"job failed: {type(exc).__name__}: {exc}",
            )

    async def _run_job(self, run: dict[str, Any]) -> None:
        settings = self._settings
        self._update_run(run, status=RunStatus.RUNNING.value)

        job_id = run.get("job_id", "")
        requested_run_id = run.get("run_id", "")
        summary = await self._source.resolve_run(job_id, requested_run_id)
        running_note = _running_note(summary.state)
        self._update_run(
            run,
            run_id=summary.run_id,
            note=" · ".join(note for note in (summary.note, running_note) if note),
        )

        forced_profile = STATE_PROFILE_OVERRIDE.get(summary.state, "")
        plan = plan_for(self._profiles, profil=run.get("profil", ""), forced=forced_profile)
        job = await self._source.fetch_job(summary, plan)
        self._update_run(
            run,
            job_id=summary.job_id,
            job_name=summary.job_name,
            profile_name=plan.profile.name,
            build_log_error=job.job_log.error,
            scenario_count=len(job.failed_scenarios),
            total_scenario_count=job.total_scenario_count,
        )

        groups = _group_scenarios(job.failed_scenarios)

        # What a previous attempt already finished. A diagnosis that exists is
        # never produced twice: the model was asked once and paid for once, and
        # a second row for the same scenario would be a duplicate answer.
        done = {
            _identity(str(row.get("scenario_id", "")), str(row.get("scenario_name", ""))): row
            for row in self._repo.list(
                settings.table_analysis_results,
                where={"analyzer_run_id": run["analyzer_run_id"]},
            )
        }
        resume_count = int(run.get("resume_count", 0))
        self._update_run(run, completed_count=len(done))

        run_notes = [
            note
            for note in (
                summary.note,
                running_note,
                _forced_note(forced_profile),
                _total_scenarios_note(summary.run_result),
                _grouped_note(groups, len(job.failed_scenarios)),
                _resumed_note(resume_count, len(done)),
            )
            if note
        ]

        if not job.failed_scenarios:
            self._update_run(
                run,
                status=RunStatus.DONE.value,
                note=" · ".join([*run_notes, "analiz edilecek hata yok"]),
            )
            return

        pending = [
            group
            for group in groups
            if _identity(group[0].scenario_id, group[0].scenario_name) not in done
        ]
        trace_errors: list[str] = []
        outcomes = await asyncio.gather(
            *(
                self._analyze_scenario(
                    run["analyzer_run_id"],
                    group[0],
                    run_id=summary.run_id,
                    plan=plan,
                    job_log=job.job_log,
                    trace_errors=trace_errors,
                )
                for group in pending
            ),
            return_exceptions=True,
        )

        escaped: list[BaseException] = []
        lost = 0
        for group, outcome in zip(pending, outcomes, strict=True):
            if isinstance(outcome, AnalysisResult):
                await self._share_with_group(outcome, group[1:], done)
            elif isinstance(outcome, BaseException):
                # The whole group is lost, not just its representative: the
                # others were never analyzed, they were waiting for its answer.
                escaped.append(outcome)
                lost += len(group)

        # Groups whose representative was answered before the process died, but
        # whose other members never got their copy.
        for group in groups:
            answered = done.get(_identity(group[0].scenario_id, group[0].scenario_name))
            if answered is not None and len(group) > 1:
                await self._share_with_group(AnalysisResult(**answered), group[1:], done)

        run = self._repo.get(settings.table_runs, run["analyzer_run_id"]) or run
        notes = list(run_notes)
        if trace_errors:
            kinds = ", ".join(sorted(set(trace_errors)))
            notes.append(
                f"{len(trace_errors)} senaryonun izi yazılamadı ({kinds}) — "
                "teşhisler kaydedildi, yalnız prompt/cevap dosyası yok"
            )
        if escaped:
            kinds = ", ".join(sorted({f"{type(e).__name__}: {e}" for e in escaped}))
            notes.append(
                f"{lost}/{len(job.failed_scenarios)} senaryo kaydedilemedi "
                f"({kinds}) — bu senaryoların sonucu yok"
            )
        self._update_run(run, status=RunStatus.DONE.value, note=" · ".join(notes))

    async def _share_with_group(
        self,
        source: AnalysisResult,
        members: list[RawScenario],
        done: dict[str, dict[str, Any]],
    ) -> None:
        """Give the group's answer to the members that do not have it yet."""
        for scenario in members:
            if _identity(scenario.scenario_id, scenario.scenario_name) in done:
                continue
            await self._save_shared_result(source, scenario)

    async def _save_shared_result(self, source: AnalysisResult, scenario: RawScenario) -> None:
        """Write one scenario's row from the diagnosis produced for another.

        The scenario keeps its own identity and its own error; only the answer
        is shared, and `grouped_with` names where it came from. Token counts and
        the call duration are NOT copied: they belong to the one call that was
        actually made. Neither are the quoted log lines — they were read out of
        ANOTHER scenario's log, and a row that quotes them would be claiming
        lines its own run never printed.
        """
        meta = AnalysisMeta(
            answered_by="group",
            llm_model=source.meta.llm_model,
            prompt_template=source.meta.prompt_template,
            prompt_version=source.meta.prompt_version,
            analyzed_at=_utcnow_iso(),
        )
        result = source.model_copy(
            update={
                "result_id": str(uuid4()),
                "scenario_name": scenario.scenario_name,
                "scenario_id": scenario.scenario_id,
                "error_text": scenario.error_text,
                "failed_step": scenario.failed_step,
                "grouped_with": source.scenario_name,
                "failure_reason": _shared_failure_reason(source),
                "most_relevant_log_lines": [],
                "meta": meta,
            }
        )
        self._repo.save(
            self._settings.table_analysis_results,
            result.result_id,
            result.model_dump(mode="json"),
        )
        await self._increment_completed(result.analyzer_run_id)

    async def _analyze_scenario(
        self,
        analyzer_run_id: str,
        scenario: RawScenario,
        *,
        run_id: str,
        plan: AnalysisPlan,
        job_log: JobLog,
        trace_errors: list[str],
    ) -> AnalysisResult:
        """Analyze one failed scenario; never raises.

        Its attachments are read HERE, not when the job was fetched: only a
        scenario that is actually analyzed is worth reading files for. A
        scenario that shares another's diagnosis never reaches this method, so
        nothing is fetched on its behalf.
        """
        async with self._llm_slots:
            settings = self._settings
            result_id = str(uuid4())

            prompt = ""
            raw_response = ""
            llm_request: dict = {}
            llm_content = ""
            http_status = 0
            meta = AnalysisMeta()
            analysis: LLMAnalysis | None = None
            findings: Findings | None = None
            skipped_no_evidence = False
            rule_failure = ""
            error_detail = ""

            precheck = type(self._precheck)
            try:
                # A check that needs no evidence runs FIRST: a catalogued failure
                # is answered without reading one file. Its key is the step and
                # the error, and both are already here.
                if not precheck.needs_evidence:
                    analysis = self._precheck.check(_scenario_facts(scenario, plan.profile))
                    if analysis is not None:
                        meta = AnalysisMeta(
                            answered_by=precheck.answered_by, analyzed_at=_utcnow_iso()
                        )

                if analysis is None:
                    scenario = await self._source.load_attachments(run_id, scenario, plan)
                    findings = self._extractor.extract(
                        scenario,
                        profile=plan.profile,
                        job_log=job_log,
                    )

                    if findings.evidence_report.rule_errors:
                        meta = AnalysisMeta(analyzed_at=_utcnow_iso())
                        raise _RuleFailure(" · ".join(findings.evidence_report.rule_errors))

                    precheck_result = (
                        self._precheck.check(findings) if precheck.needs_evidence else None
                    )
                    if precheck_result is not None:
                        analysis = precheck_result
                        raw_response = ""
                        meta = AnalysisMeta(
                            answered_by=precheck.answered_by,
                            analyzed_at=_utcnow_iso(),
                        )
                    elif not findings.has_evidence_for_llm:
                        skipped_no_evidence = True
                        meta = AnalysisMeta(analyzed_at=_utcnow_iso())
                    else:
                        prompt = self._builder.build(findings)
                        meta = AnalysisMeta(
                            prompt_template=findings.prompt_template,
                            prompt_version=self._builder.version_of(findings.prompt_template),
                            analyzed_at=_utcnow_iso(),
                        )
                        response = await self._llm.complete(prompt)
                        llm_request = response.request
                        llm_content = response.content
                        http_status = response.http_status
                        raw_response = response.raw_response or response.content
                        meta = meta.model_copy(
                            update={
                                "answered_by": "llm",
                                "llm_model": response.model,
                                "input_tokens": response.input_tokens,
                                "output_tokens": response.output_tokens,
                                "duration_ms": response.duration_ms,
                            }
                        )
                        parsed = try_json(response.content)
                        if parsed is not None:
                            try:
                                analysis = LLMAnalysis.model_validate(parsed)
                            except ValidationError:
                                analysis = None
            except _RuleFailure as exc:
                rule_failure = str(exc)
            except Exception as exc:
                error_detail = f"{type(exc).__name__}: {exc}"
                if not raw_response:
                    raw_response = f"<no response — {error_detail}>"

            failure_reason = (
                rule_failure
                if rule_failure
                else _skipped_reason(
                    prompt, findings, skipped_no_evidence, meta.answered_by, error_detail
                )
                if analysis is None
                else ""
            )
            if analysis is None and not failure_reason:
                failure_reason = (
                    f"model HTTP {http_status} döndü"
                    if http_status and http_status >= 400
                    else "model cevabı beklenen JSON şemasına uymadı"
                )

            if analysis is not None:
                result = AnalysisResult(
                    result_id=result_id,
                    analyzer_run_id=analyzer_run_id,
                    scenario_name=scenario.scenario_name,
                    scenario_id=scenario.scenario_id,
                    **analysis.model_dump(),
                    error_text=scenario.error_text,
                    failed_step=scenario.failed_step,
                    status=AnalysisStatus.OK,
                    meta=meta,
                )
            else:
                result = AnalysisResult(
                    result_id=result_id,
                    analyzer_run_id=analyzer_run_id,
                    scenario_name=scenario.scenario_name,
                    scenario_id=scenario.scenario_id,
                    failure_reason=failure_reason,
                    error_text=scenario.error_text,
                    failed_step=scenario.failed_step,
                    status=(
                        AnalysisStatus.NO_EVIDENCE
                        if skipped_no_evidence
                        else AnalysisStatus.ANALYSIS_FAILED
                    ),
                    meta=meta,
                )

            self._repo.save(
                settings.table_analysis_results,
                result_id,
                result.model_dump(mode="json"),
            )
            await self._increment_completed(analyzer_run_id)

            # AFTER the row is stored, never before: the trace is a debugging
            # aid, and a full disk must not throw away a diagnosis the model
            # was already asked — and paid — for.
            try:
                self._trace.write(
                    analyzer_run_id,
                    scenario.scenario_name,
                    scenario.scenario_id,
                    prompt=prompt,
                    response={
                        "raw_response": raw_response,
                        "content": llm_content,
                        "http_status": http_status,
                        "model": meta.llm_model,
                        "request": llm_request,
                        "input_tokens": meta.input_tokens,
                        "output_tokens": meta.output_tokens,
                        "duration_ms": meta.duration_ms,
                    },
                )
            except Exception as exc:
                trace_errors.append(f"{type(exc).__name__}: {exc}")

            return result
