"""The evidence classes."""

from app.evidence.base import ScreenshotEvidence, TextEvidence


class TestLogEvidence(TextEvidence):
    """`test.log` — what the run printed as it went: build output, then steps."""

    evidence_name = "TestLogEvidence"
    device_id = "test"
    extension = ".log"
    description = "koşum logu: build çıktısı, adımlar ve sonuçları"


class TestPropertiesEvidence(TextEvidence):
    """`test.properties` — run properties (device UDID, failedStep.*, retry)."""

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
    """Job-level build log — VisiumGo `/logs` -> `build.log`."""

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
    """`mobile.{os}.{device}.xml` — the device's UI hierarchy."""

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
