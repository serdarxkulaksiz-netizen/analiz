"""Analysis orchestration (plan.md A13) — the whole chain wired together.

Redis-ready boundaries (plan.md A13):
  1. `run_analysis(analyzer_run_id)` is THE single trigger call — when a real
     queue replaces BackgroundTasks, only the call site changes.
  2. Status/results are always read from disk (Repository), never from
     in-memory state.

Full trace (plan.md A12): raw evidence -> `evidence`, prompt + raw answer ->
`prompts`, parsed diagnosis -> `analysis_results`, run status -> `runs`.
The same row id links a scenario's rows across evidence/prompts/analysis_results.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.config import Settings
from app.domain.enums import AnalysisStatus, Platform, RunStatus
from app.domain.findings import Findings
from app.domain.result import AnalysisMeta, AnalysisResult, LLMAnalysis
from app.extraction.base import Extractor
from app.llm.provider import LLMProvider
from app.parsing.json_parser import _try_json
from app.persistence.repository import Repository
from app.precheck.base import PreCheck
from app.prompting.builder import PromptBuilder
from app.source.base import Source
from app.source.models import RawScenario


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    ) -> None:
        self._settings = settings
        self._repo = repository
        self._source = source
        self._extractor = extractor
        self._builder = prompt_builder
        self._llm = llm_provider
        self._precheck = precheck
        # Serializes read-modify-write of the run row (completed_count).
        self._run_row_lock = asyncio.Lock()

    # ------------------------------------------------------------------ runs

    def create_run(self, bank: str, job_id: str, platform: Platform) -> str:
        """Persist a pending run row and return its analyzer_run_id."""
        analyzer_run_id = str(uuid4())
        now = _utcnow_iso()
        self._repo.save(
            self._settings.table_runs,
            analyzer_run_id,
            {
                "analyzer_run_id": analyzer_run_id,
                "bank": bank,
                "job_id": job_id,
                "platform": platform.value,
                "status": RunStatus.PENDING.value,
                "scenario_count": 0,
                "completed_count": 0,
                "total_scenario_count": 0,
                "note": "",
                "cached_from": "",
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
        results_run_id = run.get("cached_from") or analyzer_run_id
        results = [
            row
            for row in self._repo.list(self._settings.table_analysis_results)
            if row.get("analyzer_run_id") == results_run_id
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
        """THE single trigger entry point (queue-swap boundary, plan.md A13)."""
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

        if settings.cache_enabled:
            cached = self._find_cached_run(run)
            if cached is not None:
                self._update_run(
                    run,
                    status=RunStatus.DONE.value,
                    scenario_count=cached.get("scenario_count", 0),
                    completed_count=cached.get("completed_count", 0),
                    total_scenario_count=cached.get("total_scenario_count", 0),
                    cached_from=cached["analyzer_run_id"],
                    note="cache: aynı bank+job_id daha önce analiz edildi, sonuçlar diskten",
                )
                return

        platform = Platform(run["platform"])
        job = await self._source.fetch_job(run["bank"], run["job_id"], platform)
        self._update_run(
            run,
            scenario_count=len(job.failed_scenarios),
            total_scenario_count=job.total_scenario_count,
        )

        if not job.failed_scenarios:
            self._update_run(
                run, status=RunStatus.DONE.value, note="analiz edilecek hata yok"
            )
            return

        semaphore = asyncio.Semaphore(settings.max_concurrency)
        await asyncio.gather(
            *(
                self._analyze_scenario(
                    run["analyzer_run_id"],
                    scenario,
                    bank=job.bank,
                    jenkins_console_log=job.jenkins_console_log,
                    semaphore=semaphore,
                )
                for scenario in job.failed_scenarios
            ),
            return_exceptions=True,
        )
        run = self._repo.get(settings.table_runs, run["analyzer_run_id"]) or run
        self._update_run(run, status=RunStatus.DONE.value)

    def _find_cached_run(self, run: dict[str, Any]) -> dict[str, Any] | None:
        """Find a previously finished run for the same bank+job_id."""
        for row in self._repo.list(self._settings.table_runs):
            if (
                row.get("analyzer_run_id") != run["analyzer_run_id"]
                and row.get("bank") == run["bank"]
                and row.get("job_id") == run["job_id"]
                and row.get("status") == RunStatus.DONE.value
                and not row.get("cached_from")
                and not row.get("note")  # only fully analyzed runs are reusable
            ):
                return row
        return None

    def _screenshot_paths(self, scenario: RawScenario) -> list[str]:
        return [
            path
            for path in (scenario.web_screenshot_path, scenario.mobile_screenshot_path)
            if path
        ]

    async def _analyze_scenario(
        self,
        analyzer_run_id: str,
        scenario: RawScenario,
        *,
        bank: str,
        jenkins_console_log: str,
        semaphore: asyncio.Semaphore,
    ) -> None:
        """Analyze one failed scenario; never raises (plan.md A9)."""
        async with semaphore:
            settings = self._settings
            result_id = str(uuid4())

            # Full trace, part 1: raw evidence as received (all raw paths).
            self._repo.save(
                settings.table_evidence,
                result_id,
                {
                    "result_id": result_id,
                    "analyzer_run_id": analyzer_run_id,
                    "scenario_name": scenario.scenario_name,
                    "platform": scenario.platform.value,
                    "screenshot_paths": self._screenshot_paths(scenario),
                    "raw_scenario": scenario.model_dump(mode="json"),
                },
            )

            prompt = ""
            raw_response = ""
            meta = AnalysisMeta()
            analysis: LLMAnalysis | None = None
            findings: Findings | None = None

            try:
                findings = self._extractor.extract(
                    scenario, bank=bank, jenkins_console_log=jenkins_console_log
                )

                # PreCheck (plan.md A7): may short-circuit before the LLM.
                precheck_result = self._precheck.check(findings)
                if precheck_result is not None:
                    analysis = precheck_result
                    raw_response = ""
                    meta = AnalysisMeta(llm_model="precheck", analyzed_at=_utcnow_iso())
                else:
                    prompt = self._builder.build(findings)
                    # Size management (plan.md A11): tokens are measured on the
                    # combined prompt; trimming (when threshold is exceeded) is
                    # delegated to each Evidence's content selector — passthrough
                    # today, so nothing is cut. Real limit tuned on the work PC.
                    response = await self._llm.complete(prompt)
                    raw_response = response.content
                    meta = AnalysisMeta(
                        llm_model=response.model,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        duration_ms=response.duration_ms,
                        analyzed_at=_utcnow_iso(),
                    )
                    parsed = _try_json(raw_response)
                    if parsed is not None:
                        try:
                            analysis = LLMAnalysis.model_validate(parsed)
                        except ValidationError:
                            analysis = None
            except Exception as exc:
                # Timeout / transport / stub NotImplementedError / anything:
                # mark this scenario failed, keep the job going.
                if not raw_response:
                    raw_response = f"<no response — {type(exc).__name__}: {exc}>"

            # Platform-appropriate (registry-filtered) stored screenshots.
            missing_evidence = findings.missing_evidence if findings else []
            result_screenshots = findings.screenshot_paths if findings else []

            # Full trace, part 2: exact prompt + raw answer.
            self._repo.save(
                settings.table_prompts,
                result_id,
                {
                    "result_id": result_id,
                    "analyzer_run_id": analyzer_run_id,
                    "scenario_name": scenario.scenario_name,
                    "prompt": prompt,
                    "raw_response": raw_response,
                },
            )

            # Full trace, part 3: the diagnosis row (or a marked failure).
            if analysis is not None:
                result = AnalysisResult(
                    result_id=result_id,
                    analyzer_run_id=analyzer_run_id,
                    **analysis.model_dump(),
                    platform=scenario.platform.value,
                    bank=bank,
                    screenshot_paths=result_screenshots,
                    missing_evidence=missing_evidence,
                    raw_llm_response=raw_response,
                    status=AnalysisStatus.OK,
                    meta=meta,
                )
            else:
                # No fabricated analysis text (plan.md A10): only factual
                # identity fields are filled by the system.
                result = AnalysisResult(
                    result_id=result_id,
                    analyzer_run_id=analyzer_run_id,
                    scenario_name=scenario.scenario_name,
                    platform=scenario.platform.value,
                    bank=bank,
                    screenshot_paths=result_screenshots,
                    missing_evidence=missing_evidence,
                    raw_llm_response=raw_response,
                    status=AnalysisStatus.ANALYSIS_FAILED,
                    meta=meta,
                )

            self._repo.save(
                settings.table_analysis_results,
                result_id,
                result.model_dump(mode="json"),
            )
            await self._increment_completed(analyzer_run_id)
