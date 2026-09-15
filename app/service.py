"""Analysis orchestration — the whole chain wired together.

Redis-ready boundaries:
  1. `run_analysis(analyzer_run_id)` is THE single trigger call — when a real
     queue replaces BackgroundTasks, only the call site changes.
  2. Status/results are always read from disk (Repository), never from
     in-memory state.

Full trace, one row per table per scenario, linked by the same
`result_id`: raw evidence -> `evidence`, outgoing prompt+request -> `prompts`,
incoming LLM answer -> `llm_responses`, parsed diagnosis -> `analysis_results`;
run status -> `runs`.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.config import Settings
from app.domain.enums import AnalysisStatus, RunState, RunStatus
from app.domain.findings import Findings
from app.domain.result import AnalysisMeta, AnalysisResult, LLMAnalysis
from app.evidence.plan import plan_for
from app.evidence.profiles import JOB_FAILED_PROFILE_NAME, Profile, ProfileRegistry
from app.extraction.base import Extractor
from app.llm.provider import LLMProvider
from app.parsing.json_parser import try_json
from app.persistence.repository import Repository
from app.precheck.base import PreCheck
from app.prompting.builder import PromptBuilder
from app.source.base import Source
from app.source.models import JobLog, RawScenario

#: Job-level run state -> the profile every scenario of that run is analyzed
#: with, bypassing the job_ids mapping (a state absent here resolves normally).
#: A registry, not an `if`: a new state is one row.
STATE_PROFILE_OVERRIDE: dict[str, str] = {RunState.FAILED.value: JOB_FAILED_PROFILE_NAME}


def _skipped_reason(
    prompt: str, findings: Findings | None, no_evidence: bool, answered_by: str
) -> str:
    """Why no prompt was built for this scenario ("" when one was).

    A `prompts` row whose `prompt` is empty used to say nothing about why, so
    "the profile sends nothing", "the evidence never arrived" and "extraction
    crashed" all looked the same: an empty file.

    Every branch is READ from what happened, never inferred. "PreCheck answered"
    comes from `answered_by` and not from "there was no prompt and no evidence
    gap" — which was also true when building the prompt itself crashed, and the
    row then blamed a PreCheck rule that had never run.
    """
    if prompt:
        return ""
    if answered_by == "precheck":
        return "precheck kuralı cevapladı — LLM çağrılmadı"
    if findings is None:
        return "kanıt çıkarımı hata verdi — prompt kurulamadı"
    if not no_evidence:
        return "prompt kurulamadı — hata ayrıntısı llm_responses.raw_response satırında"

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
    """A content rule failed — this scenario stops, the run does not.

    Its own type so the handler can tell a decision ("the rule could not slice
    this log") from an accident ("the LLM timed out") and record each as what
    it is.
    """


def _running_note(state: str) -> str:
    """Say it when the analyzed run had not finished yet ("" when it had).

    Only a caller who names a `run_id` can get here, and only deliberately.
    What they get back is a diagnosis of whatever evidence existed at that
    moment — fewer scenarios, half-written logs, screenshots not taken yet — so
    the row has to carry that, or the answer reads like a complete one.
    """
    if state != RunState.RUNNING.value:
        return ""
    return (
        "koşum hâlâ sürüyordu (state=RUNNING) — kanıtlar eksik olabilir, "
        "teşhis o ana kadar yazılanlara dayanıyor"
    )


def _total_scenarios_note(run_result: dict[str, Any]) -> str:
    """Say it when VisiumGo did not report the run's scenario total.

    `total_scenario_count` is then 0 — which must not read as "this run had no
    scenarios". The count is never substituted with one of our own.
    """
    if "totalScenarios" in run_result:
        return ""
    return "runResult.totalScenarios gelmedi — toplam senaryo sayısı bilinmiyor (0 yazıldı)"


def _forced_note(profile_name: str) -> str:
    """Say it out loud when the normal profile resolution was bypassed.

    Without this the run row would look like an ordinary analysis while every
    scenario was actually judged with a different profile.
    """
    if not profile_name:
        return ""
    return f"'{profile_name}' profili kullanıldı (job durumu FAILED)"


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


class AnalyzerService:
    """Coordinates Source -> Extraction -> PreCheck -> Prompt -> LLM -> Parse -> Persist."""

    def __init__(
        self,
        settings: Settings,
        repository: Repository,
        source: Source,
        extractor: Extractor,
        prompt_builder: PromptBuilder,
        llm_provider: LLMProvider,
        precheck: PreCheck,
        profiles: ProfileRegistry,
    ) -> None:
        self._settings = settings
        self._repo = repository
        self._source = source
        self._extractor = extractor
        self._profiles = profiles
        self._builder = prompt_builder
        self._llm = llm_provider
        self._precheck = precheck
        # Serializes read-modify-write of the run row (completed_count).
        self._run_row_lock = asyncio.Lock()

    # ------------------------------------------------------------------ runs

    def create_run(
        self,
        parameter1: str,
        job_id: str,
        parameter2: str,
        run_id: str = "",
    ) -> str:
        """Persist a pending run row and return its analyzer_run_id.

        `parameter1`/`parameter2` are written down and never read again: they are
        reserved request keys, visible through the API, and they take no part in
        profile selection, extraction or the prompt. This is the ONLY place they
        are touched.
        """
        analyzer_run_id = str(uuid4())
        now = _utcnow_iso()
        self._repo.save(
            self._settings.table_runs,
            analyzer_run_id,
            {
                "analyzer_run_id": analyzer_run_id,
                "parameter1": parameter1,
                "parameter2": parameter2,
                "job_id": job_id,
                "run_id": run_id,  # requested; resolved value filled after fetch
                "status": RunStatus.PENDING.value,
                "scenario_count": 0,
                "completed_count": 0,
                "total_scenario_count": 0,
                "job_name": "",
                "raw_run_response": {},
                "raw_results_response": [],
                "build_log_path": "",
                "build_log_chars": 0,
                "build_log_error": "",
                "note": "",
                "created_at": now,
                "updated_at": now,
            },
        )
        return analyzer_run_id

    def get_run(self, analyzer_run_id: str) -> dict[str, Any] | None:
        """Read run status + finished diagnoses from disk (never from memory)."""
        run = self._repo.get(self._settings.table_runs, analyzer_run_id)
        if run is None:
            return None
        results = [
            row
            for row in self._repo.list(self._settings.table_analysis_results)
            if row.get("analyzer_run_id") == analyzer_run_id
        ]
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

    # -------------------------------------------------------------- analysis

    async def run_analysis(self, analyzer_run_id: str) -> None:
        """THE single trigger entry point (queue-swap boundary).

        Which profile runs is decided from the job and the run's state — there
        is no caller-supplied override. One existed for a tool that forced a
        fetch-everything profile; the tool is gone, and a parameter nobody
        passes is a branch nobody tests.
        """
        run = self._repo.get(self._settings.table_runs, analyzer_run_id)
        if run is None:
            return
        try:
            await self._run_job(run)
        except Exception as exc:
            # Job-level failure (e.g. source unreachable): the run ends as
            # `failed` with an explanatory note instead of hanging in `running`.
            self._update_run(
                run,
                status=RunStatus.FAILED.value,
                note=f"job failed: {type(exc).__name__}: {exc}",
            )

    async def _run_job(self, run: dict[str, Any]) -> None:
        settings = self._settings
        self._update_run(run, status=RunStatus.RUNNING.value)

        # Resolve which run this is BEFORE fetching anything: the job-level
        # state decides whether there is anything to analyze at all, and the
        # resolved id is what every later call is made against. One lookup,
        # never repeated.
        job_id = run.get("job_id", "")
        requested_run_id = run.get("run_id", "")  # what the caller asked for
        summary = await self._source.resolve_run(job_id, requested_run_id)
        # A run the caller named BY ID is analyzed whatever its state, RUNNING
        # included: naming one run is an explicit instruction to look at THAT
        # run, and refusing it left the caller no way to ask. The state is not
        # ignored — it is written on the row, because a diagnosis built from a
        # half-written run must not read like one built from a finished run.
        # The job_id path never reaches this: `_select_run` only ever returns
        # a finished run, since "the newest run" is a choice we make and a
        # running one is the wrong choice.
        running_note = _running_note(summary.state)
        self._update_run(
            run,
            run_id=summary.run_id,
            note=" · ".join(note for note in (summary.note, running_note) if note),
        )

        # A job-level failure means the job's own profile describes a run that
        # never happened, so every scenario goes to one fixed profile instead.
        forced_profile = STATE_PROFILE_OVERRIDE.get(summary.state, "")
        # The profile follows the job the CALLER named; with only a run_id it
        # is the job that run belongs to (from the run response).
        profile_job_id = job_id or summary.job_id

        # The profile decides what is worth downloading, so it is resolved
        # BEFORE the evidence is fetched — not after, when the bytes are
        # already paid for. Resolved ONCE: this object is what every later step
        # reads, so "which profile ran" has one answer for the whole run.
        plan = plan_for(self._profiles, job_id=profile_job_id, forced=forced_profile)
        job = await self._source.fetch_job(summary, plan)
        self._update_run(
            run,
            run_id=summary.run_id,
            job_name=summary.job_name,
            # Full raw traces (save-everything rule). `runResult` is inside the
            # run response; storing it again as its own column put the same
            # numbers in the row twice.
            raw_run_response=summary.raw,
            raw_results_response=job.raw_results_response,
            # The build log itself is a FILE under `database/build_logs/`, not a
            # column: it covers a whole run and would dwarf the row that is read
            # for status. The row keeps the pointer and the size.
            build_log_path=job.job_log.stored_path,
            build_log_chars=len(job.job_log.text),
            # Empty unless the build log SHOULD have arrived and did not: the
            # reason is recorded so a misconfigured/failing endpoint cannot hide
            # as "this job simply had no build log". Does not fail the run.
            build_log_error=job.job_log.error,
            scenario_count=len(job.failed_scenarios),
            total_scenario_count=job.total_scenario_count,
        )

        if not job.failed_scenarios:
            notes = [note for note in (summary.note, "analiz edilecek hata yok") if note]
            self._update_run(run, status=RunStatus.DONE.value, note=" · ".join(notes))
            return

        semaphore = asyncio.Semaphore(settings.max_concurrency)
        outcomes = await asyncio.gather(
            *(
                self._analyze_scenario(
                    run["analyzer_run_id"],
                    scenario,
                    profile=plan.profile,
                    job_log=job.job_log,
                    semaphore=semaphore,
                )
                for scenario in job.failed_scenarios
            ),
            return_exceptions=True,
        )

        # `_analyze_scenario` handles its own errors, but its four repository
        # writes sit outside that guard: a disk/permission/serialization failure
        # would escape here. `return_exceptions=True` would then DROP it
        # silently — the run would report `done` with a missing result row and
        # nobody would ever learn why. So record what escaped.
        escaped = [o for o in outcomes if isinstance(o, BaseException)]

        run = self._repo.get(settings.table_runs, run["analyzer_run_id"]) or run
        notes = [
            note
            for note in (
                summary.note,
                running_note,
                _forced_note(forced_profile),
                _total_scenarios_note(summary.run_result),
            )
            if note
        ]
        if escaped:
            kinds = ", ".join(sorted({f"{type(e).__name__}: {e}" for e in escaped}))
            notes.append(
                f"{len(escaped)}/{len(job.failed_scenarios)} senaryo kaydedilemedi "
                f"({kinds}) — bu senaryoların sonucu diskte yok"
            )
        self._update_run(run, status=RunStatus.DONE.value, note=" · ".join(notes))

    async def _analyze_scenario(
        self,
        analyzer_run_id: str,
        scenario: RawScenario,
        *,
        profile: Profile,
        job_log: JobLog,
        semaphore: asyncio.Semaphore,
    ) -> None:
        """Analyze one failed scenario; never raises."""
        async with semaphore:
            settings = self._settings
            result_id = str(uuid4())

            prompt = ""
            raw_response = ""  # full LLM envelope (kept even if parsing fails)
            llm_request: dict = {}
            llm_content = ""  # extracted message content (may be empty)
            http_status = 0  # 0 = no response at all (transport failure)
            meta = AnalysisMeta()
            analysis: LLMAnalysis | None = None
            findings: Findings | None = None
            #: Set when the prompt would have carried no evidence at all.
            skipped_no_evidence = False
            #: Set when a profile's content rule could not shape its evidence.
            rule_failure = ""

            try:
                findings = self._extractor.extract(
                    scenario,
                    profile=profile,
                    job_log=job_log,
                )

                # A content rule that could not do its job stops this
                # scenario here. Its evidence has no shaped content, and the
                # unshaped original is exactly what the profile said not to
                # send — so there is nothing to ask about.
                if findings.evidence_report.rule_errors:
                    meta = AnalysisMeta(analyzed_at=_utcnow_iso())
                    raise _RuleFailure(" · ".join(findings.evidence_report.rule_errors))

                # PreCheck: may short-circuit before the LLM.
                precheck_result = self._precheck.check(findings)
                if precheck_result is not None:
                    analysis = precheck_result
                    raw_response = ""
                    # `llm_model` names a MODEL; no model ran, so it stays
                    # empty and `answered_by` says who did answer.
                    meta = AnalysisMeta(answered_by="precheck", analyzed_at=_utcnow_iso())
                elif not findings.has_evidence_for_llm:
                    # Every block is empty and there is no error text: the
                    # model could only answer "kanıt yok",
                    # which the system already knows. Skip the call and say so,
                    # without fabricating a diagnosis.
                    skipped_no_evidence = True
                    meta = AnalysisMeta(analyzed_at=_utcnow_iso())
                else:
                    prompt = self._builder.build(findings)
                    prompt_template = findings.prompt_template
                    prompt_version = self._builder.version_of(prompt_template)
                    # Size management happened upstream: each
                    # Evidence applied its profile's content rules, and any cut
                    # is flagged on the Findings. There is no token threshold —
                    # prompt size is recorded (`prompt_chars`) so a real limit
                    # can be set from measurement instead of guesswork.
                    response = await self._llm.complete(prompt)
                    llm_request = response.request
                    llm_content = response.content
                    http_status = response.http_status
                    # Save the FULL envelope (fallback to content for simple
                    # providers that don't populate it); parse the diagnosis
                    # from the message content only.
                    raw_response = response.raw_response or response.content
                    meta = AnalysisMeta(
                        answered_by="llm",
                        llm_model=response.model,
                        prompt_template=prompt_template,
                        prompt_version=prompt_version,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        duration_ms=response.duration_ms,
                        analyzed_at=_utcnow_iso(),
                    )
                    parsed = try_json(response.content)
                    if parsed is not None:
                        try:
                            analysis = LLMAnalysis.model_validate(parsed)
                        except ValidationError:
                            analysis = None
            except _RuleFailure as exc:
                # Not an accident: a decision. The reason is already readable,
                # so it is not dressed up as a missing LLM response.
                rule_failure = str(exc)
            except Exception as exc:
                # Timeout / transport / stub NotImplementedError / anything:
                # mark this scenario failed, keep the job going.
                if not raw_response:
                    raw_response = f"<no response — {type(exc).__name__}: {exc}>"

            failure_reason = (
                rule_failure
                if rule_failure
                else _skipped_reason(prompt, findings, skipped_no_evidence, meta.answered_by)
                if analysis is None
                else ""
            )
            if analysis is None and not failure_reason:
                failure_reason = "LLM cevabı alınamadı ya da ayrıştırılamadı — ham cevap saklandı"

            # Profile-driven flags (empty when extraction itself failed).
            profile_name = findings.profile_name if findings else ""

            # Part 1: what extraction saw — which attachments arrived, which
            # evidence class each mapped to, what reached the prompt, what got
            # cut, and where each file landed on disk.
            #
            # The file CONTENTS are not copied in here. They used to be, so a
            # text attachment was stored twice: once as a file under
            # `database/attachments/` and again inside this row. Nothing ever
            # read the copy back — this table is written and never queried — and
            # the questions it was meant to answer are answered by the file
            # itself (the raw evidence) and by the `prompts` row (what the model
            # actually saw).
            self._repo.save(
                settings.table_evidence,
                result_id,
                {
                    "result_id": result_id,
                    "analyzer_run_id": analyzer_run_id,
                    "scenario_name": scenario.scenario_name,
                    "evidence_report": (findings.evidence_report.model_dump() if findings else {}),
                },
            )

            # Full trace, part 2: the OUTGOING side — prompt + exact request.
            self._repo.save(
                settings.table_prompts,
                result_id,
                {
                    "result_id": result_id,
                    "analyzer_run_id": analyzer_run_id,
                    "scenario_name": scenario.scenario_name,
                    "prompt": prompt,
                    # Prompt size, so an oversized prompt is measurable instead
                    # of guessed (measure before setting limits).
                    "prompt_chars": len(prompt),
                    # Why there is no prompt, when there is none. An empty
                    # `prompt` with no reason next to it is the one thing this
                    # row must never be: unreadable.
                    "skipped_reason": failure_reason,
                    "request": llm_request,
                },
            )

            # Full trace, part 3: the INCOMING side — exactly what the LLM
            # returned (full envelope + extracted content + call meta).
            self._repo.save(
                settings.table_llm_responses,
                result_id,
                {
                    "result_id": result_id,
                    "analyzer_run_id": analyzer_run_id,
                    "scenario_name": scenario.scenario_name,
                    "raw_response": raw_response,
                    "content": llm_content,
                    # Who answered and how it went. `model` is what the
                    # service reported; empty means it reported none.
                    "answered_by": meta.answered_by,
                    "model": meta.llm_model,
                    "http_status": http_status,
                    "input_tokens": meta.input_tokens,
                    "output_tokens": meta.output_tokens,
                    "duration_ms": meta.duration_ms,
                },
            )

            # Full trace, part 3: the diagnosis row (or a marked failure).
            if analysis is not None:
                result = AnalysisResult(
                    result_id=result_id,
                    analyzer_run_id=analyzer_run_id,
                    **analysis.model_dump(),
                    profile_name=profile_name,
                    raw_llm_response=raw_response,
                    status=AnalysisStatus.OK,
                    meta=meta,
                )
            else:
                # No fabricated analysis text: only factual
                # identity fields are filled by the system.
                result = AnalysisResult(
                    result_id=result_id,
                    analyzer_run_id=analyzer_run_id,
                    scenario_name=scenario.scenario_name,
                    failure_reason=failure_reason,
                    profile_name=profile_name,
                    raw_llm_response=raw_response,
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
