"""The five evidence classes (plan.md A5.1 — only these).

Each declares the `mime_type` + `device_id` it matches (plan.md real spec):

| mime_type  | device_id        | class                    |
|------------|------------------|--------------------------|
| text/plain | test             | TestLogEvidence          |
| text/plain | browser.default  | BrowserLogEvidence       |
| text/plain | build            | BuildLogEvidence       |
| text/html  | browser.default  | HtmlEvidence             |
| image/png  | browser.default  | WebScreenshotEvidence    |
| image/png  | mobile (prefix)  | MobileScreenshotEvidence |

There is NO separate mobile XML/DOM evidence: the mobile UI tree arrives inside
`test.log`, carried as-is by `TestLogEvidence` (plan.md A4.3).

The build log is job-level (one log for the whole run); the extractor injects
it as a synthetic `build` attachment so it flows through the same profile and
rule machinery as everything else (e.g. "keep only this scenario's section").

`=== HATA ===` is not an evidence class: it is the scenario's `error_text`
(an A6 field), assembled by the extractor.
"""

from app.domain.findings import BLOCK_BROWSER, BLOCK_BUILD, BLOCK_DOM, BLOCK_STEPS
from app.evidence.base import ScreenshotEvidence, TextEvidence


class TestLogEvidence(TextEvidence):
    """`test.log` — the time-ordered step-flow backbone → `=== ADIMLAR ===`."""

    evidence_name = "TestLogEvidence"
    mime_type = "text/plain"
    device_id = "test"
    block_label = BLOCK_STEPS


class BrowserLogEvidence(TextEvidence):
    """`browser.default.log` — the browser log → `=== BROWSER LOG ===`."""

    evidence_name = "BrowserLogEvidence"
    mime_type = "text/plain"
    device_id = "browser.default"
    block_label = BLOCK_BROWSER


class BuildLogEvidence(TextEvidence):
    """Job-level build log — VisiumGo `/logs` -> `build.log` → `=== BUILD LOG ===`.

    Covers the whole run (every scenario), so a profile that sends it usually
    pairs it with a rule that keeps only the relevant part.
    """

    evidence_name = "BuildLogEvidence"
    mime_type = "text/plain"
    device_id = "build"
    block_label = BLOCK_BUILD


class HtmlEvidence(TextEvidence):
    """`browser.default.html` — the page DOM → `=== DOM ===`."""

    evidence_name = "HtmlEvidence"
    mime_type = "text/html"
    device_id = "browser.default"
    block_label = BLOCK_DOM


class WebScreenshotEvidence(ScreenshotEvidence):
    """`browser.default.png` — stored reference only."""

    evidence_name = "WebScreenshotEvidence"
    mime_type = "image/png"
    device_id = "browser.default"


class MobileScreenshotEvidence(ScreenshotEvidence):
    """`mobile.{os}.{brand}.png` — stored reference only (path not used to route)."""

    evidence_name = "MobileScreenshotEvidence"
    mime_type = "image/png"
    device_id = "mobile"
