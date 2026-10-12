"""VisiumGoSource — real VisiumGo API client."""

import asyncio
import io
import zipfile
from typing import Any

from app.domain.enums import ANALYZABLE_RUN_STATES, RunState
from app.source.base import DownloadPlan, Source
from app.source.models import Attachment, JobData, JobLog, RawScenario, RunSummary
from app.source.visiumgo_client import VisiumGoClient, encode_segment

_BUILD_LOG_ERROR_MAX_CHARS = 500

PATH_RUN = "/api/runs/{run_id}"
PATH_RUNS = "/api/runs"
PATH_RESULTS = "/api/runs/{run_id}/results"
PATH_LOGS = "/api/runs/{run_id}/logs"

_SHAPE_ERROR_SAMPLE = 200


def _as_list(value: Any, path: str) -> list[dict[str, Any]]:
    """The endpoint promises an array of objects. Say so when it is not."""
    if not isinstance(value, list):
        raise ValueError(
            f"{path}: dizi bekleniyordu, {type(value).__name__} geldi — "
            f"gelen: {str(value)[:_SHAPE_ERROR_SAMPLE]}"
        )
    bad = next((row for row in value if not isinstance(row, dict)), None)
    if bad is not None:
        raise ValueError(
            f"{path}: dizinin elemanları nesne olmalıydı, {type(bad).__name__} var — "
            f"gelen: {str(value)[:_SHAPE_ERROR_SAMPLE]}"
        )
    return value


def _as_dict(value: Any, path: str) -> dict[str, Any]:
    """The endpoint promises one object. Say so when it is not."""
    if not isinstance(value, dict):
        raise ValueError(
            f"{path}: nesne bekleniyordu, {type(value).__name__} geldi — "
            f"gelen: {str(value)[:_SHAPE_ERROR_SAMPLE]}"
        )
    return value


PATH_SCENARIO_DETAIL = "/api/runs/{run_id}/results/{scenario_id}"

#: VisiumGo reports the failing step TWICE, and in a real response the two agree
#: word for word: `properties["failedStep.name"]` and the `stepResults` entry
#: whose `resultType` is FAILED (its `line`). Both are read — see
#: `_failed_step_of`. What is deliberately NOT read: `failedStep.line`,
#: `failedStep.location` and `duration`. A feature file edit shifts the line and
#: every run has its own duration; the BDD sentence is what stays the same, and
#: that is what two scenarios have to share to be called the same failure.
DETAIL_PROPERTIES_KEY = "properties"
FAILED_STEP_PROPERTY = "failedStep.name"
DETAIL_STEPS_KEY = "stepResults"
STEP_SENTENCE_KEY = "line"
RESULT_FAILED = "FAILED"

_FETCH_ERROR_MAX_CHARS = 500

_TEXT_EXTENSIONS = frozenset({".log", ".properties", ".html", ".xml"})


def _state_of(record: dict[str, Any]) -> str:
    """Job-level state of a run record (`runResult.state`), "" if absent."""
    return str((record.get("runResult") or {}).get("state", ""))


def _run_order_key(record: dict[str, Any]) -> tuple[int, int, str]:
    """Sort key for picking the newest run: the largest `id` wins."""
    raw = str(record.get("id", ""))
    try:
        return (1, int(raw), "")
    except ValueError:
        return (0, 0, raw)


def _failed_step_of(detail: dict[str, Any]) -> str:
    """The BDD sentence of the step that failed, "" when the source did not say.

    The property is read first because there it is STATED; the step list is the
    fallback, where it is derived from whichever entry failed. A response that
    carries one and not the other still answers.
    """
    properties = detail.get(DETAIL_PROPERTIES_KEY) or {}
    if isinstance(properties, dict):
        stated = str(properties.get(FAILED_STEP_PROPERTY, "")).strip()
        if stated:
            return stated

    for step in detail.get(DETAIL_STEPS_KEY) or []:
        if isinstance(step, dict) and str(step.get("resultType", "")) == RESULT_FAILED:
            return str(step.get(STEP_SENTENCE_KEY, "")).strip()
    return ""


def _summary_from(record: dict[str, Any], *, job_id: str = "", note: str = "") -> RunSummary:
    """Build the resolved-run summary from a raw run record."""
    run_result = record.get("runResult") or {}
    return RunSummary(
        run_id=str(record.get("id", "")),
        job_id=job_id or str(record.get("jobId", "")),
        job_name=str(record.get("jobName", "")),
        state=_state_of(record),
        run_result=run_result,
        raw=record,
        note=note,
    )


class VisiumGoSource(Source):
    """Fetches real job evidence from a VisiumGo instance."""

    def __init__(
        self,
        client: VisiumGoClient,
        build_log_entry: str = "build.log",
        max_parallel: int = 2,
    ) -> None:
        self._client = client
        self._build_log_entry = build_log_entry
        self._max_parallel = max_parallel

    async def aclose(self) -> None:
        """Close the pooled HTTP connections."""
        await self._client.aclose()

    async def get_run(self, run_id: str) -> dict[str, Any]:
        """`GET /api/runs/{run_id}` — one run."""
        path = PATH_RUN.format(run_id=encode_segment(run_id))
        return _as_dict(await self._client.get_json(path), path)

    async def list_runs(self, job_id: str) -> list[dict[str, Any]]:
        """`GET /api/runs?jobId=` — a job's runs, each in the `get_run` shape."""
        return _as_list(await self._client.get_json(PATH_RUNS, params={"jobId": job_id}), PATH_RUNS)

    async def get_results(self, run_id: str) -> list[dict[str, Any]]:
        """`GET /api/runs/{run_id}/results` — the run's scenarios."""
        path = PATH_RESULTS.format(run_id=encode_segment(run_id))
        return _as_list(await self._client.get_json(path), path)

    async def get_scenario_detail(self, run_id: str, scenario_id: str) -> dict[str, Any]:
        """`GET /api/runs/{run_id}/results/{scenario_id}` — one scenario."""
        path = PATH_SCENARIO_DETAIL.format(
            run_id=encode_segment(run_id), scenario_id=encode_segment(scenario_id)
        )
        return _as_dict(await self._client.get_json(path), path)

    async def fetch_build_log(self, run_id: str) -> tuple[str, str]:
        """Job-level build log, served by VisiumGo."""
        path = PATH_LOGS.format(run_id=encode_segment(run_id))
        try:
            archive = await self._client.get_bytes(path)
            return self._extract_log(archive), ""
        except Exception as exc:
            reason = f"{path}: {type(exc).__name__}: {exc}"
            return "", reason[:_BUILD_LOG_ERROR_MAX_CHARS]

    @staticmethod
    def describe_attachment(meta: dict[str, Any]) -> Attachment:
        """One `attachments[]` row as an Attachment — metadata only, no bytes."""
        return Attachment(
            file_name=str(meta.get("fileName", "")),
            mime_type=str(meta.get("mimeType", "")),
            device_id=str(meta.get("deviceId", "")),
        )

    async def download_attachment(
        self, run_id: str, meta: dict[str, Any], scenario_id: str = ""
    ) -> Attachment:
        """Adım D: download one attachment (URL-encoded) and save it to disk."""
        attachment = self.describe_attachment(meta)
        file_name = attachment.file_name
        path = f"/api/runs/{encode_segment(run_id)}/attachments/{encode_segment(file_name)}"
        is_text = (
            attachment.mime_type.startswith("text/") or attachment.extension in _TEXT_EXTENSIONS
        )

        try:
            if is_text:
                text = await self._client.get_text(path)
                return attachment.model_copy(update={"content": text})
            await self._client.get_bytes(path)
            return attachment
        except Exception as exc:
            reason = f"{path}: {type(exc).__name__}: {exc}"
            return attachment.model_copy(update={"download_error": reason[:_FETCH_ERROR_MAX_CHARS]})

    async def resolve_run(self, job_id: str, run_id: str = "") -> RunSummary:
        """Adım A: which run to analyze (see `Source.resolve_run`)."""
        if run_id:
            record = await self.get_run(run_id)
            summary = _summary_from(record or {}, job_id=job_id)
            if not summary.run_id:
                raise ValueError(
                    f"run_id={run_id!r} için koşum bulunamadı (cevapta 'id' alanı yok)."
                )
            return summary
        if not job_id:
            raise ValueError("Either job_id or run_id is required.")

        runs = await self.list_runs(job_id)
        if not runs:
            raise ValueError(f"No runs found for job_id={job_id!r}.")
        return self._select_run(runs, job_id)

    def _select_run(self, runs: list[dict[str, Any]], job_id: str) -> RunSummary:
        """Newest analyzable run: `RUNNING` is skipped, largest `id` wins."""
        analyzable = [r for r in runs if _state_of(r) in ANALYZABLE_RUN_STATES]
        if not analyzable:
            states = ", ".join(sorted({_state_of(r) or "<boş>" for r in runs})) or "<yok>"
            raise ValueError(
                f"job_id={job_id!r} için seçilebilecek bitmiş koşum yok "
                f"(görülen durumlar: {states}). Sürmekte olan bir koşumu analiz "
                f"etmek istiyorsan run_id'sini doğrudan ver."
            )

        unknown = sorted(
            {
                _state_of(r) or "<boş>"
                for r in runs
                if _state_of(r) not in ANALYZABLE_RUN_STATES
                and _state_of(r) != RunState.RUNNING.value
            }
        )
        note = f"bilinmeyen koşum durumu atlandı: {', '.join(unknown)}" if unknown else ""
        return _summary_from(max(analyzable, key=_run_order_key), job_id=job_id, note=note)

    async def fetch_job(self, run: RunSummary, plan: DownloadPlan) -> JobData:
        """Adım B-D: evidence for an already-resolved run."""
        job_log = JobLog()
        if plan.wants_build_log:
            text, error = await self.fetch_build_log(run.run_id)
            job_log = JobLog(text=text, error=error)

        results = await self.get_results(run.run_id)
        failed = [r for r in results if r.get("resultType") == RESULT_FAILED]

        semaphore = asyncio.Semaphore(self._max_parallel)

        async def one(record: dict[str, Any]) -> RawScenario:
            async with semaphore:
                return await self._build_scenario(run.run_id, record, plan)

        scenarios = list(await asyncio.gather(*(one(record) for record in failed)))

        total = run.run_result.get("totalScenarios", 0)
        return JobData(
            total_scenario_count=total,
            failed_scenarios=scenarios,
            job_log=job_log,
            raw_results_response=results,
        )

    def _extract_log(self, archive: bytes) -> str:
        """Read the configured entry out of the ZIP (matched on its ending)."""
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            names = bundle.namelist()
            wanted = next((n for n in names if n.endswith(self._build_log_entry)), "")
            if not wanted:
                raise ValueError(
                    f"ZIP has no entry ending with {self._build_log_entry!r} (entries: {names})"
                )
            return bundle.read(wanted).decode("utf-8", errors="replace")

    async def _build_scenario(
        self, run_id: str, record: dict[str, Any], plan: DownloadPlan
    ) -> RawScenario:
        """Adım C: fetch scenario detail and its attachments."""
        scenario_id = str(record.get("id", ""))
        detail: dict[str, Any] = {}
        fetch_error = ""
        if not scenario_id:
            fetch_error = f"/results satırında 'id' alanı yok: {record}"
        else:
            try:
                detail = await self.get_scenario_detail(run_id, scenario_id)
            except Exception as exc:
                fetch_error = f"{PATH_SCENARIO_DETAIL}: {type(exc).__name__}: {exc}"
        fetch_error = fetch_error[:_FETCH_ERROR_MAX_CHARS]

        attachments: list[Attachment] = []
        for meta in detail.get("attachments", []):
            described = self.describe_attachment(meta)
            if not plan.wants(described):
                attachments.append(described.model_copy(update={"download_skipped": True}))
                continue
            attachments.append(await self.download_attachment(run_id, meta, scenario_id))

        return RawScenario(
            scenario_name=str(record.get("name", "")),
            scenario_id=scenario_id,
            error_text=str(detail.get("errorText", "")),
            failed_step=_failed_step_of(detail),
            attachments=attachments,
            fetch_error=fetch_error,
            detail_fields=sorted(detail),
        )
