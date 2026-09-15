"""VisiumGoSource — real VisiumGo API client.

Chain:
  A. resolve the run: `run_id` -> `GET /api/runs/{run_id}` (that run, whatever
     its state); `job_id` -> `GET /api/runs?jobId=` and pick the newest
     FINISHED run
  B. list results, keep resultType == "FAILED"
  C. per failed scenario: fetch detail (errorText, stepResults, attachments)
  D. download each attachment (URL-encoded name), save to disk for observability

Produces the attachment-based `RawScenario` the extraction ring consumes, so
VisiumGo's response shape stops at this file.

Every VisiumGo endpoint is ONE public, single-purpose method here
(`get_run`, `list_runs`, `get_results`, `get_scenario_detail`,
`download_attachment`, `fetch_build_log`); `fetch_job` only sequences them.
That split is what makes the same services usable later from something that
decides its own order, without touching this file's logic.

Save-everything rule: the raw run response, the raw /results array and each
scenario's raw detail response are kept verbatim on the models and persisted
by the service — nothing from the API is discarded.

Robustness: a failed attachment download leaves that
evidence empty but the scenario continues; the service marks a fully-failing
scenario `analysis_failed` and the job goes on.
"""

import io
import zipfile
from pathlib import Path
from typing import Any

from app.domain.enums import ANALYZABLE_RUN_STATES, RunState
from app.source.base import DownloadPlan, Source
from app.source.models import Attachment, JobData, RawScenario, RunSummary
from app.source.storage import save_attachment, save_build_log
from app.source.visiumgo_client import VisiumGoClient, encode_segment

#: Upper bound for the recorded build-log failure reason (see
#: `fetch_build_log`): keeps a long exception text or ZIP listing from
#: bloating the persisted run row.
_BUILD_LOG_ERROR_MAX_CHARS = 500

#: The run's log archive. A path, like every other endpoint here — not a
#: setting. It used to live in `.env`, which meant an unset key silently turned
#: the whole step off and recorded no reason: "this job has no build log" and
#: "nobody filled in the config" looked identical. Whether the log is fetched
#: is now a PROFILE decision (`BuildLogEvidence`), which is where it belongs.
PATH_LOGS = "/api/runs/{run_id}/logs"

#: Named in a scenario's `fetch_error`, so the reason says which call failed.
PATH_SCENARIO_DETAIL = "/api/runs/{run_id}/results/{scenario_id}"

#: Upper bound for a recorded scenario-detail failure reason (same rule as the
#: build log's): a long exception text must not bloat the stored row.
_FETCH_ERROR_MAX_CHARS = 500

#: Extensions whose content is text and therefore belongs inline on the
#: attachment, whatever mime type VisiumGo labels them with. The mime type
#: alone is not a safe test: it is the SECOND half of an attachment's identity
#: precisely because it is unreliable (`test.log` and `test.properties` share
#: `text/plain`), and an `.xml` served as `application/xml` would be read as
#: binary — the file lands on disk, `content` stays empty, and the evidence
#: silently produces no block. These four are exactly the extensions the text
#: evidences are built on.
_TEXT_EXTENSIONS = frozenset({".log", ".properties", ".html", ".xml"})


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
        build_logs_dir: Path | None = None,
        build_log_entry: str = "build.log",
    ) -> None:
        self._client = client
        self._attachments_dir = attachments_dir
        #: Where a fetched build log is written. None = keep it in memory only.
        self._build_logs_dir = build_logs_dir
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

        Returns `(log, error)`. Any failure (network, 404, not a zip, entry
        missing) leaves the log empty and the job continues — but the REASON is
        returned instead of being swallowed, so a broken endpoint can never
        pass for "this job simply has no build log".
        """
        path = PATH_LOGS.format(run_id=encode_segment(run_id))
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
        empty content AND the reason on `download_error` — the scenario
        continues, but the gap is never silent.
        """
        attachment = self.describe_attachment(meta)
        file_name = attachment.file_name
        path = f"/api/runs/{encode_segment(run_id)}/attachments/{encode_segment(file_name)}"
        is_text = (
            attachment.mime_type.startswith("text/") or attachment.extension in _TEXT_EXTENSIONS
        )

        try:
            if is_text:
                text = await self._client.get_text(path)
                stored = self._save(run_id, scenario_id, attachment, text.encode("utf-8"))
                return attachment.model_copy(update={"content": text, "stored_path": str(stored)})
            data = await self._client.get_bytes(path)
            stored = self._save(run_id, scenario_id, attachment, data)
            return attachment.model_copy(update={"stored_path": str(stored)})
        except Exception as exc:
            reason = f"{path}: {type(exc).__name__}: {exc}"
            return attachment.model_copy(update={"download_error": reason[:_FETCH_ERROR_MAX_CHARS]})

    # ----------------------------------------------------------- orchestration

    async def resolve_run(self, job_id: str, run_id: str = "") -> RunSummary:
        """Adım A: which run to analyze (see `Source.resolve_run`)."""
        if run_id:
            record = await self.get_run(run_id)
            summary = _summary_from(record or {}, job_id=job_id)
            if not summary.run_id:
                # The response carries no `id`, so VisiumGo did not confirm this
                # run. Filling the requested id back in would put a run id in the
                # record that the API never returned — analysis would then run
                # against a run nobody can prove exists.
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
        """Newest analyzable run: `RUNNING` is skipped, largest `id` wins.

        A run in an unknown state is skipped too — but the skip is reported on
        the summary, because a state VisiumGo adds later must not quietly
        remove runs from the analysis.
        """
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
        # Not fetched unless the active profile asked for it: a ZIP download
        # nobody uses is bytes paid for nothing. `want_build_log=False` means
        # "not wanted", never "could not be fetched" — the two are told apart
        # by `evidence_report.job_log.wanted`.
        build_log, build_log_error, build_log_path = "", "", ""
        if plan.wants_build_log:
            build_log, build_log_error = await self.fetch_build_log(run.run_id)
            if build_log and self._build_logs_dir is not None:
                build_log_path = str(save_build_log(self._build_logs_dir, run.run_id, build_log))

        results = await self.get_results(run.run_id)
        failed = [r for r in results if r.get("resultType") == "FAILED"]

        scenarios: list[RawScenario] = []
        for record in failed:
            scenarios.append(await self._build_scenario(run.run_id, record, plan))

        # Only what VisiumGo reported. This used to fall back to our own count
        # of `/results` rows, which put two different numbers in one field with
        # no way to tell which one you were reading. Absent -> 0, and the
        # service records that in the run note; `run_result` is stored raw.
        total = run.run_result.get("totalScenarios", 0)
        return JobData(
            total_scenario_count=total,
            failed_scenarios=scenarios,
            build_log=build_log,
            build_log_path=build_log_path,
            build_log_error=build_log_error,
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
        self, run_id: str, record: dict[str, Any], plan: DownloadPlan
    ) -> RawScenario:
        """Adım C: fetch scenario detail and its attachments.

        A detail call that cannot be made, or that fails, does NOT raise: the
        reason is carried on the scenario and the run goes on. It used to
        propagate out of `fetch_job`, so one malformed `/results` row (or one
        404) ended the whole run as `failed` — with every healthy scenario in
        it never analyzed.
        """
        scenario_id = str(record.get("id", ""))
        detail: dict[str, Any] = {}
        fetch_error = ""
        if not scenario_id:
            # No id, no detail endpoint to call: asking for `/results/` with an
            # empty segment would 404 for a reason that has nothing to do with
            # this run.
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
            fetch_error=fetch_error,
        )

    def _save(self, run_id: str, scenario_id: str, attachment: Attachment, data: bytes) -> Path:
        """Write one attachment under the shared naming rule (see `storage`)."""
        return save_attachment(self._attachments_dir, run_id, scenario_id, attachment, data)
