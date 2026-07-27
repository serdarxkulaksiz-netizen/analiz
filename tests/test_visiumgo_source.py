"""VisiumGoSource tests with an injected fake HTTP transport (no real server).

Exercises the real-spec chain (Adım A-D): resolve run_id, filter FAILED, fetch
detail, download + save attachments, map to the attachment-based RawScenario.
"""

from pathlib import Path

import httpx
import pytest

from app.domain.enums import Platform, StepStatus
from app.source.visiumgo import VisiumGoSource
from app.source.visiumgo_client import VisiumGoClient

_RUNS = [
    {"id": "RUN_OLD", "jobName": "nightly", "startTime": 100, "runResult": {"totalScenarios": 100}},
    {"id": "RUN_NEW", "jobName": "nightly", "startTime": 200, "runResult": {"totalScenarios": 100}},
]

_RESULTS = [
    {"id": "sc/pass:1", "name": "passing", "resultType": "PASSED"},
    {
        "id": "1:Bireysel/DovizAlis.feature:250_1278616082:0",
        "name": "Döviz alış başarısız",
        "resultType": "FAILED",
        "retryNumber": 1,
    },
]

_DETAIL = {
    "errorText": "AssertionError: beklenen tutar bulunamadı",
    "stepResults": [
        {"stepLine": "Döviz sayfasını aç", "resultType": "PASSED"},
        {"stepLine": "Tutarı doğrula", "resultType": "FAILED"},
        {"stepLine": "Sonucu kaydet", "resultType": "SKIPPED"},
    ],
    "attachments": [
        {"fileName": "-125/test_1.log", "mimeType": "text/plain", "deviceId": "test"},
        {"fileName": "-125/browser.default_1.log", "mimeType": "text/plain", "deviceId": "browser.default"},
        {"fileName": "-125/browser.default_1.html", "mimeType": "text/html", "deviceId": "browser.default"},
        {"fileName": "-125/browser.default_1.png", "mimeType": "image/png", "deviceId": "browser.default"},
    ],
}

_CAPTURED: list[httpx.Request] = []


def _handler(request: httpx.Request) -> httpx.Response:
    _CAPTURED.append(request)
    path = request.url.path
    if "/attachments/" in path:
        if path.endswith(".png"):
            return httpx.Response(200, content=b"\x89PNG_MOCK_BYTES")
        return httpx.Response(200, text="MOCK dosya içeriği")
    if "/results/" in path:  # scenario detail
        return httpx.Response(200, json=_DETAIL)
    if path.endswith("/results"):
        return httpx.Response(200, json=_RESULTS)
    if path == "/api/runs":
        assert request.url.params.get("jobId") == "job-42"
        return httpx.Response(200, json=_RUNS)
    return httpx.Response(404)


def _source(attachments_dir: Path) -> VisiumGoSource:
    _CAPTURED.clear()
    client = VisiumGoClient(
        base_url="https://visiumgo.test.local",
        token="eyJmock",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(_handler),
    )
    return VisiumGoSource(client, attachments_dir)


@pytest.mark.asyncio
async def test_fetch_job_resolves_latest_run_and_filters_failed(tmp_path: Path) -> None:
    source = _source(tmp_path / "attachments")
    job = await source.fetch_job("demo", "job-42", Platform.WEB)

    assert job.run_id == "RUN_NEW"  # newest by startTime
    assert job.total_scenario_count == 100
    assert len(job.failed_scenarios) == 1  # PASSED filtered out

    scenario = job.failed_scenarios[0]
    assert scenario.scenario_name == "Döviz alış başarısız"
    assert scenario.error_text.startswith("AssertionError")
    assert [s.status for s in scenario.steps] == [
        StepStatus.PASSED,
        StepStatus.FAILED,
        StepStatus.SKIPPED,
    ]
    assert len(scenario.attachments) == 4


@pytest.mark.asyncio
async def test_attachments_downloaded_and_saved(tmp_path: Path) -> None:
    source = _source(tmp_path / "attachments")
    job = await source.fetch_job("demo", "job-42", Platform.WEB)
    scenario = job.failed_scenarios[0]

    by_device = {(a.mime_type, a.device_id): a for a in scenario.attachments}
    html = by_device[("text/html", "browser.default")]
    png = by_device[("image/png", "browser.default")]

    assert html.content == "MOCK dosya içeriği"  # text content inlined
    assert png.content == ""  # binary not inlined
    # Both saved to disk for observability.
    assert Path(html.stored_path).is_file()
    assert Path(png.stored_path).read_bytes() == b"\x89PNG_MOCK_BYTES"


@pytest.mark.asyncio
async def test_run_id_wins_over_job_id_and_no_runs_query(tmp_path: Path) -> None:
    source = _source(tmp_path / "attachments")
    job = await source.fetch_job("demo", "job-42", Platform.WEB, run_id="RUN_DIRECT")

    assert job.run_id == "RUN_DIRECT"
    # The /api/runs listing must NOT be queried when run_id is given.
    assert not any(r.url.path == "/api/runs" for r in _CAPTURED)


@pytest.mark.asyncio
async def test_auth_header_and_segment_encoding(tmp_path: Path) -> None:
    source = _source(tmp_path / "attachments")
    await source.fetch_job("demo", "job-42", Platform.WEB)

    # Every request carries the Bearer token (never hardcoded; from config).
    assert all(
        r.headers.get("Authorization") == "Bearer eyJmock" for r in _CAPTURED
    )
    # The scenario id (with '/' and ':') is percent-encoded into one segment.
    detail_reqs = [
        r for r in _CAPTURED if "/results/" in r.url.path
    ]
    assert detail_reqs
    raw = str(detail_reqs[0].url)
    assert "%2F" in raw and "%3A" in raw  # '/' and ':' encoded, not path separators
