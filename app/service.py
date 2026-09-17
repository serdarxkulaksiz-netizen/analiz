"""Analysis orchestration — the whole chain wired together."""

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

STATE_PROFILE_OVERRIDE: dict[str, str] = {RunState.FAILED.value: JOB_FAILED_PROFILE_NAME}


def _skipped_reason(
    prompt: str, findings: Findings | None, no_evidence: bool, answered_by: str
) -> str:
    """Why no prompt was built for this scenario ("" when one was)."""
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
        self._run_row_lock = asyncio.Lock()

    def create_run(
        self,
        parameter1: str,
        job_id: str,
        parameter2: str,
        run_id: str = "",
    ) -> str:
        """Persist a pending run row and return its analyzer_run_id."""
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
                "run_id": run_id,
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
        profile_job_id = job_id or summary.job_id

        plan = plan_for(self._profiles, job_id=profile_job_id, forced=forced_profile)
        job = await self._source.fetch_job(summary, plan)
        self._update_run(
            run,
            job_name=summary.job_name,
            raw_run_response=summary.raw,
            raw_results_response=job.raw_results_response,
            build_log_path=job.job_log.stored_path,
            build_log_chars=len(job.job_log.text),
            build_log_error=job.job_log.error,
            scenario_count=len(job.failed_scenarios),
            total_scenario_count=job.total_scenario_count,
        )

        run_notes = [
            note
            for note in (
                summary.note,
                running_note,
                _forced_note(forced_profile),
                _total_scenarios_note(summary.run_result),
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

        escaped = [o for o in outcomes if isinstance(o, BaseException)]

        run = self._repo.get(settings.table_runs, run["analyzer_run_id"]) or run
        notes = list(run_notes)
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
            raw_response = ""
            llm_request: dict = {}
            llm_content = ""
            http_status = 0
            meta = AnalysisMeta()
            analysis: LLMAnalysis | None = None
            findings: Findings | None = None
            skipped_no_evidence = False
            rule_failure = ""

            try:
                findings = self._extractor.extract(
                    scenario,
                    profile=profile,
                    job_log=job_log,
                )

                if findings.evidence_report.rule_errors:
                    meta = AnalysisMeta(analyzed_at=_utcnow_iso())
                    raise _RuleFailure(" · ".join(findings.evidence_report.rule_errors))

                precheck_result = self._precheck.check(findings)
                if precheck_result is not None:
                    analysis = precheck_result
                    raw_response = ""
                    meta = AnalysisMeta(answered_by="precheck", analyzed_at=_utcnow_iso())
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

            profile_name = findings.profile_name if findings else ""

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

            self._repo.save(
                settings.table_prompts,
                result_id,
                {
                    "result_id": result_id,
                    "analyzer_run_id": analyzer_run_id,
                    "scenario_name": scenario.scenario_name,
                    "prompt": prompt,
                    "prompt_chars": len(prompt),
                    "skipped_reason": failure_reason,
                    "request": llm_request,
                },
            )

            self._repo.save(
                settings.table_llm_responses,
                result_id,
                {
                    "result_id": result_id,
                    "analyzer_run_id": analyzer_run_id,
                    "scenario_name": scenario.scenario_name,
                    "raw_response": raw_response,
                    "content": llm_content,
                    "answered_by": meta.answered_by,
                    "model": meta.llm_model,
                    "http_status": http_status,
                    "input_tokens": meta.input_tokens,
                    "output_tokens": meta.output_tokens,
                    "duration_ms": meta.duration_ms,
                },
            )

            if analysis is not None:
                result = AnalysisResult(
                    result_id=result_id,
                    analyzer_run_id=analyzer_run_id,
                    scenario_name=scenario.scenario_name,
                    **analysis.model_dump(),
                    profile_name=profile_name,
                    status=AnalysisStatus.OK,
                    meta=meta,
                )
            else:
                result = AnalysisResult(
                    result_id=result_id,
                    analyzer_run_id=analyzer_run_id,
                    scenario_name=scenario.scenario_name,
                    failure_reason=failure_reason,
                    profile_name=profile_name,
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
