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

The build log is job-level (one log for the whole run) and arrives from its
own endpoint, not from a scenario's `attachments[]`. `BuildLogEvidence` is
therefore built straight from that text, with the same profile flags and
content rules as every attachment-backed evidence (e.g. "keep only this
scenario's section").
"""

from app.evidence.base import ScreenshotEvidence, TextEvidence


class TestLogEvidence(TextEvidence):
    """`test.log` — what the run printed as it went: build output, then steps."""

    evidence_name = "TestLogEvidence"
    device_id = "test"
    extension = ".log"
    description = "koşum logu: build çıktısı, adımlar ve sonuçları"


class TestPropertiesEvidence(TextEvidence):
    """`test.properties` — run properties (device UDID, failedStep.*, retry).

    Stored, not prompted: no profile lists it today. It is its own class rather
    than part of `TestLogEvidence` because it is a different file with a
    different shape — merging them put properties text into the step-flow block.
    """

    evidence_name = "TestPropertiesEvidence"
    device_id = "test"
    extension = ".properties"
    description = "koşum özellikleri (cihaz, retry)"


class BrowserLogEvidence(TextEvidence):
    """`browser.default.log` — the browser's console output."""

    evidence_name = "BrowserLogEvidence"
    device_id = "browser.default"
    extension = ".log"
    description = "tarayıcı konsol logu"


class BuildLogEvidence(TextEvidence):
    """Job-level build log — VisiumGo `/logs` -> `build.log`.

    Covers the whole run (every scenario), so a profile that sends it usually
    pairs it with a rule that keeps only the relevant part.
    """

    evidence_name = "BuildLogEvidence"
    device_id = "build"
    extension = ".log"
    description = "job seviyesi build logu (tüm koşum)"


class HtmlEvidence(TextEvidence):
    """`browser.default.html` — the page as it stood when the step failed."""

    evidence_name = "HtmlEvidence"
    device_id = "browser.default"
    extension = ".html"
    description = "hata anındaki sayfa DOM'u"


class MobileDomEvidence(TextEvidence):
    """`mobile.{os}.{device}.xml` — the device's UI hierarchy.

    VisiumGo now ships the mobile UI hierarchy as its own attachment; it used
    to be readable only inside `test.log`. Its own block label (not `DOM`)
    keeps a hybrid run from producing two blocks with the same name.
    """

    evidence_name = "MobileDomEvidence"
    device_id = "mobile"
    extension = ".xml"
    description = "cihazdaki arayüz ağacı"


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
