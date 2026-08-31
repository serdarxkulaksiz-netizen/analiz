"""VisiumGoSource — real VisiumGo API client (plan.md Halka 1, real-spec §2-5).

Chain (real-spec Bölüm 2):
  A. resolve run_id (run_id wins; else newest run for job_id by startTime)
  B. list results, keep resultType == "FAILED"
  C. per failed scenario: fetch detail (errorText, stepResults, attachments)
  D. download each attachment (URL-encoded name), save to disk for observability

Produces the same attachment-based `RawScenario` as MockSource, so the
extraction ring is unchanged (mock/real difference lives only here).

Save-everything rule: the raw run response, the raw /results array and each
scenario's raw detail response are kept verbatim on the models and persisted
by the service — nothing from the API is discarded.

Robustness (real-spec Bölüm 5): a failed attachment download leaves that
evidence empty but the scenario continues; the service marks a fully-failing
scenario `analysis_failed` and the job goes on.
"""

from pathlib import Path
from typing import Any

from app.domain.enums import StepStatus
from app.domain.findings import Step
from app.source.base import Source
from app.source.models import Attachment, JobData, RawScenario
from app.source.visiumgo_client import VisiumGoClient, encode_segment


def _safe_path_part(value: str) -> str:
    """Make an id/file name safe to use as a filesystem path segment."""
    return value.replace("/", "_").replace(":", "_").replace("\\", "_")


def _to_step_status(result_type: str) -> StepStatus | None:
    try:
        return StepStatus(result_type)
    except ValueError:
        return None


class VisiumGoSource(Source):
    """Fetches real job evidence from a VisiumGo instance."""

    def __init__(
        self,
        client: VisiumGoClient,
        attachments_dir: Path,
        jenkins_log_path: str = "",
    ) -> None:
        self._client = client
        self._attachments_dir = attachments_dir
        self._jenkins_log_path = jenkins_log_path

    async def resolve_run_id(self, job_id: str, run_id: str = "") -> str:
        """Which run to analyze — no evidence fetched (see Source docstring)."""
        resolved, _ = await self._resolve_run(job_id, run_id)
        return resolved

    async def fetch_job(self, job_id: str, run_id: str = "") -> JobData:
        resolved_run_id, raw_run = await self._resolve_run(job_id, run_id)

        results = await self._client.get_json(
            f"/api/runs/{encode_segment(resolved_run_id)}/results"
        )
        failed = [r for r in results if r.get("resultType") == "FAILED"]

        scenarios: list[RawScenario] = []
        for record in failed:
            scenarios.append(await self._build_scenario(resolved_run_id, record))

        run_result = (raw_run.get("runResult") or {}) if raw_run else {}
        total = run_result.get("totalScenarios", len(results))
        return JobData(
            job_id=job_id,
            run_id=resolved_run_id,
            job_name=(raw_run.get("jobName", "") if raw_run else ""),
            run_result=run_result,
            total_scenario_count=total,
            failed_scenarios=scenarios,
            jenkins_console_log=await self._fetch_jenkins_log(resolved_run_id),
            raw_run_response=raw_run or {},
            raw_results_response=results,
        )

    async def _fetch_jenkins_log(self, run_id: str) -> str:
        """Job-level Jenkins console log, served by VisiumGo (plan.md A4.1).

        Optional: unset path = skip; a failure leaves it empty and the job
        continues (the analysis simply has one evidence less).
        """
        if not self._jenkins_log_path:
            return ""
        path = self._jenkins_log_path.format(run_id=encode_segment(run_id))
        try:
            return await self._client.get_text(path)
        except Exception:
            return ""

    async def _resolve_run(
        self, job_id: str, run_id: str
    ) -> tuple[str, dict[str, Any]]:
        """Adım A: run_id wins; else newest run for job_id by startTime."""
        if run_id:
            return run_id, {}
        if not job_id:
            raise ValueError("Either job_id or run_id is required.")
        runs = await self._client.get_json("/api/runs", params={"jobId": job_id})
        if not runs:
            raise ValueError(f"No runs found for job_id={job_id!r}.")
        # startTime is an ISO 8601 string (e.g. "2026-07-27T10:20:08.623449"),
        # which sorts chronologically as text.
        latest = max(runs, key=lambda r: r.get("startTime", ""))
        resolved = latest.get("id")
        if not resolved:
            raise ValueError(f"Run record for job_id={job_id!r} has no id.")
        return str(resolved), latest

    async def _build_scenario(
        self, run_id: str, record: dict[str, Any]
    ) -> RawScenario:
        """Adım C: fetch scenario detail and its attachments."""
        scenario_id = str(record.get("id", ""))
        detail = await self._client.get_json(
            f"/api/runs/{encode_segment(run_id)}/results/{encode_segment(scenario_id)}"
        )

        steps: list[Step] = []
        for step in detail.get("stepResults", []):
            status = _to_step_status(step.get("resultType", ""))
            if status is None:
                continue
            # `line` is the human-readable step text ("butonDevam2 öğesini
            # görürüm"); `stepLine` is only a line number — do not use it here.
            name = step.get("line") or step.get("stepType") or ""
            steps.append(Step(name=str(name), status=status))

        attachments: list[Attachment] = []
        for meta in detail.get("attachments", []):
            attachments.append(await self._download_attachment(run_id, meta))

        return RawScenario(
            scenario_name=str(record.get("name", "")),
            scenario_id=scenario_id,
            error_text=str(detail.get("errorText", "")),
            steps=steps,
            attachments=attachments,
            retry_info=str(record.get("retryNumber", "")),
            raw_detail=detail,  # full raw response, persisted (save everything)
        )

    async def _download_attachment(
        self, run_id: str, meta: dict[str, Any]
    ) -> Attachment:
        """Adım D: download one attachment (URL-encoded) and save it to disk."""
        file_name = str(meta.get("fileName", ""))
        mime_type = str(meta.get("mimeType", ""))
        device_id = str(meta.get("deviceId", ""))
        path = f"/api/runs/{encode_segment(run_id)}/attachments/{encode_segment(file_name)}"

        try:
            if mime_type.startswith("text/"):
                text = await self._client.get_text(path)
                stored = self._save(run_id, file_name, text.encode("utf-8"))
                return Attachment(
                    file_name=file_name,
                    mime_type=mime_type,
                    device_id=device_id,
                    content=text,
                    stored_path=str(stored),
                )
            data = await self._client.get_bytes(path)
            stored = self._save(run_id, file_name, data)
            return Attachment(
                file_name=file_name,
                mime_type=mime_type,
                device_id=device_id,
                stored_path=str(stored),
            )
        except Exception:
            # A failed download leaves this evidence empty — the scenario
            # continues (real-spec Bölüm 5).
            return Attachment(
                file_name=file_name, mime_type=mime_type, device_id=device_id
            )

    def _save(self, run_id: str, file_name: str, data: bytes) -> Path:
        dest = self._attachments_dir / _safe_path_part(run_id) / _safe_path_part(file_name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest
