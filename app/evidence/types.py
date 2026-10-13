"""The evidence classes."""

from app.evidence.base import ScreenshotEvidence, TextEvidence


class TestLogEvidence(TextEvidence):
    """`test.log` — what the run printed as it went: build output, then steps."""

    evidence_name = "TestLogEvidence"
    device_id = "test"
    extension = ".log"
    description = (
        "Aşağıda koşum logu var: adımlar ve sonuçları, hata satırları, exception ve "
        "stack trace, servis çağrılarının istek/cevap dökümü."
    )


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
    description = (
        "Aşağıda tarayıcının konsol çıktısı var: ağ hataları (404, 401, 500) ve JS "
        "istisnaları burada görünür; hata anına en yakın satırlar en değerlidir."
    )


class BuildLogEvidence(TextEvidence):
    """Job-level build log — VisiumGo `/logs` -> `build.log`."""

    evidence_name = "BuildLogEvidence"
    device_id = "build"
    extension = ".log"
    #: Deliberately short: what this log IS depends on the profile (one
    #: scenario's slice, or the whole run), so the profile writes the sentence.
    description = "Aşağıda koşumun build log'u var."


class HtmlEvidence(TextEvidence):
    """`browser.default.html` — the page as it stood when the step failed."""

    evidence_name = "HtmlEvidence"
    device_id = "browser.default"
    extension = ".html"
    description = (
        "Aşağıda sayfanın HATA ANINDAKİ hâli var (kırpılmış DOM): aranan element "
        "gerçekten var mı, sayfa hangi ekranda kalmış, tıklamayı engelleyen bir "
        "yükleniyor/overlay katmanı var mı — buradan bakılır."
    )


class MobileDomEvidence(TextEvidence):
    """`mobile.{os}.{device}.xml` — the device's UI hierarchy."""

    evidence_name = "MobileDomEvidence"
    device_id = "mobile"
    extension = ".xml"
    description = (
        "Aşağıda cihazın HATA ANINDAKİ arayüz ağacı var: aranan element ağaçta "
        "gerçekten var mı, uygulama hangi ekranda kalmış, element var ama erişilebilir "
        "durumda değil mi — buradan bakılır."
    )


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
