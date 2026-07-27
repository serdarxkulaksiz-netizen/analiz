"""MockSource — deterministic fake VisiumGo data for local development.

Keeps the whole chain runnable on the MacBook (plan.md A15). Produces the same
attachment-based `RawScenario` as the real source, so extraction is identical.
Every produced identifier/content is `MOCK_`-prefixed (plan.md A14.2).

No platform branching (plan.md A0.1): the per-platform attachment set is a
data lookup in `_ATTACHMENTS_BY_PLATFORM` (a dict = registry, not an `if`).

Mock convenience: a `job_id` ending with `-clean` returns a job with zero
failures (a data condition, not a variant switch).
"""

from app.domain.enums import Platform, StepStatus
from app.domain.findings import Step
from app.source.base import Source
from app.source.models import Attachment, JobData, RawScenario

CLEAN_JOB_SUFFIX = "-clean"

_TEST_LOG = """2026-07-16 10:00:01 STEP MOCK_Login sayfasını aç | PASSED
2026-07-16 10:00:07 STEP MOCK_Giriş butonuna tıkla | FAILED
2026-07-16 10:00:07 ERROR MOCK_NoSuchElementException: #login-submit"""

_BROWSER_LOG = "2026-07-16 10:00:07 INFO [console] MOCK_Form validation initialized"

_HTML = "<html><body><button id='btn-login-submit'>MOCK_Giriş</button></body></html>"

_STEPS = [
    Step(name="MOCK_Login sayfasını aç", status=StepStatus.PASSED),
    Step(name="MOCK_Giriş butonuna tıkla", status=StepStatus.FAILED),
]

_ERROR_TEXT = "MOCK_NoSuchElementException: Unable to locate element #login-submit"


def _text(file_name: str, device_id: str, content: str, mime: str = "text/plain") -> Attachment:
    return Attachment(
        file_name=f"MOCK_{file_name}",
        mime_type=mime,
        device_id=device_id,
        content=content,
        stored_path=f"MOCK_attachments/{file_name}",
    )


def _png(file_name: str, device_id: str) -> Attachment:
    return Attachment(
        file_name=f"MOCK_{file_name}",
        mime_type="image/png",
        device_id=device_id,
        stored_path=f"MOCK_attachments/{file_name}",
    )


# Per-platform attachment set (dict lookup, not an `if platform ==`).
_ATTACHMENTS_BY_PLATFORM: dict[Platform, list[Attachment]] = {
    Platform.WEB: [
        _text("test.log", "test", _TEST_LOG),
        _text("browser.default.log", "browser.default", _BROWSER_LOG),
        _text("browser.default.html", "browser.default", _HTML, mime="text/html"),
        _png("browser.default.png", "browser.default"),
    ],
    Platform.MOBILE: [
        _text("test.log", "test", _TEST_LOG),
        _png("mobile.android.samsung.png", "mobile.android.samsung"),
    ],
    Platform.HYBRID: [
        _text("test.log", "test", _TEST_LOG),
        _text("browser.default.log", "browser.default", _BROWSER_LOG),
        _text("browser.default.html", "browser.default", _HTML, mime="text/html"),
        _png("mobile.ios.iPhone.png", "mobile.ios.iPhone"),
    ],
}


def _scenario(name: str, platform: Platform, retry_info: str = "") -> RawScenario:
    return RawScenario(
        scenario_name=name,
        platform=platform,
        scenario_id=f"MOCK_{name}",
        error_text=_ERROR_TEXT,
        steps=_STEPS,
        attachments=_ATTACHMENTS_BY_PLATFORM.get(platform, []),
        retry_info=retry_info,
    )


class MockSource(Source):
    """Returns a canned job with two failed scenarios (out of 100)."""

    async def fetch_job(
        self, bank: str, job_id: str, platform: Platform, run_id: str = ""
    ) -> JobData:
        if job_id.endswith(CLEAN_JOB_SUFFIX):
            return JobData(
                bank=bank,
                job_id=job_id,
                run_id=run_id or "MOCK_run",
                platform=platform,
                total_scenario_count=100,
                failed_scenarios=[],
            )

        failed = [
            _scenario("MOCK_Login - geçerli kullanıcı ile giriş", platform),
            _scenario(
                "MOCK_Hesap özeti - hareket listesi görüntüleme",
                platform,
                retry_info="MOCK_1. koşum: FAILED",
            ),
        ]
        return JobData(
            bank=bank,
            job_id=job_id,
            run_id=run_id or "MOCK_run",
            platform=platform,
            total_scenario_count=100,
            failed_scenarios=failed,
        )
