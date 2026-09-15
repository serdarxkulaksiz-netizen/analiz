"""The whole chain on a fake wire: HTTP in, diagnosis rows out.

Every ring runs for real — `VisiumGoSource`, the profile registry, extraction,
the prompt builder, `OpenAICompatibleLLMProvider`, parsing, persistence. Only
the two network boundaries are faked, and they are faked at the LOWEST possible
level: an `httpx` transport. Nothing here substitutes a class the product uses,
so a bug in that class fails this test instead of hiding behind a stand-in.

It exists because the unit tests below it cannot see the decisions the service
makes ABOUT them — which run is analyzed, whether the LLM is called at all,
what ends up on the run row.
"""

import asyncio
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.domain.api import build_run_view
from app.evidence.profiles import ProfileRegistry
from app.evidence.registry import EvidenceRegistry
from app.extraction.evidence_extractor import EvidenceExtractor
from app.llm.openai_compatible import OpenAICompatibleLLMProvider
from app.persistence.file_repository import FileRepository
from app.precheck.noop import NoOpPreCheck
from app.prompting.builder import PromptBuilder
from app.service import AnalyzerService
from app.source.visiumgo import VisiumGoSource
from app.source.visiumgo_client import VisiumGoClient

_SCENARIO_ID = "1:Bireysel/DovizAlis.feature:250_1278616082:0"

_RESULTS = [
    {"id": "sc:pass", "name": "geçen senaryo", "resultType": "PASSED"},
    {"id": _SCENARIO_ID, "name": "Döviz alış başarısız", "resultType": "FAILED"},
]

_DETAIL = {
    "id": _SCENARIO_ID,
    "name": "Döviz alış başarısız",
    "errorText": "AssertionError: beklenen tutar bulunamadı",
    "attachments": [
        {"fileName": "-125/test_1.log", "mimeType": "text/plain", "deviceId": "test"},
        {
            "fileName": "-125/browser.default_1.html",
            "mimeType": "text/html",
            "deviceId": "browser.default",
        },
    ],
}

#: A schema-valid answer. `verdict` and `confidence` are the two the parser
#: refuses to do without.
_DIAGNOSIS = {
    "scenario_name": "Döviz alış başarısız",
    "root_cause": "Locator değişmiş",
    "error_type": "NoSuchElementException",
    "verdict": "test_maintenance",
    "explanation": "Buton id'si güncellenmiş.",
    "suggestion": "Locator'ı güncelleyin.",
    "confidence": 0.75,
    "confidence_reason": "Log ve DOM aynı yöne işaret ediyor.",
    "summary": "Locator bakımı gerekiyor.",
    "most_relevant_log_lines": ["ERROR #tutar bulunamadı"],
    "error_signature": "no-such-element",
}


def _run_record(run_id: int, state: str, job_id: int = 999) -> dict[str, Any]:
    return {
        "id": run_id,
        "jobId": job_id,
        "jobName": "nightly",
        "runResult": {"state": state, "totalScenarios": 100, "failScenarios": 1},
    }


def _zip_bytes(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, content in entries.items():
            bundle.writestr(name, content)
    return buffer.getvalue()


def _visiumgo_transport(
    state: str, calls: list[str], *, job_id: int = 999, build_log: str = "BUILD ok"
) -> httpx.MockTransport:
    """Serves the five VisiumGo endpoints the chain walks, in one place."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(path)
        if path.endswith("/logs"):
            return httpx.Response(200, content=_zip_bytes({"build.log": build_log}))
        if "/attachments/" in path:
            if path.endswith(".html"):
                return httpx.Response(200, text="<html><body>tutar yok</body></html>")
            return httpx.Response(200, text="STEP tutarı doğrula | FAILED")
        if "/results/" in path:
            return httpx.Response(200, json=_DETAIL)
        if path.endswith("/results"):
            return httpx.Response(200, json=_RESULTS)
        if path == "/api/runs":
            return httpx.Response(200, json=[_run_record(149132, state, job_id)])
        if path.startswith("/api/runs/"):
            return httpx.Response(200, json=_run_record(int(path.rsplit("/", 1)[1]), state, job_id))
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _llm_transport(prompts: list[str]) -> httpx.MockTransport:
    """Records the prompt it was asked with, answers with a valid diagnosis."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompts.append(body["messages"][0]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(_DIAGNOSIS)}}],
                "model": "qwen3-coder-next",
                "usage": {"prompt_tokens": 120, "completion_tokens": 40},
            },
        )

    return httpx.MockTransport(handler)


def _service(
    settings: Settings,
    state: str,
    calls: list[str],
    prompts: list[str],
    *,
    job_id: int = 999,
    build_log: str = "BUILD ok",
) -> AnalyzerService:
    profiles = ProfileRegistry(settings.profiles_config_path)
    client = VisiumGoClient(
        settings.visiumgo_base_url,
        settings.visiumgo_token,
        settings.visiumgo_timeout_seconds,
        transport=_visiumgo_transport(state, calls, job_id=job_id, build_log=build_log),
    )
    return AnalyzerService(
        settings=settings,
        repository=FileRepository(settings.database_dir),
        source=VisiumGoSource(
            client,
            settings.database_dir / "attachments",
            settings.database_dir / "build_logs",
        ),
        extractor=EvidenceExtractor(EvidenceRegistry()),
        prompt_builder=PromptBuilder(settings.prompts_dir, settings.confidence_buckets),
        llm_provider=OpenAICompatibleLLMProvider(
            base_url=settings.llm_base_url,
            endpoint_path=settings.llm_endpoint_path,
            api_key="",
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            timeout_seconds=settings.llm_timeout_seconds,
            max_tokens=settings.llm_max_tokens,
            transport=_llm_transport(prompts),
        ),
        precheck=NoOpPreCheck(),
        profiles=profiles,
    )


def _analyze(
    settings: Settings,
    *,
    job_id: str = "",
    run_id: str = "",
    state: str = "PASSED",
    build_log: str = "BUILD ok",
):
    calls: list[str] = []
    prompts: list[str] = []
    service = _service(
        settings,
        state,
        calls,
        prompts,
        job_id=int(job_id) if job_id else 999,
        build_log=build_log,
    )
    analyzer_run_id = service.create_run("", job_id, "", run_id)
    asyncio.run(service.run_analysis(analyzer_run_id))
    run = service.get_run(analyzer_run_id)
    assert run is not None
    return run, calls, prompts


def test_job_id_walks_the_whole_chain(settings: Settings) -> None:
    """One POST, and every ring did its job — proven from the stored rows."""
    run, calls, prompts = _analyze(settings, job_id="999")

    assert run["status"] == "done"
    assert run["scenario_count"] == 1  # only the FAILED scenario
    assert run["completed_count"] == 1
    assert run["total_scenario_count"] == 100  # what VisiumGo reported

    # The run was chosen from the job's run list, not asked for by id.
    assert "/api/runs" in calls

    # `default_web` sends test.log and the DOM, and nothing else.
    (prompt,) = prompts
    assert "=== test.log · " in prompt
    assert "=== browser.default.html · " in prompt
    assert "=== build.log · " not in prompt  # stored, not prompted

    (diagnosis,) = run["results"]
    assert diagnosis["verdict"] == "test_maintenance"
    assert diagnosis["profile_name"] == "default_web"
    assert diagnosis["status"] == "ok"
    assert diagnosis["meta"]["answered_by"] == "llm"
    assert diagnosis["meta"]["llm_model"] == "qwen3-coder-next"

    # The build log was fetched (the profile stores it) and written as a file.
    assert Path(run["build_log_path"]).read_text(encoding="utf-8") == "BUILD ok"
    # And the downloaded attachments really landed on disk.
    stored = list((settings.database_dir / "attachments").rglob("*"))
    assert {p.name for p in stored if p.is_file()} == {"test.log", "browser.default.html"}


def test_a_named_run_is_analyzed_even_while_it_is_still_running(settings: Settings) -> None:
    """The service must not veto a run the caller named.

    `resolve_run` returning a RUNNING run is only half the guarantee; the other
    half is that the service then ANALYZES it. That half is code that is no
    longer there, which is exactly the kind of thing that comes back silently.
    """
    run, calls, prompts = _analyze(settings, run_id="149140", state="RUNNING")

    assert run["status"] == "done"  # not `failed`
    assert run["run_id"] == "149140"
    assert len(prompts) == 1  # the LLM really was asked
    (diagnosis,) = run["results"]
    assert diagnosis["verdict"] == "test_maintenance"

    # The run list was never queried: the caller named the run.
    assert "/api/runs" not in calls
    # ...and the row says the evidence may be incomplete.
    assert "RUNNING" in run["note"] and "eksik olabilir" in run["note"]


def test_build_log_job_slices_the_log_per_scenario(settings: Settings) -> None:
    """886 is a build-log job: no per-scenario files, one job log, sliced."""
    log = (
        "[gradle] derleme\n"
        "beforeScenario:63 - [1]  > Scenario [Döviz alış başarısız] started\n"
        "  adım 2 FAILED: #tutar bulunamadı\n"
        "beforeScenario:63 - [2]  > Scenario [baska] started\n"
        "  baska satır\n"
    )
    run, calls, prompts = _analyze(settings, job_id="886", build_log=log)

    assert run["status"] == "done"
    assert run["results"][0]["profile_name"] == "finart_regresyon"

    # The profile wants no attachments, so none were requested.
    assert not [c for c in calls if "/attachments/" in c]
    # The log was fetched ONCE for the run, not once per scenario.
    assert len([c for c in calls if c.endswith("/logs")]) == 1

    (prompt,) = prompts
    assert "#tutar bulunamadı" in prompt  # this scenario's section
    assert "baska satır" not in prompt  # and not the next one's


def test_a_log_the_rule_cannot_slice_fails_the_scenario_with_its_reason(
    settings: Settings,
) -> None:
    """The instruction was "this scenario's section", and it could not be met.

    Sending the untrimmed log instead is the opposite of that instruction,
    repeated once per scenario. So the LLM is never asked, the row says
    `analysis_failed`, and the reason travels all the way to the API — the
    caller cannot open `database/` and should not have to.
    """
    run, calls, prompts = _analyze(settings, job_id="886", build_log="bambaska bir format\n")

    assert run["status"] == "done"  # the run itself finished
    assert prompts == []  # nothing was sent to the model

    (diagnosis,) = run["results"]
    assert diagnosis["status"] == "analysis_failed"
    assert diagnosis["verdict"] is None  # no fabricated answer
    assert "keep_scenario_section" in diagnosis["failure_reason"]
    assert "> Scenario [Döviz alış başarısız] started" in diagnosis["failure_reason"]

    # And the API view carries it too, not just the stored row.
    view = build_run_view(run)
    assert "keep_scenario_section" in view.results[0].failure_reason
