"""MockSource — deterministic fake VisiumGo data for local development.

Keeps the whole chain runnable without real services. Produces the same
attachment-based `RawScenario` as the real source, so extraction is identical.
Every produced identifier/content is `MOCK_`-prefixed (plan.md A14.2).

Each mock scenario carries the FULL attachment set seen in real runs — web
(`browser.default` html/log/png), mobile (`mobile.*` xml/png) and the two
`test` files (`test.log`, `test.properties`) — because "which attachments
exist" is exactly what varies in production, and a mock that only knows the
happy set hides mapping bugs until the work PC finds them. Which of them reach
the prompt is decided downstream by the analysis profile, like with real data.

Mock conveniences, all DATA conditions on `job_id` (not variant switches):
  `-clean`   -> a run with zero failures
  `-jobfail` -> the job itself failed (`runResult.state == "FAILED"`)
  `-running` -> the run is still going (`RUNNING`); the service refuses it
"""

from app.domain.enums import RunState, StepStatus
from app.domain.findings import Step
from app.source.base import Source
from app.source.models import Attachment, JobData, RawScenario, RunSummary

CLEAN_JOB_SUFFIX = "-clean"
JOB_FAILED_SUFFIX = "-jobfail"
RUNNING_JOB_SUFFIX = "-running"

_TEST_LOG = """2026-07-16 10:00:01 STEP MOCK_Login sayfasını aç | PASSED
2026-07-16 10:00:07 STEP MOCK_Giriş butonuna tıkla | FAILED
2026-07-16 10:00:07 ERROR MOCK_NoSuchElementException: #login-submit"""

_TEST_PROPERTIES = """mobile.android.samsung=Name:MOCK_R58-UDID:MOCK_R58
failedStep.name=MOCK_Giriş butonuna tıkla
failedStep.line=42"""

_BROWSER_LOG = "2026-07-16 10:00:07 INFO [console] MOCK_Form validation initialized"

_HTML = "<html><body><button id='btn-login-submit'>MOCK_Giriş</button></body></html>"

_MOBILE_DOM = (
    "<hierarchy><android.widget.Button "
    "resource-id='btn-login-submit' text='MOCK_Giriş'/></hierarchy>"
)

_STEPS = [
    Step(name="MOCK_Login sayfasını aç", status=StepStatus.PASSED),
    Step(name="MOCK_Giriş butonuna tıkla", status=StepStatus.FAILED),
]

_ERROR_TEXT = "MOCK_NoSuchElementException: Unable to locate element #login-submit"

# Job-level log: contains EVERY scenario, like the real one. Profiles can slice
# it per scenario with a `keep_scenario_section` rule.
_BUILD_LOG = """MOCK_[jenkins] build started
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
    _text("test.properties", "test", _TEST_PROPERTIES),
    _text("browser.default.log", "browser.default", _BROWSER_LOG),
    _text("browser.default.html", "browser.default", _HTML, mime="text/html"),
    _text("mobile.android.samsung.xml", "mobile.android.samsung", _MOBILE_DOM, mime="text/xml"),
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


def _state_for(job_id: str) -> str:
    """Job-level state this fake job reports (a data condition on job_id)."""
    if job_id.endswith(RUNNING_JOB_SUFFIX):
        return RunState.RUNNING.value
    if job_id.endswith(JOB_FAILED_SUFFIX):
        return RunState.FAILED.value
    # Like real VisiumGo: the job itself ran fine even when scenarios failed.
    return RunState.PASSED.value


class MockSource(Source):
    """Returns a canned job with two failed scenarios (out of 100)."""

    async def resolve_run(self, job_id: str, run_id: str = "") -> RunSummary:
        if not job_id and not run_id:
            raise ValueError("Either job_id or run_id is required.")
        # Per-job ids, like the real source: two different jobs must never look
        # like the same run (the cache keys on run_id).
        resolved = run_id or f"MOCK_run_{job_id}"
        clean = job_id.endswith(CLEAN_JOB_SUFFIX)
        failed_count = 0 if clean else 2
        return RunSummary(
            run_id=resolved,
            job_id=job_id,
            job_name="MOCK_nightly-test",
            state=_state_for(job_id),
            run_result={
                "state": _state_for(job_id),
                "totalScenarios": 100,
                "failScenarios": failed_count,
                "passScenarios": 100 - failed_count,
                "unstableScenarios": 0,
            },
            raw={"jobName": "MOCK_nightly-test", "id": resolved, "jobId": job_id},
        )

    async def fetch_job(self, run: RunSummary) -> JobData:
        failed: list[RawScenario] = []
        if not run.job_id.endswith(CLEAN_JOB_SUFFIX):
            failed = [
                _scenario("MOCK_Login - geçerli kullanıcı ile giriş"),
                _scenario(
                    "MOCK_Hesap özeti - hareket listesi görüntüleme",
                    retry_info="MOCK_1. koşum: FAILED",
                ),
            ]
        return JobData(
            job_id=run.job_id,
            run_id=run.run_id,
            job_name=run.job_name,
            run_result=run.run_result,
            total_scenario_count=100,
            failed_scenarios=failed,
            build_log=_BUILD_LOG if failed else "",
            raw_run_response=run.raw,
            raw_results_response=[
                {"id": s.scenario_id, "name": s.scenario_name, "resultType": "FAILED"}
                for s in failed
            ],
        )
