"""End-to-end smoke test with mocks (plan.md B4 definition of done).

POST /analyze/visiumgo -> background analysis -> full trace under database/
-> GET /analyze/visiumgo/{id} returns the diagnoses. TestClient executes
BackgroundTasks before returning the response, so no polling loop is needed.
"""

import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def test_end_to_end_with_mocks(settings: Settings) -> None:
    client = _client(settings)

    # Parameters omitted -> default/default.
    response = client.post("/analyze/visiumgo", json={"job_id": "job-42"})
    assert response.status_code == 200
    body = response.json()
    analyzer_run_id = body["analyzer_run_id"]
    assert body["status"] == "pending"

    result = client.get(f"/analyze/visiumgo/{analyzer_run_id}").json()
    assert result["status"] == "done"
    assert result["parameter1"] == "default"
    assert result["parameter2"] == "default"
    assert result["scenario_count"] == 2
    assert result["completed_count"] == 2
    assert result["total_scenario_count"] == 100
    # Job-level raw traces are persisted (save-everything rule).
    assert result["raw_run_response"]["jobName"] == "MOCK_nightly-test"
    assert len(result["raw_results_response"]) == 2

    names = {row["scenario_name"] for row in result["results"]}
    assert names == {
        "MOCK_Login - geçerli kullanıcı ile giriş",
        "MOCK_Hesap özeti - hareket listesi görüntüleme",
    }
    for row in result["results"]:
        assert row["status"] == "ok"
        assert row["verdict"] == "test_maintenance"  # single mock diagnosis
        assert row["confidence"] in {0.1, 0.25, 0.5, 0.75, 0.99}
        assert row["explanation"].startswith("MOCK_")  # mock-labeled content
        assert row["parameter1"] == "default"
        assert row["parameter2"] == "default"
        assert row["profile_name"] == "default"  # which profile actually ran
        assert row["screenshot_paths"] and all(
            p.startswith("MOCK_") for p in row["screenshot_paths"]
        )
        # raw_llm_response is the FULL envelope (not just content).
        assert '"choices"' in row["raw_llm_response"]
        assert row["meta"]["llm_model"] == f"MOCK_{settings.llm_model}"

    # Full trace on disk (plan.md A12): one row per table per scenario + run row.
    db = settings.database_dir
    assert len(list((db / settings.table_runs).glob("*.json"))) == 1
    assert len(list((db / settings.table_evidence).glob("*.json"))) == 2
    assert len(list((db / settings.table_prompts).glob("*.json"))) == 2
    assert len(list((db / settings.table_analysis_results).glob("*.json"))) == 2
    assert len(list((db / settings.table_llm_responses).glob("*.json"))) == 2

    # evidence row keeps the scenario's full raw detail (save-everything rule).
    evidence_row = json.loads(
        next((db / settings.table_evidence).glob("*.json")).read_text("utf-8")
    )
    assert evidence_row["raw_scenario"]["raw_detail"]

    # prompts row = OUTGOING side only (prompt + request), no response copy.
    prompt_row = json.loads(
        next((db / settings.table_prompts).glob("*.json")).read_text("utf-8")
    )
    assert prompt_row["prompt"]
    assert prompt_row["request"]["messages"]  # full sent request
    assert "raw_response" not in prompt_row  # no duplication

    # llm_responses row = INCOMING side only (envelope + content + meta).
    llm_row = json.loads(
        next((db / settings.table_llm_responses).glob("*.json")).read_text("utf-8")
    )
    assert '"choices"' in llm_row["raw_response"]  # full raw envelope
    assert llm_row["content"]  # extracted message content
    assert llm_row["model"] and llm_row["duration_ms"] is not None
    assert "request" not in llm_row  # no duplication


def test_evidence_to_store_controls_inline_content(
    settings: Settings, tmp_path
) -> None:
    """A profile can keep an evidence out of the store; metadata still shows it."""
    profiles = {
        "default": {
            "evidence_to_llm": ["TestLogEvidence"],
            # HtmlEvidence deliberately NOT stored
            "evidence_to_store": ["TestLogEvidence"],
        }
    }
    path = tmp_path / "p.json"
    path.write_text(json.dumps(profiles), encoding="utf-8")
    settings = settings.model_copy(update={"profiles_config_path": path})
    client = _client(settings)

    rid = client.post("/analyze/visiumgo", json={"job_id": "job-1"}).json()[
        "analyzer_run_id"
    ]
    client.get(f"/analyze/visiumgo/{rid}")

    row = json.loads(
        next((settings.database_dir / settings.table_evidence).glob("*.json")).read_text(
            "utf-8"
        )
    )
    assert "HtmlEvidence" in row["excluded_from_store"]
    by_file = {a["file_name"]: a for a in row["raw_scenario"]["attachments"]}
    html = by_file["MOCK_browser.default.html"]
    # Excluded: content dropped but the file is still visible in the trace.
    assert html["content"] == ""
    assert html["mime_type"] == "text/html" and html["stored_path"]  # metadata kept
    assert html["content_stored"] is False
    # Kept evidence is untouched.
    assert by_file["MOCK_test.log"]["content"]


def test_precheck_rule_answers_without_calling_llm(
    settings: Settings, tmp_path
) -> None:
    """A matching PreCheck rule must skip the LLM entirely, end to end."""
    rules = [
        {
            "name": "mock_selector",
            # MockSource's error text contains this.
            "match": "NoSuchElementException",
            "verdict": "test_maintenance",
            "confidence": 0.99,
            "suggestion": "Lütfen selector'ı güncelleyin.",
            "error_signature": "hazir-cevap",
        }
    ]
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(rules), encoding="utf-8")
    settings = settings.model_copy(
        update={"precheck_provider": "rules", "precheck_rules_path": path}
    )
    client = _client(settings)

    rid = client.post("/analyze/visiumgo", json={"job_id": "job-1"}).json()[
        "analyzer_run_id"
    ]
    result = client.get(f"/analyze/visiumgo/{rid}").json()

    row = result["results"][0]
    assert row["suggestion"] == "Lütfen selector'ı güncelleyin."  # canned answer
    assert row["error_signature"] == "hazir-cevap"  # which rule answered
    assert row["meta"]["llm_model"] == "precheck"  # LLM was not called
    assert row["status"] == "ok"

    db = settings.database_dir
    # No prompt was built and no LLM answer came back.
    prompt_row = json.loads(
        next((db / settings.table_prompts).glob("*.json")).read_text("utf-8")
    )
    assert prompt_row["prompt"] == ""
    llm_row = json.loads(
        next((db / settings.table_llm_responses).glob("*.json")).read_text("utf-8")
    )
    assert llm_row["raw_response"] == "" and llm_row["content"] == ""


def test_precheck_miss_falls_through_to_llm(settings: Settings, tmp_path) -> None:
    rules = [
        {
            "name": "nope",
            "match": "BOYLE_BIR_HATA_YOK",
            "verdict": "environment_error",
            "confidence": 0.5,
        }
    ]
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(rules), encoding="utf-8")
    settings = settings.model_copy(
        update={"precheck_provider": "rules", "precheck_rules_path": path}
    )
    client = _client(settings)

    rid = client.post("/analyze/visiumgo", json={"job_id": "job-1"}).json()[
        "analyzer_run_id"
    ]
    row = client.get(f"/analyze/visiumgo/{rid}").json()["results"][0]
    assert row["meta"]["llm_model"] == f"MOCK_{settings.llm_model}"  # LLM ran


def test_explicit_parameters_are_recorded(settings: Settings) -> None:
    client = _client(settings)

    rid = client.post(
        "/analyze/visiumgo",
        json={"parameter1": "projeX", "parameter2": "tipY", "job_id": "job-9"},
    ).json()["analyzer_run_id"]

    result = client.get(f"/analyze/visiumgo/{rid}").json()
    assert result["parameter1"] == "projeX"
    assert result["parameter2"] == "tipY"
    for row in result["results"]:
        assert row["parameter1"] == "projeX"
        assert row["parameter2"] == "tipY"


def test_clean_job_returns_nothing_to_analyze(settings: Settings) -> None:
    client = _client(settings)

    analyzer_run_id = client.post(
        "/analyze/visiumgo", json={"job_id": "job-clean"}
    ).json()["analyzer_run_id"]

    result = client.get(f"/analyze/visiumgo/{analyzer_run_id}").json()
    assert result["status"] == "done"
    assert result["scenario_count"] == 0
    assert result["results"] == []
    assert result["note"] == "analiz edilecek hata yok"


def test_job_or_run_id_required(settings: Settings) -> None:
    client = _client(settings)
    # No job_id/run_id -> 422 (parameters alone are not enough).
    resp = client.post("/analyze/visiumgo", json={"parameter1": "x"})
    assert resp.status_code == 422


def test_cache_reuses_previous_analysis(settings: Settings) -> None:
    client = _client(settings)
    job = {"job_id": "job-7"}

    first_id = client.post("/analyze/visiumgo", json=job).json()["analyzer_run_id"]
    second_id = client.post("/analyze/visiumgo", json=job).json()["analyzer_run_id"]

    second = client.get(f"/analyze/visiumgo/{second_id}").json()
    assert second["status"] == "done"
    assert second["cached_from"] == first_id
    assert len(second["results"]) == 2  # served from the first run's rows

    # No new analysis rows were produced for the second run.
    db = settings.database_dir
    assert len(list((db / settings.table_analysis_results).glob("*.json"))) == 2


def test_cache_key_includes_parameters(settings: Settings) -> None:
    # Same run, different parameters -> NOT served from cache.
    client = _client(settings)

    client.post("/analyze/visiumgo", json={"job_id": "job-7"})
    second_id = client.post(
        "/analyze/visiumgo", json={"job_id": "job-7", "parameter1": "projeX"}
    ).json()["analyzer_run_id"]

    second = client.get(f"/analyze/visiumgo/{second_id}").json()
    assert second["cached_from"] == ""  # re-analyzed, not cached


def test_cache_key_is_run_not_job(settings: Settings) -> None:
    """Same job, DIFFERENT run -> must be re-analyzed, not served from cache.

    A job runs many times; each run has its own failures. Keying the cache on
    job_id would hand back an older run's diagnoses.
    """
    client = _client(settings)

    first_id = client.post(
        "/analyze/visiumgo", json={"job_id": "job-7", "run_id": "RUN_1"}
    ).json()["analyzer_run_id"]
    second_id = client.post(
        "/analyze/visiumgo", json={"job_id": "job-7", "run_id": "RUN_2"}
    ).json()["analyzer_run_id"]

    first = client.get(f"/analyze/visiumgo/{first_id}").json()
    second = client.get(f"/analyze/visiumgo/{second_id}").json()
    assert first["run_id"] == "RUN_1" and second["run_id"] == "RUN_2"
    assert second["cached_from"] == ""  # NOT cached — different run
    db = settings.database_dir
    assert len(list((db / settings.table_analysis_results).glob("*.json"))) == 4

    # Same run again -> now it IS cached.
    third_id = client.post(
        "/analyze/visiumgo", json={"job_id": "job-7", "run_id": "RUN_2"}
    ).json()["analyzer_run_id"]
    third = client.get(f"/analyze/visiumgo/{third_id}").json()
    assert third["cached_from"] == second_id


def test_cache_hit_does_not_fetch_evidence(settings: Settings) -> None:
    """A cache hit must skip the whole (expensive) download, not just the LLM."""
    from app.main import build_service

    service = build_service(settings)
    calls: list[str] = []
    real_fetch = service._source.fetch_job

    async def counting_fetch(job_id: str, run_id: str = ""):
        calls.append(run_id or job_id)
        return await real_fetch(job_id, run_id)

    service._source.fetch_job = counting_fetch  # type: ignore[method-assign]

    import asyncio

    first = service.create_run("default", "job-7", "default", "RUN_9")
    asyncio.run(service.run_analysis(first))
    assert len(calls) == 1  # first run fetched

    second = service.create_run("default", "job-7", "default", "RUN_9")
    asyncio.run(service.run_analysis(second))
    assert len(calls) == 1  # cache hit -> no fetch at all
    assert service.get_run(second)["cached_from"] == first


def test_cache_disabled_reanalyzes(settings: Settings) -> None:
    settings = settings.model_copy(update={"cache_enabled": False})
    client = _client(settings)
    job = {"job_id": "job-7"}

    client.post("/analyze/visiumgo", json=job)
    second_id = client.post("/analyze/visiumgo", json=job).json()["analyzer_run_id"]

    second = client.get(f"/analyze/visiumgo/{second_id}").json()
    assert second["cached_from"] == ""
    db = settings.database_dir
    assert len(list((db / settings.table_analysis_results).glob("*.json"))) == 4


def test_unknown_run_id_returns_404(settings: Settings) -> None:
    client = _client(settings)

    assert client.get("/analyze/visiumgo/does-not-exist").status_code == 404
