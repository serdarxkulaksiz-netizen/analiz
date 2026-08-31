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
    # Same job, different parameters -> NOT served from cache.
    client = _client(settings)

    client.post("/analyze/visiumgo", json={"job_id": "job-7"})
    second_id = client.post(
        "/analyze/visiumgo", json={"job_id": "job-7", "parameter1": "projeX"}
    ).json()["analyzer_run_id"]

    second = client.get(f"/analyze/visiumgo/{second_id}").json()
    assert second["cached_from"] == ""  # re-analyzed, not cached


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
