"""MockSource — deterministic fake VisiumGo data for local development.

Keeps the whole chain runnable on the MacBook (plan.md A15). Every produced
identifier (scenario names, screenshot paths) is `MOCK_`-prefixed (plan.md
A14.2) so mock data is unmistakable in `database/`.

No platform branching (plan.md A0.1): each scenario is filled with ALL raw
fields and tagged with the requested platform. Which of those fields count as
"expected" evidence is decided downstream by the EvidenceRegistry's platform
map — mobile simply never looks at the html/browser fields, etc.

Mock convenience: a `job_id` ending with `-clean` returns a job with zero
failures, to exercise the "nothing to analyze" path (a data condition, not a
variant switch).
"""

from app.domain.enums import Platform
from app.source.base import Source
from app.source.models import JobData, RawScenario

CLEAN_JOB_SUFFIX = "-clean"

_TEST_LOG_1 = """2026-07-16 10:00:01 STEP MOCK_Login sayfasını aç | PASSED
2026-07-16 10:00:03 STEP MOCK_Kullanıcı adını gir | PASSED
2026-07-16 10:00:05 STEP MOCK_Şifreyi gir | PASSED
2026-07-16 10:00:07 STEP MOCK_Giriş butonuna tıkla | FAILED
2026-07-16 10:00:07 ERROR MOCK_NoSuchElementException: Unable to locate element: {"selector":"#login-submit"}
2026-07-16 10:00:07 ERROR   at LoginPage.clickSubmit(LoginPage.java:42)"""

_BROWSER_LOG_1 = """2026-07-16 10:00:02 INFO [console] MOCK_Page loaded: /login
2026-07-16 10:00:07 INFO [console] MOCK_Form validation initialized"""

_DOM_HTML_1 = """<html>
  <body>
    <form id="login-form">
      <button id="btn-login-submit" type="submit">MOCK_Giriş</button>
    </form>
  </body>
</html>"""

_TEST_LOG_2 = """2026-07-16 10:05:01 STEP MOCK_Hesap özeti sayfasını aç | PASSED
2026-07-16 10:05:04 STEP MOCK_Hesap hareketlerini listele | FAILED
2026-07-16 10:05:04 ERROR MOCK_HttpClientErrorException: 401 Unauthorized on GET /api/transactions
2026-07-16 10:05:05 STEP MOCK_Hareketi doğrula | SKIPPED"""

_BROWSER_LOG_2 = """2026-07-16 10:05:04 ERROR [console] MOCK_GET /api/transactions 401 (Unauthorized)
2026-07-16 10:05:04 ERROR [console] MOCK_Session token expired or invalid"""

_DOM_HTML_2 = """<html>
  <body>
    <div class="error-banner">MOCK_Oturum doğrulanamadı</div>
  </body>
</html>"""


def _scenario(
    name: str,
    platform: Platform,
    test_log: str,
    browser_log: str,
    dom_html: str,
    retry_info: str = "",
) -> RawScenario:
    """Build a scenario with all raw fields filled; registry selects per platform."""
    return RawScenario(
        scenario_name=name,
        platform=platform,
        test_log=test_log,
        dom_html=dom_html,
        browser_log=browser_log,
        web_screenshot_path=f"MOCK_attachments/{name}/browser.default.png",
        mobile_screenshot_path=f"MOCK_attachments/{name}/mobile.android.samsung.png",
        retry_info=retry_info,
    )


class MockSource(Source):
    """Returns a canned job with two failed scenarios (out of 100)."""

    async def fetch_job(self, bank: str, job_id: str, platform: Platform) -> JobData:
        if job_id.endswith(CLEAN_JOB_SUFFIX):
            return JobData(
                bank=bank,
                job_id=job_id,
                platform=platform,
                total_scenario_count=100,
                failed_scenarios=[],
            )

        failed = [
            _scenario(
                "MOCK_Login - geçerli kullanıcı ile giriş",
                platform,
                _TEST_LOG_1,
                _BROWSER_LOG_1,
                _DOM_HTML_1,
            ),
            _scenario(
                "MOCK_Hesap özeti - hareket listesi görüntüleme",
                platform,
                _TEST_LOG_2,
                _BROWSER_LOG_2,
                _DOM_HTML_2,
                retry_info="MOCK_1. koşum: FAILED, tekrar koşulmadı",
            ),
        ]
        return JobData(
            bank=bank,
            job_id=job_id,
            platform=platform,
            total_scenario_count=100,
            failed_scenarios=failed,
        )
