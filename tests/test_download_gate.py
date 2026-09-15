"""The profile decides what is downloaded at all.

Three separate guarantees:
  * a file no profile wants is never fetched — but it is still reported,
  * a file no Evidence class claims is ALWAYS fetched (it is the interesting one),
  * a config that prompts what it does not store fails at startup.
"""

from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.evidence.plan import AnalysisPlan, plan_for
from app.evidence.profiles import ProfileRegistry
from app.main import build_service
from app.source.models import Attachment
from app.source.visiumgo import VisiumGoSource
from app.source.visiumgo_client import VisiumGoClient
from tests.conftest import write_profiles


def _att(device: str, extension: str, mime: str = "text/plain") -> Attachment:
    return Attachment(file_name=f"220/{device}_1{extension}", mime_type=mime, device_id=device)


def _plan(tmp_path: Path, profiles: dict) -> AnalysisPlan:
    return plan_for(ProfileRegistry(write_profiles(tmp_path / "p.json", profiles)))


def test_filter_follows_the_profile(tmp_path: Path) -> None:
    plan = _plan(
        tmp_path,
        {
            "default_web": {
                "evidence_to_llm": ["TestLogEvidence"],
                "evidence_to_store": ["TestLogEvidence", "WebScreenshotEvidence"],
            }
        },
    )
    wants = plan.wants

    assert wants(_att("test", ".log")) is True  # prompted
    assert wants(_att("browser.default", ".png", "image/png")) is True  # stored only
    assert wants(_att("browser.default", ".html", "text/html")) is False  # neither list


def test_unknown_file_is_always_fetched(tmp_path: Path) -> None:
    """We cannot judge a file we never look at.

    A device or extension no Evidence claims is exactly what the evidence
    report exists to surface; skipping it would hide the change we most want
    to notice.
    """
    plan = _plan(tmp_path, {"default_web": {"evidence_to_llm": ["TestLogEvidence"]}})

    assert plan.wants(_att("bilinmeyen-cihaz", ".pdf", "application/pdf")) is True


def test_prompting_what_is_not_stored_fails_at_startup(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="evidence_to_store'da yok"):
        ProfileRegistry(
            write_profiles(
                tmp_path / "p.json",
                {
                    "default_web": {
                        "evidence_to_llm": ["HtmlEvidence"],
                        "evidence_to_store": ["TestLogEvidence"],
                    }
                },
                complete=True,
            )
        )


def test_unknown_evidence_name_fails_at_startup(settings: Settings, tmp_path: Path) -> None:
    """A typo in `evidence_to_llm` would otherwise silently disable an evidence."""
    path = write_profiles(
        tmp_path / "p.json", {"default_web": {"evidence_to_llm": ["TestLogEvidenc"]}}
    )
    with pytest.raises(ValueError, match="unknown evidence"):
        build_service(settings.model_copy(update={"profiles_config_path": path}))


_DETAIL = {
    "errorText": "AssertionError",
    "stepResults": [],
    "attachments": [
        {"fileName": "-1/test_1.log", "mimeType": "text/plain", "deviceId": "test"},
        {
            "fileName": "-1/browser.default_1.html",
            "mimeType": "text/html",
            "deviceId": "browser.default",
        },
    ],
}


@pytest.mark.asyncio
async def test_unwanted_attachment_is_not_requested_but_is_reported(tmp_path: Path) -> None:
    """No request, no bytes, no file — but the row stays, flagged."""
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/attachments/" in path:
            requested.append(path)
            return httpx.Response(200, text="içerik")
        if "/results/" in path:
            return httpx.Response(200, json=_DETAIL)
        if path.endswith("/results"):
            return httpx.Response(200, json=[{"id": "s1", "name": "S", "resultType": "FAILED"}])
        return httpx.Response(404)

    source = VisiumGoSource(
        VisiumGoClient(
            base_url="https://visiumgo.test.local",
            token="t",
            timeout_seconds=5.0,
            transport=httpx.MockTransport(handler),
        ),
        tmp_path / "attachments",
    )
    plan = _plan(tmp_path, {"default_web": {"evidence_to_llm": ["TestLogEvidence"]}})
    wants = plan.wants

    from app.source.models import RunSummary

    job = await source.fetch_job(RunSummary(run_id="1", job_id="j", state="PASSED"), wants)

    by_label = {a.label: a for a in job.failed_scenarios[0].attachments}
    assert by_label["test.log"].content == "içerik"
    html = by_label["browser.default.html"]
    assert html.download_skipped is True
    assert html.content == "" and html.stored_path == ""
    # The unwanted file cost nothing: it was never asked for.
    assert not any("html" in path for path in requested)
