"""One-command check: does a real run's evidence actually arrive?

    python -m tools.inspect_run --run-id 148918
    python -m tools.inspect_run --job-id 886
    python -m tools.inspect_run                 # uses the DEFAULT_* constants below

Runs the REAL chain against the configured source — resolve the run, download
every attachment, map each one to an Evidence class, build the prompt — then
prints what arrived, what did not, and how big the prompt got.

Two guarantees, both deliberate:

  * **The LLM is never called.** The service is built with the mock provider no
    matter what `.env` says, and there is no flag to change that. This is a
    plumbing check, not an analysis: it must never occupy the on-prem model.
  * **The `test_all` profile is forced**, so every attachment is fetched. That
    is the point of the tool: "is everything downloadable?", not "what would
    this job's own profile keep?".

Exit code 1 when something is actually wrong — a file no Evidence class claims,
or one that was downloaded but is not on disk — so this is a check, not just a
report. Development tool: `app/` never imports it.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.extraction.evidence_extractor import BUILD_LOG_DEVICE_ID
from app.main import build_service
from app.persistence.file_repository import FileRepository

#: Fill these in on the work PC so the tool runs with no arguments at all.
DEFAULT_RUN_ID = ""
DEFAULT_JOB_ID = ""

#: The profile this tool always uses — it must fetch everything.
INSPECT_PROFILE = "test_all"

_OK = "OK"
_MISSING = "EKSİK"
_SKIPPED = "ATLANDI"
_UNMATCHED = "EŞLEŞMEDİ"
_JOB_LEVEL = "JOB LOGU"
_LINE = "=" * 78


def _settings_without_llm() -> Settings:
    """Real source, fake LLM. The mock provider cannot reach the network."""
    return get_settings().model_copy(update={"llm_provider": "mock"})


def _print_run(run: dict[str, Any]) -> None:
    result = run.get("run_result") or {}
    print(_LINE)
    print(f"KOŞUM   run_id={run.get('run_id')}   job={run.get('job_name') or '-'}")
    print(
        f"        state={result.get('state') or '-'}   "
        f"toplam senaryo={run.get('total_scenario_count')}   "
        f"başarısız={run.get('scenario_count')}"
    )
    if run.get("build_log_error"):
        print(f"        build log ALINAMADI: {run['build_log_error']}")
    else:
        print(f"        build log: {len(run.get('build_log') or '')} karakter")
    if run.get("note"):
        print(f"        not: {run['note']}")


def _attachment_status(row: dict[str, Any], stored_path: str) -> str:
    """One attachment's verdict: downloaded and on disk, or why not."""
    if row.get("device_id") == BUILD_LOG_DEVICE_ID:
        # Not a per-scenario file at all: the build log is job-level and lives
        # on the run row. It has no path of its own and never will.
        return _JOB_LEVEL
    if row.get("download_skipped"):
        return _SKIPPED  # profile did not want it (not possible under test_all)
    if not row.get("evidence_name"):
        return _UNMATCHED  # VisiumGo sent a file no Evidence class claims
    return _OK if stored_path and Path(stored_path).is_file() else _MISSING


def _print_scenario(evidence_row: dict[str, Any], prompt_chars: int) -> int:
    """Print one scenario's evidence table; return how many problems it had."""
    report = evidence_row.get("evidence_report") or {}
    stored = {
        str(a.get("file_name", "")): str(a.get("stored_path", ""))
        for a in (evidence_row.get("raw_scenario") or {}).get("attachments", [])
    }

    print("-" * 78)
    print(f"SENARYO {evidence_row.get('scenario_name')}")

    problems = 0
    attachments = report.get("attachments") or []
    if not attachments:
        print("  (bu senaryoda hiç ek yok — tek kanıt build log olabilir)")
    for row in attachments:
        name = str(row.get("file_name", ""))
        status = _attachment_status(row, stored.get(name, ""))
        if status in (_MISSING, _UNMATCHED):
            problems += 1
        print(
            f"  [{status:9}] {name:52} "
            f"{row.get('evidence_name') or '-':24} {row.get('chars', 0):>8} krk"
        )

    for block in report.get("blocks") or []:
        cut = " (kural kesti)" if block.get("trimmed") else ""
        print(f"  BLOK       {block.get('label'):52} {block.get('chars', 0):>8} krk{cut}")

    print(f"  PROMPT     {prompt_chars} karakter")
    return problems


def inspect(run_id: str, job_id: str) -> int:
    settings = _settings_without_llm()
    service = build_service(settings)
    repo = FileRepository(settings.database_dir)

    analyzer_run_id = service.create_run("default", job_id, "default", run_id)
    asyncio.run(service.run_analysis(analyzer_run_id, profile_override=INSPECT_PROFILE))

    run = service.get_run(analyzer_run_id)
    if run is None:
        print("HATA: koşum satırı yazılamadı.")
        return 1

    _print_run(run)
    if run.get("status") == "failed":
        print(f"\nKOŞUM BAŞARISIZ: {run.get('note')}")
        return 1

    prompt_chars = {
        row.get("result_id"): row.get("prompt_chars", 0)
        for row in repo.list(settings.table_prompts)
        if row.get("analyzer_run_id") == analyzer_run_id
    }
    rows = [
        row
        for row in repo.list(settings.table_evidence)
        if row.get("analyzer_run_id") == analyzer_run_id
    ]

    problems = sum(
        _print_scenario(row, prompt_chars.get(row.get("result_id"), 0))
        for row in sorted(rows, key=lambda r: str(r.get("scenario_name", "")))
    )

    print(_LINE)
    if problems:
        print(f"SONUÇ: {problems} sorun (yukarıdaki {_MISSING} / {_UNMATCHED} satırları).")
        return 1
    print(f"SONUÇ: her şey yerinde. Ham iz: {settings.database_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="VisiumGo koşumunun kanıtlarını denetler.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID, help="VisiumGo koşum id'si")
    parser.add_argument("--job-id", default=DEFAULT_JOB_ID, help="VisiumGo job id'si")
    args = parser.parse_args()

    if not args.run_id and not args.job_id:
        parser.error(
            "--run-id ya da --job-id verin (ya da tools/inspect_run.py başındaki "
            "DEFAULT_RUN_ID / DEFAULT_JOB_ID sabitlerini doldurun)."
        )
    return inspect(args.run_id, args.job_id)


if __name__ == "__main__":
    sys.exit(main())
