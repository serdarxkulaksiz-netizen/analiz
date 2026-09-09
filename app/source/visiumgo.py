"""VisiumGoSource — real VisiumGo API client.

Chain (real-spec Bölüm 2):
  A. resolve the run: `run_id` -> `GET /api/runs/{run_id}`;
     `job_id` -> `GET /api/runs?jobId=` and pick the newest analyzable run
  B. list results, keep resultType == "FAILED"
  C. per failed scenario: fetch detail (errorText, stepResults, attachments)
  D. download each attachment (URL-encoded name), save to disk for observability

Produces the same attachment-based `RawScenario` as MockSource, so the
extraction ring is unchanged (mock/real difference lives only here).

Every VisiumGo endpoint is ONE public, single-purpose method here
(`get_run`, `list_runs`, `get_results`, `get_scenario_detail`,
`download_attachment`, `fetch_build_log`); `fetch_job` only sequences them.
That split is what makes the same services usable later from something that
decides its own order, without touching this file's logic.

Save-everything rule: the raw run response, the raw /results array and each
scenario's raw detail response are kept verbatim on the models and persisted
by the service — nothing from the API is discarded.

Robustness (real-spec Bölüm 5): a failed attachment download leaves that
evidence empty but the scenario continues; the service marks a fully-failing
scenario `analysis_failed` and the job goes on.
"""

import io
import zipfile
from pathlib import Path
from typing import Any

from app.domain.enums import ANALYZABLE_RUN_STATES, RunState
from app.source.base import AttachmentFilter, Source, accept_all
from app.source.models import Attachment, JobData, RawScenario, RunSummary
from app.source.storage import save_attachment
from app.source.visiumgo_client import VisiumGoClient, encode_segment

#: Upper bound for the recorded build-log failure reason (see
#: `fetch_build_log`): keeps a long exception text or ZIP listing from
#: bloating the persisted run row.
_BUILD_LOG_ERROR_MAX_CHARS = 500


def _state_of(record: dict[str, Any]) -> str:
    """Job-level state of a run record (`runResult.state`), "" if absent."""
    return str((record.get("runResult") or {}).get("state", ""))


def _run_order_key(record: dict[str, Any]) -> tuple[int, int, str]:
    """Sort key for picking the newest run: the largest `id` wins.

    `id` IS the run id and grows with every run, so it orders runs even when
    two of them share a `startTime` (which is what the previous, time-based
    ordering could not do). Ids are numeric in VisiumGo; a non-numeric one
    still sorts (below the numeric ones, lexicographically) instead of
    crashing the whole resolution.
    """
    raw = str(record.get("id", ""))
    try:
        return (1, int(raw), "")
    except ValueError:
        return (0, 0, raw)


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
        attachments_dir: Path,
        build_log_path: str = "",
        build_log_entry: str = "build.log",
    ) -> None:
        self._client = client
        self._attachments_dir = attachments_dir
        self._build_log_path = build_log_path
        self._build_log_entry = build_log_entry

    # ------------------------------------------------------------- endpoints

    async def get_run(self, run_id: str) -> dict[str, Any]:
        """`GET /api/runs/{run_id}` — one run.

        Returns: `{id, jobId, jobName, userId, startTime, duration,
        runResult{state, totalScenarios, failScenarios, passScenarios,
        unstableScenarios}}`.
        """
        return await self._client.get_json(f"/api/runs/{encode_segment(run_id)}")

    async def list_runs(self, job_id: str) -> list[dict[str, Any]]:
        """`GET /api/runs?jobId=` — a job's runs, each in the `get_run` shape."""
        return await self._client.get_json("/api/runs", params={"jobId": job_id})

    async def get_results(self, run_id: str) -> list[dict[str, Any]]:
        """`GET /api/runs/{run_id}/results` — the run's scenarios.

        Returns rows of `{id, jobId, name, resultType, duration, runId,
        retryNumber, dateTime, featureName, feature, jobStep}`. `resultType` is
        `FAILED` | `PASSED` | `UNSTABLE`; every scenario appears once.
        """
        return await self._client.get_json(f"/api/runs/{encode_segment(run_id)}/results")

    async def get_scenario_detail(self, run_id: str, scenario_id: str) -> dict[str, Any]:
        """`GET /api/runs/{run_id}/results/{scenario_id}` — one scenario.

        Returns `{id, name, resultType, errorText, dateTime, stepResults[],
        attachments[], properties{}}`. Its `runId`/`retryNumber` are unreliable
        (observed as 0); the real values live in the results row and in
        `properties`. `stepResults` is deliberately NOT read: VisiumGo derives
        it from `test.log`, which we send whole.
        """
        return await self._client.get_json(
            f"/api/runs/{encode_segment(run_id)}/results/{encode_segment(scenario_id)}"
        )

    async def fetch_build_log(self, run_id: str) -> tuple[str, str]:
        """Job-level build log, served by VisiumGo.

        The endpoint (`/api/runs/{run_id}/logs`) returns a **ZIP archive**, not
        plain text; the wanted entry (`build.log` by default) is extracted from
        it. The archive itself is not kept — only the extracted text.

        Returns `(log, error)`. Optional: unset path = deliberate skip, both
        empty. Any failure (network, 404, not a zip, entry missing) leaves the
        log empty and the job continues — but the REASON is returned instead of
        being swallowed, so "no build log configured" and "build log could not
        be fetched" stay distinguishable (no silent loss).
        """
        if not self._build_log_path:
            return "", ""
        path = self._build_log_path.format(run_id=encode_segment(run_id))
        try:
            archive = await self._client.get_bytes(path)
            return self._extract_log(archive), ""
        except Exception as exc:
            reason = f"{path}: {type(exc).__name__}: {exc}"
            # Bounded: an exception text (or a ZIP listing) must not blow up the
            # run row. Architectural guard, not a tunable setting.
            return "", reason[:_BUILD_LOG_ERROR_MAX_CHARS]

    @staticmethod
    def describe_attachment(meta: dict[str, Any]) -> Attachment:
        """One `attachments[]` row as an Attachment — metadata only, no bytes.

        This is what the download filter judges: `deviceId`, `mimeType` and
        `fileName` all arrive with the scenario detail, so a file the profile
        does not want costs nothing at all.
        """
        return Attachment(
            file_name=str(meta.get("fileName", "")),
            mime_type=str(meta.get("mimeType", "")),
            device_id=str(meta.get("deviceId", "")),
        )

    async def download_attachment(
        self, run_id: str, meta: dict[str, Any], scenario_id: str = ""
    ) -> Attachment:
        """Adım D: download one attachment (URL-encoded) and save it to disk.

        `meta` is one `attachments[]` row: `{deviceId, mimeType, fileName,
        startTime, duration}`. A failed download returns the attachment with
        empty content — the scenario continues (real-spec Bölüm 5).
        """
        attachment = self.describe_attachment(meta)
        file_name = attachment.file_name
        mime_type = attachment.mime_type
        path = f"/api/runs/{encode_segment(run_id)}/attachments/{encode_segment(file_name)}"

        try:
            if mime_type.startswith("text/"):
                text = await self._client.get_text(path)
                stored = self._save(run_id, scenario_id, attachment, text.encode("utf-8"))
                return attachment.model_copy(update={"content": text, "stored_path": str(stored)})
            data = await self._client.get_bytes(path)
            stored = self._save(run_id, scenario_id, attachment, data)
            return attachment.model_copy(update={"stored_path": str(stored)})
        except Exception:
            return attachment

    # ----------------------------------------------------------- orchestration

    async def resolve_run(self, job_id: str, run_id: str = "") -> RunSummary:
        """Adım A: which run to analyze (see `Source.resolve_run`)."""
        if run_id:
            record = await self.get_run(run_id)
            summary = _summary_from(record or {}, job_id=job_id)
            # A run detail with no id at all means we asked for a run that is
            # not there; keep the requested id rather than returning an empty one.
            return summary if summary.run_id else summary.model_copy(update={"run_id": run_id})
        if not job_id:
            raise ValueError("Either job_id or run_id is required.")

        runs = await self.list_runs(job_id)
        if not runs:
            raise ValueError(f"No runs found for job_id={job_id!r}.")
        return self._select_run(runs, job_id)

    def _select_run(self, runs: list[dict[str, Any]], job_id: str) -> RunSummary:
        """Newest analyzable run: `RUNNING` is skipped, largest `id` wins.

        A run in an unknown state is skipped too — but the skip is reported on
        the summary, because a state VisiumGo adds later must not quietly
        remove runs from the analysis.
        """
        analyzable = [r for r in runs if _state_of(r) in ANALYZABLE_RUN_STATES]
        if not analyzable:
            states = ", ".join(sorted({_state_of(r) or "<boş>" for r in runs})) or "<yok>"
            raise ValueError(
                f"job_id={job_id!r} için analiz edilebilir koşum yok "
                f"(görülen durumlar: {states}; RUNNING koşumlar analiz edilmez)."
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

    async def fetch_job(self, run: RunSummary, wants: AttachmentFilter = accept_all) -> JobData:
        """Adım B-D: evidence for an already-resolved run."""
        build_log, build_log_error = await self.fetch_build_log(run.run_id)

        results = await self.get_results(run.run_id)
        failed = [r for r in results if r.get("resultType") == "FAILED"]

        scenarios: list[RawScenario] = []
        for record in failed:
            scenarios.append(await self._build_scenario(run.run_id, record, wants))

        total = run.run_result.get("totalScenarios", len(results))
        return JobData(
            job_id=run.job_id,
            run_id=run.run_id,
            job_name=run.job_name,
            run_result=run.run_result,
            total_scenario_count=total,
            failed_scenarios=scenarios,
            build_log=build_log,
            build_log_error=build_log_error,
            raw_run_response=run.raw,
            raw_results_response=results,
        )

    def _extract_log(self, archive: bytes) -> str:
        """Read the configured entry out of the ZIP (matched on its ending).

        Raises when the archive holds no matching entry, so the caller can
        report *why* the log is missing (the exception never reaches the job).
        """
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            names = bundle.namelist()
            wanted = next((n for n in names if n.endswith(self._build_log_entry)), "")
            if not wanted:
                raise ValueError(
                    f"ZIP has no entry ending with {self._build_log_entry!r} (entries: {names})"
                )
            return bundle.read(wanted).decode("utf-8", errors="replace")

    async def _build_scenario(
        self, run_id: str, record: dict[str, Any], wants: AttachmentFilter = accept_all
    ) -> RawScenario:
        """Adım C: fetch scenario detail and its attachments."""
        scenario_id = str(record.get("id", ""))
        detail = await self.get_scenario_detail(run_id, scenario_id)

        attachments: list[Attachment] = []
        for meta in detail.get("attachments", []):
            described = self.describe_attachment(meta)
            if not wants(described):
                # Not wanted by this profile: no request, no bytes, no file —
                # but the row stays, flagged, so the gap is explained later.
                attachments.append(described.model_copy(update={"download_skipped": True}))
                continue
            attachments.append(await self.download_attachment(run_id, meta, scenario_id))

        return RawScenario(
            scenario_name=str(record.get("name", "")),
            scenario_id=scenario_id,
            error_text=str(detail.get("errorText", "")),
            attachments=attachments,
            retry_info=str(record.get("retryNumber", "")),
            raw_detail=detail,  # full raw response, persisted (save everything)
        )

    def _save(self, run_id: str, scenario_id: str, attachment: Attachment, data: bytes) -> Path:
        """Write one attachment under the shared naming rule (see `storage`)."""
        return save_attachment(self._attachments_dir, run_id, scenario_id, attachment, data)
