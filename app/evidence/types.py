"""The evidence classes.

Each declares the `device_id` + file extension it matches — the same pair
VisiumGo's UI shows as the attachment's name (`browser.default.html`,
`test.properties`):

| device_id        | extension    | class                    |
|------------------|--------------|--------------------------|
| test             | .log         | TestLogEvidence          |
| test             | .properties  | TestPropertiesEvidence   |
| browser.default  | .log         | BrowserLogEvidence       |
| browser.default  | .html        | HtmlEvidence             |
| browser.default  | .png         | WebScreenshotEvidence    |
| mobile (prefix)  | .xml         | MobileDomEvidence        |
| mobile (prefix)  | .png         | MobileScreenshotEvidence |
| build            | .log         | BuildLogEvidence         |

The mime type is deliberately NOT part of the identity: `test.log` and
`test.properties` are both `text/plain` on device `test`, so a mime-based
match cannot separate them.

The build log is job-level (one log for the whole run); the extractor injects
it as a synthetic `build` attachment so it flows through the same profile and
rule machinery as everything else (e.g. "keep only this scenario's section").

`=== HATA ===` is not an evidence class: it is the scenario's `error_text`
(an A6 field), assembled by the extractor.
"""

from app.domain.findings import (
    BLOCK_BROWSER,
    BLOCK_BUILD,
    BLOCK_DOM,
    BLOCK_MOBILE_DOM,
    BLOCK_STEPS,
    BLOCK_TEST_PROPERTIES,
)
from app.evidence.base import ScreenshotEvidence, TextEvidence


class TestLogEvidence(TextEvidence):
    """`test.log` — the time-ordered step-flow backbone → `=== ADIMLAR ===`."""

    evidence_name = "TestLogEvidence"
    device_id = "test"
    extension = ".log"
    block_label = BLOCK_STEPS


class TestPropertiesEvidence(TextEvidence):
    """`test.properties` — run properties (device UDID, failedStep.*, retry).

    Stored, not prompted: no profile lists it today. It is its own class rather
    than part of `TestLogEvidence` because it is a different file with a
    different shape — merging them put properties text into the step-flow block.
    """

    evidence_name = "TestPropertiesEvidence"
    device_id = "test"
    extension = ".properties"
    block_label = BLOCK_TEST_PROPERTIES


class BrowserLogEvidence(TextEvidence):
    """`browser.default.log` — the browser log → `=== BROWSER LOG ===`."""

    evidence_name = "BrowserLogEvidence"
    device_id = "browser.default"
    extension = ".log"
    block_label = BLOCK_BROWSER


class BuildLogEvidence(TextEvidence):
    """Job-level build log — VisiumGo `/logs` -> `build.log` → `=== BUILD LOG ===`.

    Covers the whole run (every scenario), so a profile that sends it usually
    pairs it with a rule that keeps only the relevant part.
    """

    evidence_name = "BuildLogEvidence"
    device_id = "build"
    extension = ".log"
    block_label = BLOCK_BUILD


class HtmlEvidence(TextEvidence):
    """`browser.default.html` — the web page DOM → `=== DOM ===`."""

    evidence_name = "HtmlEvidence"
    device_id = "browser.default"
    extension = ".html"
    block_label = BLOCK_DOM


class MobileDomEvidence(TextEvidence):
    """`mobile.{os}.{device}.xml` — the mobile UI tree → `=== MOBIL DOM ===`.

    VisiumGo now ships the mobile UI hierarchy as its own attachment; it used
    to be readable only inside `test.log`. Its own block label (not `DOM`)
    keeps a hybrid run from producing two blocks with the same name.
    """

    evidence_name = "MobileDomEvidence"
    device_id = "mobile"
    extension = ".xml"
    block_label = BLOCK_MOBILE_DOM


class WebScreenshotEvidence(ScreenshotEvidence):
    """`browser.default.png` — stored reference only."""

    evidence_name = "WebScreenshotEvidence"
    device_id = "browser.default"
    extension = ".png"


class MobileScreenshotEvidence(ScreenshotEvidence):
    """`mobile.{os}.{device}.png` — stored reference only (path not used to route)."""

    evidence_name = "MobileScreenshotEvidence"
    device_id = "mobile"
    extension = ".png"
