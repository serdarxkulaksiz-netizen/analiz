"""MockSource — deterministic fake VisiumGo data for local development.

Keeps the whole chain runnable without real services. Produces the same
attachment-based `RawScenario` as the real source, so extraction is identical.
Every produced identifier/content is `MOCK_`-prefixed (plan.md A14.2).

Each mock scenario carries the FULL attachment set (all 5 evidence types);
which of them reach the prompt is decided downstream by the analysis profile
(parameter1/parameter2), exactly like with real data.

Mock convenience: a `job_id` ending with `-clean` returns a job with zero
failures (a data condition, not a variant switch).
"""

from app.domain.enums import StepStatus
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

# Job-level log: contains EVERY scenario, like the real one. Profiles can slice
# it per scenario with a `keep_scenario_section` rule.
_JENKINS_LOG = """MOCK_[jenkins] build started
Scenario: MOCK_Login - geçerli kullanıcı ile giriş
MOCK_  adım 1 ok
MOCK_  adım 2 FAILED: #login-submit yok
Scenario: MOCK_Hesap özeti - hareket listesi görüntüleme
MOCK_  adım 1 ok
MOCK_  adım 2 FAILED: tablo boş
MOCK_[jenkins] build finished"""


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


# Full attachment set — the profile (not the source) decides what reaches the LLM.
_ALL_ATTACHMENTS: list[Attachment] = [
    _text("test.log", "test", _TEST_LOG),
    _text("browser.default.log", "browser.default", _BROWSER_LOG),
    _text("browser.default.html", "browser.default", _HTML, mime="text/html"),
    _png("browser.default.png", "browser.default"),
    _png("mobile.android.samsung.png", "mobile.android.samsung"),
]


def _scenario(name: str, retry_info: str = "") -> RawScenario:
    return RawScenario(
        scenario_name=name,
        scenario_id=f"MOCK_{name}",
        error_text=_ERROR_TEXT,
        steps=_STEPS,
        attachments=_ALL_ATTACHMENTS,
        retry_info=retry_info,
        raw_detail={"MOCK_note": "sahte senaryo-detay ham cevabı", "name": name},
    )


class MockSource(Source):
    """Returns a canned job with two failed scenarios (out of 100)."""

    async def resolve_run_id(self, job_id: str, run_id: str = "") -> str:
        # Per-job ids, like the real source: two different jobs must never look
        # like the same run (the cache keys on run_id).
        return run_id or f"MOCK_run_{job_id}"

    async def fetch_job(self, job_id: str, run_id: str = "") -> JobData:
        resolved = await self.resolve_run_id(job_id, run_id)
        if job_id.endswith(CLEAN_JOB_SUFFIX):
            return JobData(
                job_id=job_id,
                run_id=resolved,
                job_name="MOCK_nightly-test",
                run_result={
                    "state": "PASSED",
                    "totalScenarios": 100,
                    "failScenarios": 0,
                    "passScenarios": 100,
                    "unstableScenarios": 0,
                },
                total_scenario_count=100,
                failed_scenarios=[],
                raw_run_response={"jobName": "MOCK_nightly-test", "state": "PASSED"},
                raw_results_response=[],
            )

        failed = [
            _scenario("MOCK_Login - geçerli kullanıcı ile giriş"),
            _scenario(
                "MOCK_Hesap özeti - hareket listesi görüntüleme",
                retry_info="MOCK_1. koşum: FAILED",
            ),
        ]
        return JobData(
            job_id=job_id,
            run_id=resolved,
            job_name="MOCK_nightly-test",
            run_result={
                "state": "FAILED",
                "totalScenarios": 100,
                "failScenarios": len(failed),
                "passScenarios": 100 - len(failed),
                "unstableScenarios": 0,
            },
            total_scenario_count=100,
            failed_scenarios=failed,
            jenkins_console_log=_JENKINS_LOG,
            raw_run_response={"jobName": "MOCK_nightly-test", "state": "FAILED"},
            raw_results_response=[
                {"id": s.scenario_id, "name": s.scenario_name, "resultType": "FAILED"}
                for s in failed
            ],
        )
