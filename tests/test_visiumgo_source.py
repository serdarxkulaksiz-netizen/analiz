"""VisiumGoSource tests with an injected fake HTTP transport (no real server).

Exercises the real-spec chain (Adım A-D): resolve the run (by run_id or by
job_id + state), filter FAILED, fetch detail, download + save attachments, map
to the attachment-based RawScenario, and keep every raw response
(save-everything rule).
"""

import io
import zipfile
from pathlib import Path

import httpx
import pytest

from app.source.models import RunSummary
from app.source.visiumgo import VisiumGoSource
from app.source.visiumgo_client import VisiumGoClient


def _zip_bytes(entries: dict[str, str]) -> bytes:
    """Build an in-memory ZIP, like the real /logs endpoint returns."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, content in entries.items():
            bundle.writestr(name, content)
    return buffer.getvalue()


def _run(run_id: int, state: str) -> dict:
    return {
        "id": run_id,
        "jobId": 886,
        "jobName": "nightly",
        "startTime": "2026-09-07T17:48:49.612314",
        "duration": 163613,
        "runResult": {
            "state": state,
            "totalScenarios": 100,
            "failScenarios": 1,
            "passScenarios": 99,
            "unstableScenarios": 0,
        },
    }


#: Deliberately out of order, and the LARGEST id is a RUNNING run: the newest
#: analyzable run is 149132, not 149140.
_RUNS = [
    _run(149100, "PASSED"),
    _run(149140, "RUNNING"),
    _run(149132, "PASSED"),
    _run(149090, "ABORTED"),  # a state we do not know
]

_RESULTS = [
    {"id": "sc/pass:1", "name": "passing", "resultType": "PASSED"},
    {"id": "sc/unstable:1", "name": "unstable", "resultType": "UNSTABLE"},
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
        {"fileName": "-125/test.properties", "mimeType": "text/plain", "deviceId": "test"},
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
            content=_zip_bytes({"build.log": "MOCK build log", "other.txt": "ilgisiz"}),
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
    if path.startswith("/api/runs/"):  # single run detail
        return httpx.Response(200, json=_run(149132, "PASSED"))
    return httpx.Response(404)


def _source(attachments_dir: Path, build_logs_dir: Path | None = None) -> VisiumGoSource:
    _CAPTURED.clear()
    client = VisiumGoClient(
        base_url="https://visiumgo.test.local",
        token="eyJmock",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(_handler),
    )
    return VisiumGoSource(client, attachments_dir, build_logs_dir)


async def _job(
    source: VisiumGoSource,
    job_id: str = "job-42",
    run_id: str = "",
    *,
    want_build_log: bool = False,
):
    """Resolve then fetch — the two steps the service performs in order."""
    run = await source.resolve_run(job_id, run_id)
    return await source.fetch_job(run, want_build_log=want_build_log)


@pytest.mark.asyncio
async def test_fetch_job_resolves_latest_run_and_filters_failed(tmp_path: Path) -> None:
    source = _source(tmp_path / "attachments")
    run = await source.resolve_run("job-42")
    job = await source.fetch_job(run)

    assert run.run_id == "149132"  # largest id among PASSED/FAILED runs
    assert job.total_scenario_count == 100
    assert len(job.failed_scenarios) == 1  # PASSED and UNSTABLE filtered out

    scenario = job.failed_scenarios[0]
    assert scenario.scenario_name == "Döviz alış başarısız"
    # errorText is kept on the scenario (PreCheck will read it one day); the
    # step list is not read at all — VisiumGo derives it from test.log.
    assert scenario.error_text.startswith("AssertionError")
    assert not hasattr(scenario, "steps")
    assert len(scenario.attachments) == 5


@pytest.mark.asyncio
async def test_run_selection_skips_running_and_reports_unknown_states(tmp_path: Path) -> None:
    """Newest = largest id, but only among runs we may analyze.

    A `RUNNING` run is still writing its evidence, so it is skipped even when
    it has the largest id. A state we do not know is skipped too — and said
    out loud, so a state VisiumGo adds later cannot quietly drop runs.
    """
    source = _source(tmp_path / "attachments")
    summary = await source.resolve_run("job-42")

    assert summary.run_id == "149132"
    assert summary.state == "PASSED"
    assert summary.job_id == "job-42"  # the job the CALLER named
    assert "ABORTED" in summary.note
    assert "RUNNING" not in summary.note  # skipping a running run is normal


@pytest.mark.asyncio
async def test_job_id_path_refuses_to_choose_an_unfinished_run(tmp_path: Path) -> None:
    """...and the error points at the way that DOES work: name the run_id."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/runs":
            return httpx.Response(200, json=[_run(1, "RUNNING")])
        return _handler(request)

    client = VisiumGoClient(
        base_url="https://visiumgo.test.local",
        token="eyJmock",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )
    source = VisiumGoSource(client, tmp_path / "attachments")

    with pytest.raises(ValueError, match="run_id'sini doğrudan ver"):
        await source.resolve_run("job-42")


@pytest.mark.asyncio
async def test_job_level_raw_responses_are_kept(tmp_path: Path) -> None:
    """The two job-level responses survive verbatim; the per-scenario one does not.

    A scenario's detail response used to be carried whole on the model for one
    reason: to be written into the `evidence` row. Nothing read it back, and
    that row no longer stores raw content at all — so it stopped travelling.
    What the detail was FOR still travels: the attachment list it named, and
    the error text PreCheck will read.
    """
    source = _source(tmp_path / "attachments")
    run = await source.resolve_run("job-42")
    job = await source.fetch_job(run)

    # The run response stays on the summary that read it, not copied onto the
    # evidence bundle as well.
    assert run.raw["jobName"] == "nightly"
    assert job.raw_results_response == _RESULTS

    scenario = job.failed_scenarios[0]
    assert not hasattr(scenario, "raw_detail")
    assert scenario.error_text.startswith("AssertionError")
    assert len(scenario.attachments) == 5


@pytest.mark.asyncio
async def test_attachments_downloaded_and_saved(tmp_path: Path) -> None:
    source = _source(tmp_path / "attachments")
    job = await _job(source)
    scenario = job.failed_scenarios[0]

    by_label = {a.label: a for a in scenario.attachments}
    html = by_label["browser.default.html"]
    png = by_label["browser.default.png"]

    assert html.content == "MOCK dosya içeriği"  # text content inlined
    assert png.content == ""  # binary not inlined
    # Both saved to disk for observability.
    assert Path(html.stored_path).is_file()
    assert Path(png.stored_path).read_bytes() == b"\x89PNG_MOCK_BYTES"


@pytest.mark.asyncio
async def test_attachments_saved_under_run_and_scenario_with_ui_names(tmp_path: Path) -> None:
    """Files are named like VisiumGo names them, one folder per scenario.

    The scenario folder is what makes the UI name usable: every scenario of a
    run produces its own `browser.default.html`.
    """
    source = _source(tmp_path / "attachments")
    job = await _job(source)
    scenario = job.failed_scenarios[0]

    stored = {Path(a.stored_path) for a in scenario.attachments}
    names = {path.name for path in stored}
    assert names == {
        "test.log",
        "test.properties",
        "browser.default.log",
        "browser.default.html",
        "browser.default.png",
    }
    folders = {path.parent for path in stored}
    assert len(folders) == 1
    folder = folders.pop()
    # <attachments>/<run_id>/<scenario_id>, with '/' and ':' made path-safe.
    assert folder.name == "1_Bireysel_DovizAlis.feature_250_1278616082_0"
    assert folder.parent.name == "149132"


@pytest.mark.asyncio
async def test_resolve_run_uses_the_single_run_endpoint(tmp_path: Path) -> None:
    # Explicit run_id -> the run detail endpoint is asked (that is what fills
    # job_name / runResult / state), and the listing is NOT queried.
    source = _source(tmp_path / "attachments")
    summary = await source.resolve_run("", "RUN_DIRECT")
    assert [r.url.path for r in _CAPTURED] == ["/api/runs/RUN_DIRECT"]
    assert summary.state == "PASSED"
    assert summary.job_name == "nightly"
    assert summary.job_id == "886"  # from the response, when the caller gave none

    # Only job_id -> newest run resolved with a single listing, no evidence.
    source = _source(tmp_path / "attachments")
    assert (await source.resolve_run("job-42")).run_id == "149132"
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
    return VisiumGoSource(client, tmp_path / "attachments", tmp_path / "build_logs")


@pytest.mark.asyncio
async def test_build_log_extracted_from_zip(tmp_path: Path) -> None:
    # /logs returns a ZIP; build.log is pulled out of it (raw zip not kept).
    source = _source(tmp_path / "attachments", tmp_path / "build_logs")
    job = await _job(source, want_build_log=True)
    assert job.build_log == "MOCK build log"  # not the other entry
    # The working path stays exactly as it was: a successful fetch reports no
    # error at all (this assertion is the regression lock for that).
    assert job.build_log_error == ""
    # It lands on disk as a file of its own, not inline in a row.
    assert Path(job.build_log_path).read_text(encoding="utf-8") == "MOCK build log"
    assert Path(job.build_log_path).parent == tmp_path / "build_logs"


@pytest.mark.asyncio
async def test_build_log_matches_nested_entry(tmp_path: Path) -> None:
    # Entry matched on its ending, so `logs/build.log` works too.
    source = _zip_source(tmp_path, {"logs/build.log": "iç içe"}, "/api/runs/{run_id}/logs")
    job = await _job(source, want_build_log=True)
    assert job.build_log == "iç içe"


@pytest.mark.asyncio
async def test_logs_endpoint_is_not_called_unless_the_profile_wants_it(tmp_path: Path) -> None:
    # The profile decides. Not wanted -> the request is never made at all, so
    # a run that reads no build log pays for no ZIP.
    source = _source(tmp_path / "attachments", tmp_path / "build_logs")
    skipped = await _job(source)
    assert skipped.build_log == ""
    assert skipped.build_log_error == ""
    assert skipped.build_log_path == ""
    assert not [r for r in _CAPTURED if r.url.path.endswith("/logs")]

    # Wanted -> exactly one call.
    wanted = _source(tmp_path / "attachments", tmp_path / "build_logs")
    await _job(wanted, want_build_log=True)
    assert len([r for r in _CAPTURED if r.url.path.endswith("/logs")]) == 1


@pytest.mark.asyncio
async def test_build_log_failure_is_recorded_not_swallowed(tmp_path: Path) -> None:
    # Endpoint errors -> empty log, job continues, but the reason is recorded:
    # a broken endpoint can no longer look like "this job had no build log".
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/logs"):
            return httpx.Response(404)
        return _handler(request)

    client = VisiumGoClient(
        base_url="https://visiumgo.test.local",
        token="eyJmock",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )
    broken = VisiumGoSource(client, tmp_path / "attachments", tmp_path / "build_logs")
    job = await _job(broken, want_build_log=True)
    assert job.build_log == ""
    assert job.build_log_path == ""
    assert len(job.failed_scenarios) == 1  # analysis still happened
    assert "/logs" in job.build_log_error
    assert "404" in job.build_log_error


@pytest.mark.asyncio
async def test_missing_entry_or_non_zip_is_tolerated(tmp_path: Path) -> None:
    # A ZIP without build.log -> empty, no crash; the reason names the wanted
    # entry AND what the archive actually held (that is what makes it fixable).
    source = _zip_source(tmp_path, {"baska.txt": "x"}, "/api/runs/{run_id}/logs")
    job = await _job(source, want_build_log=True)
    assert job.build_log == ""
    assert "build.log" in job.build_log_error
    assert "baska.txt" in job.build_log_error

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
    bad = VisiumGoSource(client, tmp_path / "attachments", tmp_path / "build_logs")
    not_zip = await _job(bad, want_build_log=True)
    assert not_zip.build_log == ""
    assert "BadZipFile" in not_zip.build_log_error


@pytest.mark.asyncio
async def test_run_id_wins_over_job_id_and_no_runs_query(tmp_path: Path) -> None:
    source = _source(tmp_path / "attachments")
    run = await source.resolve_run("job-42", "RUN_DIRECT")
    await source.fetch_job(run)

    assert run.run_id == "149132"  # the id the run detail reports
    # The /api/runs listing must NOT be queried when run_id is given.
    assert not any(r.url.path == "/api/runs" for r in _CAPTURED)


@pytest.mark.asyncio
async def test_fetch_job_does_not_resolve_again(tmp_path: Path) -> None:
    """Resolution happens once: fetching must not ask for the run summary again."""
    source = _source(tmp_path / "attachments")
    await source.fetch_job(RunSummary(run_id="149132", job_id="job-42", state="PASSED"))

    paths = [r.url.path for r in _CAPTURED]
    assert "/api/runs" not in paths
    assert "/api/runs/149132" not in paths


@pytest.mark.asyncio
async def test_auth_header_and_segment_encoding(tmp_path: Path) -> None:
    source = _source(tmp_path / "attachments")
    await _job(source)

    # Every request carries the Bearer token (never hardcoded; from config).
    assert all(r.headers.get("Authorization") == "Bearer eyJmock" for r in _CAPTURED)
    # The scenario id (with '/' and ':') is percent-encoded into one segment.
    detail_reqs = [r for r in _CAPTURED if "/results/" in r.url.path]
    assert detail_reqs
    raw = str(detail_reqs[0].url)
    assert "%2F" in raw and "%3A" in raw  # '/' and ':' encoded, not path separators


@pytest.mark.asyncio
async def test_one_unreadable_scenario_does_not_end_the_run(tmp_path: Path) -> None:
    """A broken `/results` row costs its own analysis, not every other one.

    The detail call used to raise straight out of `fetch_job`, so a single row
    without an `id` — or a single 404 — ended the whole run as `failed` with
    every healthy scenario in it never analyzed.
    """
    rows = [
        {"id": "", "name": "id'siz senaryo", "resultType": "FAILED"},
        {"id": "yok-boyle-senaryo", "name": "404 veren senaryo", "resultType": "FAILED"},
        {
            "id": "1:Bireysel/DovizAlis.feature:250_1278616082:0",
            "name": "sağlam",
            "resultType": "FAILED",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/results"):
            return httpx.Response(200, json=rows)
        if request.url.path.endswith("/results/yok-boyle-senaryo"):
            return httpx.Response(404)
        return _handler(request)

    client = VisiumGoClient(
        base_url="https://visiumgo.test.local",
        token="eyJmock",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )
    source = VisiumGoSource(client, tmp_path / "attachments", tmp_path / "build_logs")

    job = await source.fetch_job(await source.resolve_run("job-42"))

    assert [s.scenario_name for s in job.failed_scenarios] == [
        "id'siz senaryo",
        "404 veren senaryo",
        "sağlam",
    ]
    no_id, not_found, healthy = job.failed_scenarios
    # Each broken one says WHY, and carries no attachments.
    assert "'id' alanı yok" in no_id.fetch_error and no_id.attachments == []
    assert "404" in not_found.fetch_error and not_found.attachments == []
    # The healthy one is untouched.
    assert healthy.fetch_error == "" and len(healthy.attachments) == 5


@pytest.mark.asyncio
async def test_failed_download_records_its_reason(tmp_path: Path) -> None:
    """VisiumGo listed the file, we asked for it, it did not come — say so.

    An empty `content` has three causes: the profile skipped the file, the file
    really is empty, and the download failed. Only the third is a fault, and it
    used to be the one that left no trace at all.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".html"):
            return httpx.Response(500)
        return _handler(request)

    client = VisiumGoClient(
        base_url="https://visiumgo.test.local",
        token="eyJmock",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )
    source = VisiumGoSource(client, tmp_path / "attachments", tmp_path / "build_logs")

    job = await source.fetch_job(await source.resolve_run("job-42"))
    by_name = {a.label: a for a in job.failed_scenarios[0].attachments}

    broken = by_name["browser.default.html"]
    assert broken.content == "" and broken.stored_path == ""
    assert broken.download_skipped is False  # we DID ask for it
    assert "500" in broken.download_error
    assert "browser.default_1.html" in broken.download_error  # which file

    # An untouched file carries no reason at all.
    assert by_name["test.log"].download_error == ""


@pytest.mark.asyncio
async def test_text_is_read_by_extension_not_only_by_mime(tmp_path: Path) -> None:
    """An `.xml` served as `application/xml` must still arrive as text.

    The mime type used to be the only test, so any text file VisiumGo did not
    label `text/*` was read as binary: the file landed on disk, `content` stayed
    empty, and its evidence produced no prompt block — silently.
    """
    detail = {
        "attachments": [
            {
                "fileName": "-125/mobile.ios.iPhone 14_9.xml",
                "mimeType": "application/xml",  # NOT text/*
                "deviceId": "mobile.ios.iPhone 14",
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "/attachments/" in request.url.path:
            return httpx.Response(200, text="<hierarchy><node/></hierarchy>")
        if "/results/" in request.url.path:
            return httpx.Response(200, json=detail)
        return _handler(request)

    client = VisiumGoClient(
        base_url="https://visiumgo.test.local",
        token="eyJmock",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )
    source = VisiumGoSource(client, tmp_path / "attachments", tmp_path / "build_logs")

    job = await source.fetch_job(await source.resolve_run("job-42"))
    (dom,) = job.failed_scenarios[0].attachments

    assert dom.content == "<hierarchy><node/></hierarchy>"  # inline, so it can be prompted
    assert Path(dom.stored_path).is_file()  # and still on disk


@pytest.mark.asyncio
async def test_a_named_run_resolves_even_while_it_is_still_running(tmp_path: Path) -> None:
    """Naming a run_id is an instruction, not a guess — so state cannot veto it.

    The job_id path skips RUNNING runs because "the newest run" is a choice WE
    make, and an unfinished run is the wrong choice. Naming one run is the
    caller's choice, and refusing it left them no way to ask at all.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/runs/149140":
            return httpx.Response(200, json=_run(149140, "RUNNING"))
        return _handler(request)

    client = VisiumGoClient(
        base_url="https://visiumgo.test.local",
        token="eyJmock",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )
    source = VisiumGoSource(client, tmp_path / "attachments")

    summary = await source.resolve_run("", "149140")

    assert summary.run_id == "149140"
    assert summary.state == "RUNNING"  # reported, not refused
    assert summary.job_id == "886"  # taken from the run's own response
