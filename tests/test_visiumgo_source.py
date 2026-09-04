"""VisiumGoSource tests with an injected fake HTTP transport (no real server).

Exercises the real-spec chain (Adım A-D): resolve run_id, filter FAILED, fetch
detail, download + save attachments, map to the attachment-based RawScenario,
and keep every raw response (save-everything rule).
"""

import io
import zipfile
from pathlib import Path

import httpx
import pytest

from app.domain.enums import StepStatus
from app.source.visiumgo import VisiumGoSource
from app.source.visiumgo_client import VisiumGoClient


def _zip_bytes(entries: dict[str, str]) -> bytes:
    """Build an in-memory ZIP, like the real /logs endpoint returns."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, content in entries.items():
            bundle.writestr(name, content)
    return buffer.getvalue()

_RUNS = [
    {
        "id": "RUN_OLD",
        "jobName": "nightly",
        "startTime": "2026-07-27T09:00:00",
        "runResult": {"totalScenarios": 100},
    },
    {
        "id": "RUN_NEW",
        "jobName": "nightly",
        "startTime": "2026-07-27T10:20:08",
        "runResult": {"totalScenarios": 100},
    },
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
        {"line": "Döviz sayfasını aç", "resultType": "PASSED", "stepLine": "6"},
        {"line": "Tutarı doğrula", "resultType": "FAILED", "stepLine": "284"},
        {"line": "Sonucu kaydet", "resultType": "SKIPPED", "stepLine": "285"},
    ],
    "attachments": [
        {"fileName": "-125/test_1.log", "mimeType": "text/plain", "deviceId": "test"},
        {
            "fileName": "-125/browser.default_1.log",
            "mimeType": "text/plain",
            "deviceId": "browser.default",
        },
        {
            "fileName": "-125/browser.default_1.html",
            "mimeType": "text/html",
            "deviceId": "browser.default",
        },
        {
            "fileName": "-125/browser.default_1.png",
            "mimeType": "image/png",
            "deviceId": "browser.default",
        },
    ],
    "properties": {"retryNumber": "0", "mobile.ios.iPhone 14 Pro Max": "Name:X-UDID:Y"},
}

_CAPTURED: list[httpx.Request] = []


def _handler(request: httpx.Request) -> httpx.Response:
    _CAPTURED.append(request)
    path = request.url.path
    if path.endswith("/logs"):
        # The real endpoint returns a ZIP archive containing build.log.
        return httpx.Response(
            200,
            content=_zip_bytes(
                {"build.log": "MOCK build log", "other.txt": "ilgisiz"}
            ),
        )
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


def _source(attachments_dir: Path, build_log_path: str = "") -> VisiumGoSource:
    _CAPTURED.clear()
    client = VisiumGoClient(
        base_url="https://visiumgo.test.local",
        token="eyJmock",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(_handler),
    )
    return VisiumGoSource(client, attachments_dir, build_log_path=build_log_path)


@pytest.mark.asyncio
async def test_fetch_job_resolves_latest_run_and_filters_failed(tmp_path: Path) -> None:
    source = _source(tmp_path / "attachments")
    job = await source.fetch_job("job-42")

    assert job.run_id == "RUN_NEW"  # newest by startTime (ISO string order)
    assert job.total_scenario_count == 100
    assert len(job.failed_scenarios) == 1  # PASSED filtered out

    scenario = job.failed_scenarios[0]
    assert scenario.scenario_name == "Döviz alış başarısız"
    assert scenario.error_text.startswith("AssertionError")
    # Step names come from `line` (human text), not `stepLine` (line number).
    assert [s.name for s in scenario.steps] == [
        "Döviz sayfasını aç",
        "Tutarı doğrula",
        "Sonucu kaydet",
    ]
    assert [s.status for s in scenario.steps] == [
        StepStatus.PASSED,
        StepStatus.FAILED,
        StepStatus.SKIPPED,
    ]
    assert len(scenario.attachments) == 4


@pytest.mark.asyncio
async def test_every_raw_response_is_kept(tmp_path: Path) -> None:
    # Save-everything rule: run response, /results array and scenario detail
    # all survive verbatim on the models.
    source = _source(tmp_path / "attachments")
    job = await source.fetch_job("job-42")

    assert job.raw_run_response["jobName"] == "nightly"
    assert job.raw_results_response == _RESULTS
    scenario = job.failed_scenarios[0]
    assert scenario.raw_detail["properties"]["retryNumber"] == "0"


@pytest.mark.asyncio
async def test_attachments_downloaded_and_saved(tmp_path: Path) -> None:
    source = _source(tmp_path / "attachments")
    job = await source.fetch_job("job-42")
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
async def test_resolve_run_id_is_cheap_and_correct(tmp_path: Path) -> None:
    # Explicit run_id -> returned as-is, WITHOUT any network call (this is what
    # makes a cache hit free).
    source = _source(tmp_path / "attachments")
    assert await source.resolve_run_id("job-42", "RUN_DIRECT") == "RUN_DIRECT"
    assert _CAPTURED == []

    # Only job_id -> newest run resolved with a single lookup, no evidence.
    source = _source(tmp_path / "attachments")
    assert await source.resolve_run_id("job-42") == "RUN_NEW"
    assert [r.url.path for r in _CAPTURED] == ["/api/runs"]


def _zip_source(tmp_path: Path, entries: dict[str, str], path: str) -> VisiumGoSource:
    """Source whose /logs endpoint returns the given ZIP entries."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(("/logs", "/nolog")):
            return httpx.Response(200, content=_zip_bytes(entries))
        return _handler(request)

    client = VisiumGoClient(
        base_url="https://visiumgo.test.local",
        token="eyJmock",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )
    return VisiumGoSource(client, tmp_path / "attachments", build_log_path=path)


@pytest.mark.asyncio
async def test_build_log_extracted_from_zip(tmp_path: Path) -> None:
    # /logs returns a ZIP; build.log is pulled out of it (raw zip not kept).
    source = _source(
        tmp_path / "attachments", build_log_path="/api/runs/{run_id}/logs"
    )
    job = await source.fetch_job("job-42")
    assert job.build_log == "MOCK build log"  # not the other entry


@pytest.mark.asyncio
async def test_build_log_matches_nested_entry(tmp_path: Path) -> None:
    # Entry matched on its ending, so `logs/build.log` works too.
    source = _zip_source(
        tmp_path, {"logs/build.log": "iç içe"}, "/api/runs/{run_id}/logs"
    )
    job = await source.fetch_job("job-42")
    assert job.build_log == "iç içe"


@pytest.mark.asyncio
async def test_build_log_skipped_when_unset_or_endpoint_fails(tmp_path: Path) -> None:
    # Unset path -> step skipped entirely.
    source = _source(tmp_path / "attachments")
    assert (await source.fetch_job("job-42")).build_log == ""

    # Endpoint errors -> empty log, job continues.
    broken = _source(tmp_path / "attachments", build_log_path="/api/does-not-exist")
    job = await broken.fetch_job("job-42")
    assert job.build_log == ""
    assert len(job.failed_scenarios) == 1  # analysis still happened


@pytest.mark.asyncio
async def test_missing_entry_or_non_zip_is_tolerated(tmp_path: Path) -> None:
    # A ZIP without build.log -> empty, no crash.
    source = _zip_source(tmp_path, {"baska.txt": "x"}, "/api/runs/{run_id}/logs")
    assert (await source.fetch_job("job-42")).build_log == ""

    # Not a ZIP at all -> empty, no crash.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/logs"):
            return httpx.Response(200, content=b"bu bir zip degil")
        return _handler(request)

    client = VisiumGoClient(
        base_url="https://visiumgo.test.local",
        token="eyJmock",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )
    bad = VisiumGoSource(
        client, tmp_path / "attachments", build_log_path="/api/runs/{run_id}/logs"
    )
    assert (await bad.fetch_job("job-42")).build_log == ""


@pytest.mark.asyncio
async def test_run_id_wins_over_job_id_and_no_runs_query(tmp_path: Path) -> None:
    source = _source(tmp_path / "attachments")
    job = await source.fetch_job("job-42", run_id="RUN_DIRECT")

    assert job.run_id == "RUN_DIRECT"
    # The /api/runs listing must NOT be queried when run_id is given.
    assert not any(r.url.path == "/api/runs" for r in _CAPTURED)


@pytest.mark.asyncio
async def test_auth_header_and_segment_encoding(tmp_path: Path) -> None:
    source = _source(tmp_path / "attachments")
    await source.fetch_job("job-42")

    # Every request carries the Bearer token (never hardcoded; from config).
    assert all(
        r.headers.get("Authorization") == "Bearer eyJmock" for r in _CAPTURED
    )
    # The scenario id (with '/' and ':') is percent-encoded into one segment.
    detail_reqs = [r for r in _CAPTURED if "/results/" in r.url.path]
    assert detail_reqs
    raw = str(detail_reqs[0].url)
    assert "%2F" in raw and "%3A" in raw  # '/' and ':' encoded, not path separators
