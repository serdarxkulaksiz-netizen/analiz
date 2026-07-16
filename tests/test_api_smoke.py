"""End-to-end smoke test with mocks (plan.md B4 definition of done).

POST /analyze/visiumgo -> background analysis -> full trace under database/
-> GET /analyze/visiumgo/{id} returns the diagnoses. TestClient executes
BackgroundTasks before returning the response, so no polling loop is needed.
"""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def test_end_to_end_with_mocks(settings: Settings) -> None:
    client = _client(settings)

    response = client.post(
        "/analyze/visiumgo", json={"bank": "demo", "job_id": "job-42"}
    )
    assert response.status_code == 200
    body = response.json()
    analyzer_run_id = body["analyzer_run_id"]
    assert body["status"] == "pending"

    result = client.get(f"/analyze/visiumgo/{analyzer_run_id}").json()
    assert result["status"] == "done"
    assert result["scenario_count"] == 2
    assert result["completed_count"] == 2
    assert result["total_scenario_count"] == 100

    verdicts = {row["scenario_name"]: row["verdict"] for row in result["results"]}
    assert verdicts == {
        "Login - geçerli kullanıcı ile giriş": "test_maintenance",
        "Hesap özeti - hareket listesi görüntüleme": "environment_error",
    }
    for row in result["results"]:
        assert row["analysis_failed"] is False
        assert row["confidence"] in {0.1, 0.25, 0.5, 0.75, 0.99}
        assert row["explanation"]  # Turkish content present
        assert row["raw_llm_response"]
        assert row["meta"]["llm_model"] == settings.llm_model

    # Full trace on disk (plan.md A10): one row per table per scenario + run row.
    db = settings.database_dir
    assert len(list((db / settings.table_runs).glob("*.json"))) == 1
    assert len(list((db / settings.table_evidence).glob("*.json"))) == 2
    assert len(list((db / settings.table_prompts).glob("*.json"))) == 2
    assert len(list((db / settings.table_analysis_results).glob("*.json"))) == 2


def test_clean_job_returns_nothing_to_analyze(settings: Settings) -> None:
    client = _client(settings)

    analyzer_run_id = client.post(
        "/analyze/visiumgo", json={"bank": "demo", "job_id": "job-clean"}
    ).json()["analyzer_run_id"]

    result = client.get(f"/analyze/visiumgo/{analyzer_run_id}").json()
    assert result["status"] == "done"
    assert result["scenario_count"] == 0
    assert result["results"] == []
    assert result["note"] == "analiz edilecek hata yok"


def test_cache_reuses_previous_analysis(settings: Settings) -> None:
    client = _client(settings)

    first_id = client.post(
        "/analyze/visiumgo", json={"bank": "demo", "job_id": "job-7"}
    ).json()["analyzer_run_id"]
    second_id = client.post(
        "/analyze/visiumgo", json={"bank": "demo", "job_id": "job-7"}
    ).json()["analyzer_run_id"]

    second = client.get(f"/analyze/visiumgo/{second_id}").json()
    assert second["status"] == "done"
    assert second["cached_from"] == first_id
    assert len(second["results"]) == 2  # served from the first run's rows

    # No new analysis rows were produced for the second run.
    db = settings.database_dir
    assert len(list((db / settings.table_analysis_results).glob("*.json"))) == 2


def test_cache_disabled_reanalyzes(settings: Settings) -> None:
    settings = settings.model_copy(update={"cache_enabled": False})
    client = _client(settings)

    client.post("/analyze/visiumgo", json={"bank": "demo", "job_id": "job-7"})
    second_id = client.post(
        "/analyze/visiumgo", json={"bank": "demo", "job_id": "job-7"}
    ).json()["analyzer_run_id"]

    second = client.get(f"/analyze/visiumgo/{second_id}").json()
    assert second["cached_from"] == ""
    db = settings.database_dir
    assert len(list((db / settings.table_analysis_results).glob("*.json"))) == 4


def test_unknown_run_id_returns_404(settings: Settings) -> None:
    client = _client(settings)

    assert client.get("/analyze/visiumgo/does-not-exist").status_code == 404
