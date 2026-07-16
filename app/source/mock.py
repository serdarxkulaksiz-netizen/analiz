"""MockSource — deterministic fake VisiumGo data for local development.

Keeps the whole chain runnable on the MacBook (plan.md A12). Log contents are
mock fixture data. Mock convenience: a `job_id` ending with `-clean` returns
a job with zero failures, to exercise the "nothing to analyze" path.
"""

from app.domain.enums import Platform
from app.source.base import Source
from app.source.models import JobData, RawScenario

CLEAN_JOB_SUFFIX = "-clean"

_WEB_TEST_LOG = """2026-07-16 10:00:01 STEP Login sayfasını aç | PASSED
2026-07-16 10:00:03 STEP Kullanıcı adını gir | PASSED
2026-07-16 10:00:05 STEP Şifreyi gir | PASSED
2026-07-16 10:00:07 STEP Giriş butonuna tıkla | FAILED
2026-07-16 10:00:07 ERROR NoSuchElementException: Unable to locate element: {"method":"css selector","selector":"#login-submit"}
2026-07-16 10:00:07 ERROR   at LoginPage.clickSubmit(LoginPage.java:42)
2026-07-16 10:00:07 ERROR   at LoginTest.validLogin(LoginTest.java:18)"""

_WEB_BROWSER_LOG = """2026-07-16 10:00:02 INFO [console] Page loaded: /login
2026-07-16 10:00:06 WARN [console] Deprecated API usage: findElementLegacy
2026-07-16 10:00:07 INFO [console] Form validation initialized"""

_WEB_DOM_HTML = """<html>
  <body>
    <form id="login-form">
      <input id="username" type="text" value="qa_user" />
      <input id="password" type="password" />
      <button id="btn-login-submit" type="submit">Giriş</button>
    </form>
  </body>
</html>"""

_WEB2_TEST_LOG = """2026-07-16 10:05:01 STEP Hesap özeti sayfasını aç | PASSED
2026-07-16 10:05:04 STEP Hesap hareketlerini listele | FAILED
2026-07-16 10:05:04 ERROR HttpClientErrorException: 401 Unauthorized on GET /api/accounts/transactions
2026-07-16 10:05:04 ERROR   at AccountPage.listTransactions(AccountPage.java:77)
2026-07-16 10:05:05 STEP Hareketi doğrula | SKIPPED"""

_WEB2_BROWSER_LOG = """2026-07-16 10:05:03 INFO [console] Fetching /api/accounts/transactions
2026-07-16 10:05:04 ERROR [console] GET /api/accounts/transactions 401 (Unauthorized)
2026-07-16 10:05:04 ERROR [console] Session token expired or invalid"""

_WEB2_DOM_HTML = """<html>
  <body>
    <div id="account-summary">
      <div class="error-banner">Oturum doğrulanamadı</div>
    </div>
  </body>
</html>"""


class MockSource(Source):
    """Returns a canned job with two failed web scenarios (out of 100)."""

    async def fetch_job(self, bank: str, job_id: str) -> JobData:
        if job_id.endswith(CLEAN_JOB_SUFFIX):
            return JobData(
                bank=bank,
                job_id=job_id,
                platform=Platform.WEB,
                total_scenario_count=100,
                failed_scenarios=[],
            )

        scenario_selector_broken = RawScenario(
            scenario_name="Login - geçerli kullanıcı ile giriş",
            platform=Platform.WEB,
            test_log=_WEB_TEST_LOG,
            browser_log=_WEB_BROWSER_LOG,
            dom_html=_WEB_DOM_HTML,
            screenshot_path="attachments/browser.default_1.png",
        )
        scenario_auth_failure = RawScenario(
            scenario_name="Hesap özeti - hareket listesi görüntüleme",
            platform=Platform.WEB,
            test_log=_WEB2_TEST_LOG,
            browser_log=_WEB2_BROWSER_LOG,
            dom_html=_WEB2_DOM_HTML,
            screenshot_path="attachments/browser.default_2.png",
            retry_info="1. koşum: FAILED, tekrar koşulmadı",
        )
        return JobData(
            bank=bank,
            job_id=job_id,
            platform=Platform.WEB,
            total_scenario_count=100,
            failed_scenarios=[scenario_selector_broken, scenario_auth_failure],
        )
