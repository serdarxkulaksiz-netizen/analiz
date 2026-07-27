# CHANGELOG — VisiumGo Test Analyzer

> Dış hafıza dosyası (plan.md B1). Her halka bitince buraya yazılır.
> Yeni oturum: önce `plan.md`, sonra bu dosya okunur; "Sıradaki adım"dan devam edilir.

## Oturum kararları (2026-07-16)
- Proje kökü: `/Users/serdarkulaksiz/Desktop/analiz` (kullanıcı onayı; **git init YOK**, depoyu kullanıcı kuracak).
- Yapım planı kullanıcı tarafından onaylandı (plan.md B2 sırası).

---

## [B2 Adım 1-2] Sözleşmeler + Domain katmanı — TAMAM (2026-07-16)

**Oluşturulan dosyalar:**
- `app/__init__.py`, `app/domain/__init__.py`
- `app/domain/enums.py` — `Platform` (web/mobile/ios), `Verdict` (4 değer, A8), `StepStatus` (PASSED/FAILED/SKIPPED), `RunStatus` (pending/running/done).
- `app/domain/findings.py` — `Findings` sözleşmesi (A6, alan adları birebir) + `Step`, `EvidenceBlock` + blok etiketi sabitleri (`ADIMLAR`, `HATA (stack trace)`, `DOM`, `CONSOLE.LOG` — A5).
- `app/domain/result.py` — `LLMAnalysis` (A8'in LLM alanları, birebir) + `AnalysisMeta` + `AnalysisResult` (saklanan satır: flat LLM alanları + sistem meta).
- `app/config.py` — tek config katmanı (pydantic-settings, `.env`); tablo adları, LLM parametreleri, kırpma eşiği (0=passthrough), paralellik, confidence kovaları, prompt şablon yolu hepsi burada.

**Uygulanan kararlar / notlar:**
- `evidence_blocks`: `list[EvidenceBlock{label, content}]` olarak modellendi (sıralı; kırpma önceliği ve prompt render sırası için). Alan adı A6'daki gibi `evidence_blocks`.
- `AnalysisResult`'a plan A8'de olmayan 3 sistem alanı eklendi (zorunluluk gereği, LLM alanı değil): `result_id`, `analyzer_run_id` (persistence anahtarları), `analysis_failed` (A9'un zorunlu kıldığı işaret).
- `analysis_failed` durumunda `scenario_name`/`platform` sistem tarafından Findings'ten doldurulur (kimlik bilgisi — uydurma analiz metni değil; B3.9 ihlali yok). Diğer LLM alanları boş kalır.
- `confidence` LLM'den ne dönerse o saklanır; kova doğrulaması/map YOK (A14.1).
- Token/karakter oranı (`token_chars_ratio=4`) kaba tahmin için config'e kondu (hardcoded olmasın diye).

**Sıradaki adım:** ~~B2 Adım 3~~ (tamamlandı, aşağıya bak).

---

## [B2 Adım 3] Halka 6 — Persistence — TAMAM (2026-07-16)

**Oluşturulan dosyalar:**
- `app/persistence/__init__.py`
- `app/persistence/repository.py` — `Repository` arayüzü: `save/get/list/exists` (A10, birebir).
- `app/persistence/file_repository.py` — `FileRepository`: `<root>/<table>/<id>.json`; UTF-8, insan-okunur indent; temp-dosya + `os.replace` ile atomik yazım (durum diskten poll edildiği için yarım satır okunmasın).

**Notlar:**
- Arayüz sync (POC boyutuna oranlı, A0.5); dosya I/O çok küçük. İleride SQLite/Oracle aynı imzayla takılır.
- Tablo adları hiçbir yerde hardcode değil; her çağrı `settings.table_*` üzerinden yapılacak.

**Sıradaki adım:** ~~B2 Adım 4~~ (tamamlandı, aşağıya bak).

---

## [B2 Adım 4-5] Halka 4 (LLM) + Halka 5 (Parsing) — TAMAM (2026-07-16)

**Oluşturulan dosyalar:**
- `app/llm/__init__.py`, `app/llm/provider.py` — `LLMProvider` arayüzü (`async complete(prompt) -> LLMResponse`), `LLMError`, `LLMResponse` (content + model + token sayıları + duration_ms).
- `app/llm/openai_compatible.py` — `OpenAICompatibleLLMProvider`: config'ten tam URL'e passthrough, `choices[0].message.content`; tüm parametreler constructor'dan (DI), hiçbiri hardcoded değil. Her tür hata `LLMError`'a sarılır.
- `app/llm/mock.py` — `MockLLMProvider`: deterministik, şema-geçerli Türkçe JSON döner. Prompt'taki `Senaryo:`/`Platform:` satırlarından kimliği geri yansıtır (yalnızca mock kolaylığı). Prompt'ta `401/Unauthorized` görürse `environment_error`, yoksa `test_maintenance` döner (mock çeşitliliği).
- `app/parsing/__init__.py`, `app/parsing/json_parser.py` — yalnızca `_try_json`: düz JSON → markdown fence → en dış `{...}` sırasıyla dener; obje değilse `None`. Regex / alan-parse YOK (B3.6).

**Notlar:**
- `LLM_API_URL` **tam** chat-completions URL'i olarak tutuluyor (endpoint yolu bile hardcode edilmedi).
- Mock'un içindeki Türkçe metinler ve `len//4` token tahmini mock fixture verisidir, ürün default'u değildir (B3.9 kapsamı dışı).

**Sıradaki adım:** ~~B2 Adım 6~~ (tamamlandı, aşağıya bak).

---

## [B2 Adım 6-8] Halka 3 (Prompt) + Halka 1 (Source) + Halka 2 (Extraction) — TAMAM (2026-07-16)

**Oluşturulan dosyalar:**
- `config/prompt_template.txt` — A7'ye göre katı prompt METNİ (rol, görev, platform, organize kanıt, adım-adım düşünme, sert negatif kısıtlar, zorunlu A8 JSON şeması, TR dil kuralı). Kodda prompt metni yok.
- `app/prompting/builder.py` — `PromptBuilder`: `string.Template` ile render (şablondaki JSON `{}`'leri bozulmasın diye `$placeholder`); confidence kovaları config'ten şablona akar. Şablon startup'ta yüklenir (fail-fast).
- `app/source/models.py` — `RawScenario` (ham kanıt paketi; platforma göre alanlar boş kalabilir) + `JobData` (`jenkins_console_log` sözleşme yeri açık, stub — A4).
- `app/source/base.py` — `Source` arayüzü (`async fetch_job(bank, job_id) -> JobData`).
- `app/source/banks.py` — `BankConnection` + `BankRegistry` (banka bilgisi `config/banks.json`'dan, yolu `.env`'den; hardcoded yok).
- `config/banks.json` — örnek `demo` bankası.
- `app/source/mock.py` — `MockSource`: 100 senaryoluk sahte job, 2 başarısız web senaryosu (selector kırık → test_maintenance kokusu; 401 → environment_error kokusu). `job_id` sonu `-clean` → hatasız job (temiz dönüş yolu test edilebilsin diye, mock kolaylığı).
- `app/source/visiumgo.py` — `VisiumGoSource` STUB, `# TODO(work-pc)` işaretli; `BankRegistry` enjekte, `NotImplementedError`.
- `app/extraction/base.py` — `Extractor` arayüzü (`extract(RawScenario) -> Findings`).
- `app/extraction/mock.py` — `MockExtractor`: yalnızca MockSource fixture formatını anlar (mock tesisatı; gerçek parse-minimal extractor değil).
- `app/extraction/visiumgo.py` — `VisiumGoExtractor` STUB, `# TODO(work-pc)` + A5 kuralları yorumda.
- `app/extraction/truncation.py` — `estimate_tokens` (oran config'ten) + `truncate_findings`: varsayılan passthrough (eşik 0); kesme önceliği CONSOLE.LOG (kuyruk korunur) → DOM (baş korunur) → ui_excerpt; HATA bloğu / failed_step / error_message ASLA kesilmez; kesinti notu döner.

**Kararlar:**
- MockLLMProvider'ın kimlik yansıtması şablondaki `Senaryo:` / `Platform:` satırlarına dayanır → şablonda bu iki satır sabit tutulmalı (mock bağımlılığı; gerçek LLM etkilenmez).
- Kırpmada CONSOLE.LOG'un kuyruğu, DOM'un başı korunur (en bilgilendirici kısımlar); not olarak kaydedilir.

**Sıradaki adım:** ~~B2 Adım 9~~ (tamamlandı, aşağıya bak).

---

## [B2 Adım 9] API + arka plan — TAMAM (2026-07-16)

**Oluşturulan dosyalar:**
- `app/service.py` — `AnalyzerService`: zincirin tamamı. `run_analysis(analyzer_run_id)` = TEK tetik fonksiyonu (Redis sınırı #1); durum/sonuç her zaman diskten okunur (Redis sınırı #2). Parametrik `asyncio.Semaphore`; senaryo başına tam iz: `evidence` → `prompts` (tam prompt + ham cevap) → `analysis_results`; aynı `result_id` üç tabloda ortak anahtar. LLM hatası/geçersiz JSON/ValidationError → `analysis_failed=true`, ham cevap saklanır, job devam eder (A9). Kırpma eşik>0 iken devreye girer (A5). Cache: aynı bank+job_id'nin tam analizli `done` koşusu varsa `cached_from` ile diskten döner. Hatasız job → `note="analiz edilecek hata yok"`.
- `app/main.py` — app factory (`create_app(settings)`) + DI kökü (`build_service`): source/extractor/LLM/repository seçimi tamamen config'ten. Endpoint'ler plan'daki adlarla birebir: `POST /analyze/visiumgo {bank, job_id}` → anında `analyzer_run_id`; `GET /analyze/visiumgo/{analyzer_run_id}` → durum + biten teşhisler.

**Kararlar / açık noktalar:**
- Plan A11 durumları yalnızca pending/running/done → job-seviyesi hata (source erişilemedi vb.) durumunda status=`done` + `note="job failed: ..."` yazılıyor. Ayrı bir `failed` durumu eklemek plan'daki durum listesini değiştirirdi (B3.2); **kullanıcıya sorulacak açık nokta** olarak buraya not edildi.
- `runs` tablosuna plan A10'daki alanlara ek olarak `job_id`, `completed_count`, `total_scenario_count`, `note`, `cached_from` kondu (A11'in sorgulama gereksinimleri için; alan adı değişikliği değil, ekleme).

**Sıradaki adım:** ~~B2 Adım 10-11~~ (tamamlandı, aşağıya bak).

---

## [B2 Adım 10-11] Testler + taşınabilirlik dosyaları — TAMAM (2026-07-16)

**Oluşturulan dosyalar:**
- `tests/conftest.py` — izole `Settings` fixture'ı (tmp `database/`, mock her şey, `_env_file=None`).
- `tests/test_contracts.py` — A6/A8 alan adları + enum değerleri donduruldu (sözleşme bekçisi).
- `tests/test_persistence.py` — Repository sözleşmesi (roundtrip, unicode insan-okunur, eksik satır, overwrite).
- `tests/test_parsing.py` — `_try_json`: düz/fence'li/düzyazılı JSON, çöp→None, obje-olmayan→None.
- `tests/test_prompt_builder.py` — kanıt + kısıtlar + kovalarda config değeri + doldurulmamış placeholder yok. (Mock LLM'in dayandığı `Senaryo:`/`Platform:` satırları da burada korunuyor.)
- `tests/test_llm_mock.py`, `tests/test_extraction_mock.py` — mock'lar sözleşmeye uygun; mobilde `ui_excerpt` boş (uydurma yok).
- `tests/test_truncation.py` — passthrough varsayılan; kesme önceliği CONSOLE→DOM→ui_excerpt; HATA/failed_step asla kesilmez; orijinal obje mutate edilmez.
- `tests/test_resilience.py` — çöp LLM / timeout → `analysis_failed=true`, ham cevap saklı, job `done`; source stub patlarsa run `done` + `note="job failed: ..."`.
- `tests/test_api_smoke.py` — B4 uçtan uca: POST→arka plan→`database/` tam iz→GET; temiz job; cache açık/kapalı; 404.
- `pyproject.toml` (bağımlılıklar + pytest ayarı), `requirements.txt` (== ile sabit sürümler), `.env.example`, `.gitignore` (`database/*` hariç `.gitkeep`), `.gitattributes` (`* text=auto`), `database/.gitkeep`, `README.md` (Mac + Windows adımları, mock→gerçek geçiş tablosu).

**Doğrulama (B4 ölçütü):**
- `pytest`: **36/36 geçti** (Python 3.13, fastapi 0.139.2, pydantic 2.13.4).
- Canlı: `cp .env.example .env` → `uvicorn app.main:app` → `POST /analyze/visiumgo {"bank":"demo","job_id":"job-42"}` anında id döndü → `GET` `done`, 2/2 senaryo, doğru verdict'ler → `database/runs|evidence|prompts|analysis_results` altına tam iz (prompt + ham cevap dahil) yazıldı. Doğrulama sonrası runtime `database/` içeriği temizlendi; `.env` yerinde bırakıldı (mock ayarlı).

**Düzeltilen hata:** MockLLM'in `401` ipucu, şablonun kendi kural metnindeki "ör. 401" yüzünden her prompt'ta tetikleniyordu → ipucu `"401 Unauthorized"` tam ifadesine daraltıldı.

**Açık noktalar / kullanıcıya sorulacaklar (B3.3 listesi):**
1. Job-seviyesi hata (source erişilemedi vb.): plan A11'de yalnızca pending/running/done var → şimdilik `status=done` + `note="job failed: ..."`. Ayrı bir `failed` durumu istenirse söyleyin.
2. Starlette, `httpx`'li TestClient için deprecation uyarısı veriyor (`httpx2` öneriyor) — davranışı etkilemiyor, ileride bağımlılık güncellemesinde ele alınabilir.
3. İş bilgisayarı işleri plan A13'te: `VisiumGoSource`, `VisiumGoExtractor`, Jenkins console.log API'si, gerçek context penceresine göre `TRUNCATION_THRESHOLD_TOKENS`.

**PROJE DURUMU: B2'nin 11 adımı da tamamlandı; B4 bitmiş sayılma ölçütü karşılandı.**

---

## [Kullanıcı kararları] Açık noktalar kapatıldı (2026-07-16)

Kullanıcı iki açık noktada kararı bana bıraktı; uygulanan:

1. **4. run durumu eklendi:** `RunStatus.FAILED = "failed"` (`app/domain/enums.py`). Job-seviyesi hata (ör. source erişilemedi) artık `status=failed` + `note="job failed: ..."` (`app/service.py`). Senaryo-seviyesi LLM hataları run'ı `failed` YAPMAZ — onlar satır bazında `analysis_failed` ile işaretlenir, run `done` biter (A9 korunuyor). Plan A11'in pending/running/done listesine kullanıcı onayıyla yapılmış ekleme.
2. **Starlette TestClient deprecation uyarısı:** bağımlılık değiştirilmedi (davranış etkilenmiyor); `pyproject.toml`'a hedefli `filterwarnings` eklendi (`starlette.exceptions.StarletteDeprecationWarning` — UserWarning alt sınıfı olduğu için tam sınıf yoluyla). Sonraki bağımlılık güncellemesinde `httpx2` önerisi tekrar değerlendirilecek.

Güncellenen testler: `tests/test_contracts.py` (durum kümesi 4 değer), `tests/test_resilience.py` (source hatası → `failed`).
Doğrulama: `pytest` → **36/36 geçti, 0 uyarı**.

**Sıradaki adım:** yok — sırada iş bilgisayarındaki gerçeklemeler (A13) veya kullanıcıdan gelecek yeni talimat var.

---
---

# [v2-uyum] plan.md v2'ye Uyum Düzeltmeleri (2026-07-22)

> `plan.md` **v2** ile değiştirildi (tek doğru kaynak). Mevcut kod v1'e göreydi; bu bölüm kodu
> v2'ye uydurma adımlarını kaydeder. Onaylı plan:
> `~/.claude/plans/users-serdarkulaksiz-downloads-plan-1-m-mossy-chipmunk.md`.
> **Onaylı kararlar:** (1) plan.md=v2 depoya yazıldı; (2) `RunStatus.FAILED` korunuyor;
> (3) MockLLM 401 dallanması kaldırılacak → tek sabit `MOCK_` teşhis; (4) `MOCK_` yalnız
> serbest-metne (enum/float hariç); (5) Docker yok = no-op.

## [v2 Adım 0] plan.md v2 depoya kondu — TAMAM (2026-07-22)
- **Dosyalar:** `plan.md` (v1 → v2 ile değiştirildi; `~/Downloads/plan_1.md`'den kopyalandı, 527 satır).
- **Karar:** Depodaki plan.md hâlâ v1'di; kullanıcı onayıyla v2 yazıldı (tek doğru kaynak).
- **Eksik/kapsam-dışı:** yok.
- **Sıradaki adım:** v2 Adım 1 — Domain/enums (`Platform` hybrid, `Verdict` 6 değer, `AnalysisStatus`).

## [v2 Adım 1] Domain / enums — TAMAM (2026-07-22)
- **Dosyalar:** `app/domain/enums.py`.
- **Karar:**
  - `Platform`: `IOS="ios"` → `HYBRID="hybrid"` (A4.2; hybrid = tek senaryoda web+mobil adım).
  - `Verdict`: 4 → 6 değer; `UNKNOWN="unknown"` + `INCONCLUSIVE="inconclusive"` eklendi (A10).
  - `RunStatus.FAILED` korundu; docstring "A13'e onaylı 4. değer" olarak güncellendi.
  - Yeni `AnalysisStatus(str, Enum)`: `OK="ok"` / `ANALYSIS_FAILED="analysis_failed"` (A10 sistem-meta `status`).
- **Eksik/kapsam-dışı:** `Platform.IOS` ve eski `Verdict` değerlerini kullanan yerler (findings,
  result, prompt, mock'lar, testler) sonraki adımlarda güncellenecek — şu an kod tutarsız (beklenen).
- **Sıradaki adım:** v2 Adım 2 — Findings sözleşmesi (`bank`, `missing_evidence`, `screenshot_paths`,
  `ui_excerpt` kaldır, blok etiketleri HATA/BROWSER LOG).

## [v2 Adım 2] Findings sözleşmesi (A6) — TAMAM (2026-07-22)
- **Dosyalar:** `app/domain/findings.py`.
- **Karar:**
  - Blok etiketleri: `BLOCK_ERROR "HATA (stack trace)"` → `"HATA"`; yeni `BLOCK_BROWSER="BROWSER LOG"`.
    Nihai set: ADIMLAR/HATA/DOM/BROWSER LOG/CONSOLE.LOG (BROWSER LOG=browser.default.log,
    CONSOLE.LOG=Jenkins console.log).
  - `Findings`: `bank` + `missing_evidence: list[str]` eklendi; `screenshot_path` →
    `screenshot_paths: list[str]`; `ui_excerpt` **kaldırıldı** (içerik `evidence_blocks`'ta, A6).
- **Eksik/kapsam-dışı:** `MockExtractor` hâlâ `ui_excerpt`/`screenshot_path` kullanıyor (Adım 6'da
  Evidence mimarisiyle düzeltilecek); prompt şablonu `$ui_excerpt` içeriyor (Adım 8).
- **Sıradaki adım:** v2 Adım 3 — Sonuç şeması (`LLMAnalysis`'ten platform çıkar; `AnalysisResult`:
  bank, screenshot_paths, missing_evidence, status).

## [v2 Adım 3] Sonuç şeması (A10) — TAMAM (2026-07-22)
- **Dosyalar:** `app/domain/result.py`.
- **Karar:**
  - `LLMAnalysis`'ten `platform` çıkarıldı (LLM üretmez; sistem ekler, A10).
  - `AnalysisResult`: `bank` + `missing_evidence: list[str]` eklendi; `screenshot_path` →
    `screenshot_paths: list[str]`; `analysis_failed: bool` → `status: AnalysisStatus` (ok/analysis_failed).
    `platform` sistem-meta bölümüne taşındı.
- **Eksik/kapsam-dışı:** `app/service.py` hâlâ `analysis_failed=`, `screenshot_path=`, `platform=`
  (LLMAnalysis'te) kullanıyor → Adım 10'da düzeltilecek (şu an import/attribute hatası verir, beklenen).
- **Sıradaki adım:** v2 Adım 4 — Config (evidence bayrakları, precheck_provider, registry anahtarları).

## [v2 Adım 4] Config (A0.2 / A5.2) — TAMAM (2026-07-22)
- **Dosyalar:** `app/config.py`.
- **Karar:**
  - `evidence_flags: dict[str, dict[str,bool]]` eklendi (A5.2); varsayılan `_DEFAULT_EVIDENCE_FLAGS`:
    png'ler `goes_to_llm=false`, diğerleri `true`; hepsi `goes_to_store=true`. Anahtar = evidence
    sınıf adı (registry anahtarıyla aynı).
  - `precheck_provider: str = "noop"` eklendi (A7).
  - Provider string'leri (`source/extractor/llm_provider`) artık "registry anahtarı" olarak
    yorumlanacak (Adım 9). Docstring plan atıfları v2'ye güncellendi (A10→A12, A7→A8 vb.).
  - `truncation_threshold_tokens`/`token_chars_ratio` korundu (A11 ölçüm birleşik metinde);
    kırpma Evidence content selector'ına delege edilecek (Adım 5/6).
- **Eksik/kapsam-dışı:** yok.
- **Sıradaki adım:** v2 Adım 5 — Evidence mimarisi (`app/evidence/`: base + 5 tip + registry).

## [v2 Adım 5] Evidence mimarisi (A5) — TAMAM (2026-07-22)
- **Kullanıcıya sorulan (B3.3) → yanıt:** test.log bölünmesi = **"ADIMLAR ham + HATA=error_message"**.
  TestLogEvidence ham test.log'u `=== ADIMLAR ===` bloklar; `=== HATA ===` bloğu extractor'ın
  minimal tanımladığı `error_message`'tan gelir. CONSOLE.LOG (Jenkins) 5 sınıfın dışında (A4.1
  job-seviyesi, A5.1 "yalnızca 5"), extractor job verisinden ekler.
- **Dosyalar (yeni):** `app/evidence/__init__.py`, `app/evidence/base.py` (`Evidence` ABC +
  `TextEvidence` + `ScreenshotEvidence`; `from_scenario` ile tip-dallanmasız kurulum, `to_block`,
  `select_content` passthrough A5.3, `is_present`/`is_missing` A5.4, config'ten `goes_to_llm`/
  `goes_to_store`), `app/evidence/types.py` (5 sınıf: TestLog→ADIMLAR, Html→DOM, BrowserLog→
  BROWSER LOG, Web/MobileScreenshot→path), `app/evidence/registry.py` (`EvidenceRegistry`:
  ad→sınıf + platform→beklenen set; `build_for(scenario)` eksikleri de örnekler; `if platform ==` YOK).
- **Dosyalar (değişen):** `app/source/models.py` — `RawScenario` v2 A4.3'e göre: `screenshot_path`
  (tek) → `web_screenshot_path` + `mobile_screenshot_path`; `dom_html`/`browser_log`/`test_log` korundu.
- **Karar:** platform→evidence-tipleri eşlemesi registry'de (mimari yapı, A4.2 "registry'ye satır");
  `goes_to_llm`/`goes_to_store` config'ten (A5.2). Ekstra global trimmer yok (A5.3) — kırpma
  evidence içi `select_content`'a delege (bugün passthrough).
- **Eksik/kapsam-dışı:** `MockExtractor`/`service`/`MockSource` hâlâ eski `RawScenario.screenshot_path`
  ve v1 Findings alanlarını kullanıyor → Adım 6/10'da düzeltilecek (şu an tutarsız, beklenen).
- **Sıradaki adım:** v2 Adım 6 — Extraction'ı Evidence üstüne kur; `truncation.py` sil; MockExtractor
  yeni Findings (bank/missing_evidence/screenshot_paths + HATA=error_message + CONSOLE.LOG).

## [v2 Adım 6] Extraction'ı Evidence üstüne kur — TAMAM (2026-07-22)
- **Dosyalar (silinen):** `app/extraction/truncation.py` (global trimmer, A5.3 yasak),
  `tests/test_truncation.py`.
- **Dosyalar (değişen):** `app/extraction/base.py` — `Extractor.extract` imzası: `extract(scenario, *,
  bank="", jenkins_console_log="") -> Findings` (job-seviyesi bağlam A4.1). `app/extraction/mock.py` —
  `MockExtractor(registry)`: EvidenceRegistry'den blok/screenshot/missing toplar; test.log'dan minimal
  steps/failed_step/error_message tanımlar; `=== HATA ===` = error_message; `=== CONSOLE.LOG ===` =
  jenkins_console_log; yeni Findings (bank, missing_evidence, screenshot_paths). `app/extraction/
  visiumgo.py` — stub `__init__(registry)` + yeni imza, `# TODO(work-pc)`.
- **Karar:** Onaylı test.log kararı uygulandı. Blok sırası: ADIMLAR/DOM/BROWSER LOG (registry) → HATA →
  CONSOLE.LOG (prompt'ta ayrı $failed_step/$error_message bölümleri de var, sıra kritik değil).
- **Eksik/kapsam-dışı:** `service.py` hâlâ `truncate_findings` import ediyor + `scenario.screenshot_path`
  + `analysis_failed=`; `main.py` extractor'a registry enjekte etmiyor → Adım 9/10'da düzeltilecek.
- **Sıradaki adım:** v2 Adım 7 — PreCheck kancası (`app/precheck/`: base + NoOpPreCheck).

## [v2 Adım 7] PreCheck kancası (A7) — TAMAM (2026-07-22)
- **Dosyalar (yeni):** `app/precheck/__init__.py`, `app/precheck/base.py` (`PreCheck.check(findings)
  -> LLMAnalysis | None`), `app/precheck/noop.py` (`NoOpPreCheck`: her zaman `None`).
- **Karar:** Hiçbir kural/known-issues/pattern DB YOK (A7, bilinçli). İleride yeni PreCheck
  gerçeklemesi registry'ye eklenir; üst kod değişmez.
- **Eksik/kapsam-dışı:** service henüz PreCheck çağırmıyor → Adım 10'da bağlanacak.
- **Sıradaki adım:** v2 Adım 8 — Prompt (şablon: ui_excerpt kaldır; bank/missing_evidence ekle;
  verdict 6; hybrid; blok etiketleri) + PromptBuilder.

## [v2 Adım 8] Prompt (A8) — TAMAM (2026-07-22)
- **Dosyalar:** `config/prompt_template.txt`, `app/prompting/builder.py`.
- **Karar:** Şablonda `$ui_excerpt` kaldırıldı; `$bank` + `$missing_evidence` (eksik kanıt bildirimi)
  eklendi; hybrid bağlam notu; verdict 4→6 (unknown/inconclusive açıklamalı); confidence 5-kova
  öğretimi (ara değer yok, 0.0/1.0 yok); JSON şemadan `platform` çıkarıldı; verdict enum 6 değer.
  `$scenario_name`/`$platform` satırları korundu. Builder `ui_excerpt` yerine `bank`+`missing_evidence`
  substitüsyonu yapıyor (missing boşsa "(eksik kanıt yok)").
- **Eksik/kapsam-dışı:** yok.
- **Sıradaki adım:** v2 Adım 9 — Registry+DI (`main.py`: if-zincirleri → registry; POST'a platform;
  platform akışı).

## [v2 Adım 9] Registry + DI, dallanmayı kaldır (A0.1) — TAMAM (2026-07-22)
- **Dosyalar:** `app/main.py` (yeniden yazıldı), `app/source/base.py`, `app/source/visiumgo.py`.
- **Karar:**
  - `_build_source/_extractor/_llm` içindeki `if provider == "..."` zincirleri **kaldırıldı** →
    `SOURCE_REGISTRY`/`EXTRACTOR_REGISTRY`/`LLM_REGISTRY`/`PRECHECK_REGISTRY` (ad→fabrika) + `_select`
    (bilinmeyen ad → net hata). Yeni varyant = registry'ye bir satır.
  - `MockExtractor`/`VisiumGoExtractor` fabrikaları `EvidenceRegistry(settings.evidence_flags)` enjekte ediyor.
  - `AnalyzeRequest`'e `platform: Platform` eklendi (A13 gövdesi; geçersiz platform → 422).
  - `Source.fetch_job` imzasına `platform: Platform` eklendi (A4.2 girdi); VisiumGoSource stub güncellendi.
  - `build_service` artık `precheck` de enjekte ediyor.
- **Eksik/kapsam-dışı:** `AnalyzerService.__init__` henüz `precheck` param'ı + `create_run(platform)` +
  `fetch_job(...platform)` + truncation kaldırımı yok → Adım 10'da. MockSource yeni imza + MOCK_ → Adım 10.5.
  (Şu an import zinciri service/mock'ta kırık, beklenen.)
- **Sıradaki adım:** v2 Adım 10 — Service (status/screenshot_paths/bank/missing_evidence, precheck,
  platform akışı, truncation import kaldır).

## [v2 Adım 10] Service (A9/A10/A13) — TAMAM (2026-07-22)
- **Dosyalar:** `app/service.py` (yeniden yazıldı).
- **Karar:**
  - `__init__`'e `precheck: PreCheck` eklendi; `create_run(bank, job_id, platform)`; run satırına
    platform yaratılışta yazılıyor; `_run_job` platformu run'dan okuyup `fetch_job(...,platform)`'a geçiriyor.
  - PreCheck çağrısı extraction'dan sonra, prompt'tan önce (A7): sonuç `None` değilse LLM atlanır,
    `meta.llm_model="precheck"`, prompt boş. (NoOp bugün hep None.)
  - Sonuç alanları v2: `analysis_failed` yerine `status` (OK/ANALYSIS_FAILED); `screenshot_path` →
    `screenshot_paths` (web+mobil dolu olanlar); `bank` + `missing_evidence` (Findings'ten) eklendi;
    `platform` sistem tarafından scenario'dan yazılıyor.
  - `truncate_findings`/`estimate_tokens` import ve mantığı **kaldırıldı** (global trimmer yok);
    A11 ölçüm/kırpma yorumu evidence content selector'a delege (bugün passthrough). `truncated`
    alanı Result default'unda False.
  - evidence trace satırı `screenshot_paths` listesi + raw_scenario dump.
- **Eksik/kapsam-dışı:** `MockSource.fetch_job` hâlâ eski imza + `screenshot_path` + MOCK_ yok →
  Adım 10.5. `MockLLMProvider` 401 dallanması + MOCK_ yok → Adım 10.5. Testler → Adım 11.
- **Sıradaki adım:** v2 Adım 10.5 — MockLLM (dallanma kaldır, tek MOCK_ teşhis) + MockSource
  (yeni imza, web/mobile/hybrid, MOCK_ etiketleme).

## [v2 Adım 10.5] MockLLM + MockSource (A14) — TAMAM (2026-07-22)
- **Dosyalar:** `app/llm/mock.py`, `app/source/mock.py` (ikisi de yeniden yazıldı).
- **Karar:**
  - `MockLLMProvider`: `if "401 Unauthorized"` dallanması **kaldırıldı** → tek sabit, şema-geçerli
    teşhis. Serbest-metin alanların hepsi `MOCK_` ön ekli. `scenario_name` prompt'tan yansıtılıyor
    (kaynak zaten `MOCK_` ürettiği için hizalı). **MOCK_ hariç tutulanlar:** `verdict` (enum geçerli
    kalmalı → `test_maintenance`), `confidence` (float → 0.75), `scenario_name` (kimlik yansıması).
  - `MockSource.fetch_job(bank, job_id, platform)`: yeni imza. **Platform dallanması YOK** (B3.4):
    her senaryo TÜM ham alanlarla dolu + istenen platformla etiketli; hangi kanıtın "beklendiğini"
    `EvidenceRegistry` platform→tip eşlemesi seçer. Senaryo adları + screenshot yolları `MOCK_` ön ekli.
    `-clean` job_id → hatasız job (veri koşulu, varyant anahtarı değil).
- **Eksik/kapsam-dışı:** Testler (`conftest`/8 test dosyası) hâlâ v1 alanlarına göre → Adım 11.
  `.env.example`/`README` v1 → Adım 12. `AnalyzeRequest` artık `platform` zorunlu → test POST gövdeleri
  güncellenecek.
- **Sıradaki adım:** v2 Adım 11 — Testler (verdict 6, platform hybrid, Findings/Result yeni alanlar,
  status, POST'ta platform, MOCK_; evidence registry + missing + NoOpPreCheck testleri; smoke).

## [v2 Adım 11] Testler — TAMAM (2026-07-22)
- **Dosyalar (değişen):** `tests/conftest.py` (+`precheck_provider`; `evidence_registry`/`mock_extractor`
  fixture'ları), `tests/test_contracts.py` (Findings/LLMAnalysis/AnalysisResult yeni alanlar, verdict 6,
  platform hybrid, AnalysisStatus), `tests/test_extraction_mock.py` (Evidence mimarisi; web/mobile/hybrid;
  missing toleransı; CONSOLE.LOG), `tests/test_llm_mock.py` (tek MOCK_ teşhis; dallanmasız; MOCK_ ön ekleri),
  `tests/test_prompt_builder.py` (bank/missing_evidence; HATA etiketi; 6 verdict), `tests/test_api_smoke.py`
  (POST'ta platform; status/screenshot_paths/MOCK_; platform zorunlu→422), `tests/test_resilience.py`
  (precheck+registry enjeksiyonu; create_run platform; status).
- **Dosyalar (yeni):** `tests/test_evidence.py` (platform→beklenen set; bayrak→blok; config override;
  eksik kanıt is_missing), `tests/test_precheck.py` (NoOp her zaman None).
- **Doğrulama:** `pytest` → **41/41 geçti** (Python 3.13). test_persistence/test_parsing değişmeden geçti.
- **Sıradaki adım:** v2 Adım 12 — Taşınabilirlik & docs (.env.example, README).

## [v2 Adım 12] Taşınabilirlik & docs — TAMAM (2026-07-22)
- **Dosyalar:** `.env.example` (plan atıfları v2; `PRECHECK_PROVIDER`; EVIDENCE_FLAGS JSON notu; kırpma
  Evidence-içi notu), `README.md` (platform web/mobile/hybrid; POST gövdesine platform; Evidence/PreCheck/
  dallanma-yok/MOCK_/Docker-yok bölümleri; A8→A10 atıf; geçiş tablosu güncel).
- **Docker:** Depoda Docker dosyası **yok** → item 8 no-op (eklenmedi).
- **Eksik/kapsam-dışı (B3.10):**
  1. `ruff`/`mypy` bu venv'de kurulu değil (v1 kurulumunda pyproject'e eklenmemiş) → plan doğrulama
     adım 1 çalıştırılamadı. `compileall` + 41 test + statik grep + canlı smoke ile telafi edildi.
     İstenirse dev bağımlılıklarına eklenebilir (kapsam dışı, sormadan yapmadım).
  2. `MOCK_` ön eki `verdict` (enum) / `confidence` (float) / `scenario_name` (kimlik yansıması)
     alanlarına uygulanmadı — geçerlilik/hiza için bilinçli (Adım 10.5).
- **Sıradaki adım:** yok — v2-uyum tamam (aşağıya bak).

---

## [v2-uyum SONUÇ] Tüm adımlar tamam — B4 karşılandı (2026-07-22)
- **Doğrulama özeti:**
  - `pytest` → **41/41 geçti, 0 uyarı**.
  - Statik grep: kodda gerçek `if mock`/`if platform ==`/`if type ==` **yok** (yalnız yorumlar);
    `ios`/`ui_excerpt`/`analysis_failed` kod izi **yok**.
  - `compileall` temiz.
  - Canlı smoke (3 platform, mock source+LLM): `POST {bank,job_id,platform}` → arka plan →
    `database/{runs,evidence,prompts,analysis_results}` tam iz → `GET` sonuç `done`. Platforma göre
    doğru screenshot (web→web png, mobile/hybrid→mobil png) registry ile seçildi (dallanma yok).
    Tüm mock çıktıları `MOCK_`; row status=ok; verdict=test_maintenance.
- **B4 ölçütü:** karşılandı (mock uçtan uca; gerçek yalnız `.env` ile; Halka 1-2 `# TODO(work-pc)` stub;
  dallanma yok; sözleşme testleri geçer).
- **İş bilgisayarı (A16) bekleyenler:** `VisiumGoSource`/`VisiumGoExtractor` gerçeklemesi, Jenkins
  console.log API'si, gerçek context penceresi → `TRUNCATION_THRESHOLD_TOKENS`, çoklu banka `banks.json`.

---
---

# [VisiumGo entegrasyonu] Halka 1-2 gerçek gerçekleme (2026-07-23)

> Kullanıcı gerçek VisiumGo API sözleşmesini verdi; Halka 1 (Source) + Halka 2 (Extraction/Evidence)
> stub'ları gerçeğe bağlanıyor. **Onaylı tasarım kararları (3× A):**
> A1 = attachment-tabanlı `RawScenario`; A2 = tek paylaşılan extractor (mock/visiumgo extractor
> ayrımı + `EXTRACTOR_PROVIDER` emekli); A3 = global `.env` (`VISIUMGO_BASE_URL`/`TOKEN`), `bank` etiket,
> `banks.json`/`BankRegistry` emekli.

## [VG Adım 1] Config + Domain + Evidence + tek Extractor — TAMAM (2026-07-23)
- **Dosyalar (değişen):**
  - `app/config.py` — `VISIUMGO_BASE_URL`/`VISIUMGO_TOKEN`/`VISIUMGO_TIMEOUT_SECONDS` eklendi;
    `extractor_provider` (A2) ve `banks_config_path` (A3) kaldırıldı.
  - `app/source/models.py` — attachment-tabanlı model: `Attachment{file_name, mime_type, device_id,
    content, stored_path}`, `RawScenario{scenario_name, platform, scenario_id, error_text,
    steps: list[Step], attachments, retry_info}`, `JobData`(+`run_id`, `job_name`, `run_result`,
    `raw_run_response`). Tipli test_log/dom_html/... alanları kaldırıldı.
  - `app/evidence/base.py` — `from_scenario` → `from_attachment`; her Evidence `mime_type`+`device_id`
    ile `matches()` (device_id tam ya da noktalı prefix → mobil tek sınıf).
  - `app/evidence/types.py` — 5 sınıfa `mime_type`/`device_id` eklendi (text/plain+test=TestLog,
    text/plain+browser.default=BrowserLog, text/html+browser.default=Html, image/png+browser.default=
    WebScreenshot, image/png+mobile=MobileScreenshot).
  - `app/evidence/registry.py` — attachment→sınıf eşleme (`_class_for`/`matches`); `build_for` artık
    attachment'lardan üretir; `expected_names`/`missing_names` platform beklenen setinden eksik hesaplar.
- **Dosyalar (yeni/silinen):** `app/extraction/evidence_extractor.py` (`EvidenceExtractor` — tek,
  kaynaktan bağımsız); `app/extraction/mock.py` + `app/extraction/visiumgo.py` **silindi**.
- **Karar:** HATA bloğu = `error_text`; CONSOLE.LOG = job-seviyesi jenkins; failed_step = FAILED adım;
  parse-minimal (alan-çıkaran parser yok).
- **Eksik/kapsam-dışı (sonraki adımlarda):** `VisiumGoClient`+`VisiumGoSource` yok; `MockSource`/
  `source/base.py` eski imza+model; `banks.py`/`banks.json` hâlâ duruyor (silinecek); `main.py`
  EXTRACTOR_REGISTRY+BankRegistry; `service` run_id; testler; .env.example/README. (Şu an kod tutarsız.)
- **Sıradaki adım:** VG Adım 2 — Source katmanı (`VisiumGoClient`, `VisiumGoSource`, `MockSource` yeni
  model, `source/base.py` imza +run_id, `banks.py`/`banks.json` sil).

## [VG Adım 2] Source katmanı — TAMAM (2026-07-23)
- **Dosyalar (yeni):** `app/source/visiumgo_client.py` (`VisiumGoClient`: Bearer header, timeout,
  `get_json/get_text/get_bytes`, `encode_segment` URL-encode; test için `transport` enjekte edilebilir).
- **Dosyalar (değişen):** `app/source/base.py` (`fetch_job(bank, job_id, platform, run_id="")`),
  `app/source/visiumgo.py` (gerçek: Adım A run_id çözümle [run_id öncelik / job_id→startTime max],
  B FAILED filtrele, C detay errorText+stepResults+attachments, D attachment indir+diske kaydet;
  hata→boş attachment=eksik; job devam), `app/source/mock.py` (yeni attachment modeli; platform→
  attachment dict lookup, `if platform` yok; hepsi `MOCK_`).
- **Dosyalar (silinen):** `app/source/banks.py`, `config/banks.json` (A3: BankRegistry emekli).
- **Karar:** İnen dosyalar `database/attachments/{run_id}/{file}` altına (pathlib, ad sanitize);
  ham run/detay response'ları JobData'da taşınıp service tarafından `runs`/`evidence`'a yazılacak (SRP:
  Source indirir, Service kalıcılaştırır).
- **Eksik/kapsam-dışı:** `main.py` hâlâ `BankRegistry`+`EXTRACTOR_REGISTRY` (kırık import); `service`
  run_id + fetch_job imzası + ham response persistı yok; conftest `banks_config_path`; testler. → VG Adım 3-4.
- **Sıradaki adım:** VG Adım 3 — `main.py` (registry'ler: tek extractor, VisiumGo client enjekte,
  AnalyzeRequest +run_id) + `service.py` (create_run run_id, fetch_job çağrısı, ham response persist).

## [VG Adım 3] API + Service — TAMAM (2026-07-23)
- **Dosyalar:** `app/main.py` (EXTRACTOR_REGISTRY kaldırıldı → tek `EvidenceExtractor(registry)`;
  `SOURCE_REGISTRY` visiumgo = `VisiumGoSource(VisiumGoClient(.env), database_dir/"attachments")`;
  BankRegistry kaldırıldı; `AnalyzeRequest`'e `job_id`/`run_id` opsiyonel + "en az biri" validator),
  `app/service.py` (`create_run(..., run_id="")` + run satırına run_id/job_name/run_result;
  `fetch_job(..., run_id)`; fetch sonrası çözülen run_id/job_name/run_result run'a yazılır;
  `_screenshot_paths` attachment'lardan üretir).
- **Sıradaki adım:** VG Adım 4 — testler.

## [VG Adım 4] Testler — TAMAM (2026-07-23)
- **Dosyalar:** `tests/conftest.py` (banks_config_path/extractor_provider kaldırıldı; `extractor`
  fixture=`EvidenceExtractor`), `tests/test_evidence.py` (attachment→sınıf eşleme, iki text/plain
  deviceId ile ayrım, mobil prefix, bayrak override, missing, bilinmeyen atlanır),
  `tests/test_extraction.py` (yeni; EvidenceExtractor RawScenario→Findings), `tests/test_resilience.py`
  (EvidenceExtractor; source hatası artık `FailingSource` ile — ağ yok), `tests/test_api_smoke.py`
  (mevcut, geçerli). `tests/test_extraction_mock.py` silindi.
- **Yeni:** `tests/test_visiumgo_source.py` — enjekte `httpx.MockTransport` ile Adım A-D: run çözümleme
  (startTime max), FAILED filtre, detay steps/errorText, attachment indir+diske kaydet, run_id önceliği,
  Bearer header + segment encode (%2F/%3A). **Dış servise bağımlılık yok.**
- **Bug düzeltildi:** `service._screenshot_paths` eski RawScenario alanlarına erişiyordu → senaryolar
  sessizce düşüyordu (gather return_exceptions); attachment tabanlıya çevrildi.
- **Sıradaki adım:** VG Adım 5 — .env.example + README.

## [VG Adım 5] Taşınabilirlik & docs — TAMAM (2026-07-23)
- **Dosyalar:** `.env.example` (`VISIUMGO_BASE_URL/TOKEN/TIMEOUT_SECONDS`; `BANKS_CONFIG_PATH` +
  `EXTRACTOR_PROVIDER` kaldırıldı), `README.md` (POST'a run_id notu; Halka 1-2 artık "gerçek";
  geçiş tablosunda VisiumGo satırı .env'e göre; extractor kaynaktan bağımsız).

---

## [VisiumGo entegrasyonu SONUÇ] Halka 1-2 gerçek — TAMAM (2026-07-23)
- **Doğrulama:** `pytest` → **47/47 geçti**; `compileall` temiz; statik grep → gerçek `if mock/
  platform==/type==` yok, ölü modül importu yok, eski RawScenario alanı yok. Canlı mock smoke (web/
  mobile/hybrid) → doğru screenshot registry ile seçildi, tam iz `database/`'e yazıldı. VisiumGo zinciri
  sahte HTTP transport ile testlerde uçtan uca doğrulandı.
- **Bitmiş ölçütü (real-spec Bölüm 7):** `.env`'e gerçek URL+token yazılıp `SOURCE_PROVIDER=visiumgo`
  seçilince gerçek zincir çalışır (kod değişmeden); `.env` boşken mock ile uçtan uca çalışır (`MOCK_`);
  token/URL hardcode yok; `if mock/platform/type` yok.
- **İş bilgisayarında kalan (A16):** gerçek `.env` (URL+token) ile canlı doğrulama; gerçek `stepResults`/
  attachment alan adları beklendiği gibi mi (stepLine/errorText/fileName/mimeType/deviceId) — sapma olursa
  yalnızca `VisiumGoSource` içinde alan adı ayarı; Jenkins console.log alımı (hâlâ açık); gerçek context
  penceresine göre `TRUNCATION_THRESHOLD_TOKENS`.
- **Kapsam dışı / not:** VisiumGo run **özet** endpoint'i (run_id doğrudan verildiğinde job_name/
  run_result) spec'te tanımlı olmadığından, run_id doğrudan verilince bu alanlar boş kalır (job_id ile
  gelince dolu). Gerekirse iş-pc'de tek satırla run-detay çağrısı eklenebilir.

## [Atık kod incelemesi] Push öncesi temizlik — TAMAM (2026-07-23)
Kullanıcı push öncesi atık/ölü kod incelemesi istedi; tek tek konuşuldu, kararlar:
- **`token_chars_ratio` SİLİNDİ** (`config.py` + `.env.example`): silinen global trimmer'ın
  `estimate_tokens` yardımcı değeriydi, yetim kalmıştı. "Neden iki kırpma düğmesi var?" tutarsızlığı giderildi.
- **`truncation_threshold_tokens` KALDI** (tek eşik, A11): "ileride Evidence-içi kırpma için ayrılmış,
  bugün passthrough" yorumu eklendi.
- **`raw_run_response` artık `runs` satırına yazılıyor** (`service.py`): toplanıp çöpe gidiyordu; A12
  "tam iz" gereği kalıcılaştırıldı. `create_run` başlangıç satırına da eklendi.
- **`retry_info`**: karar = yalnızca kayıtta kalsın, prompt'a eklenmedi (değişiklik yok; ileride
  `transient_error` isabeti için tek satırla eklenebilir).
- **Küçük temizlik:** `tests/test_visiumgo_source.py` kullanılmayan `import json` silindi;
  `tests/test_extraction.py` çift `app.domain.findings` importu birleştirildi.
- **Ölü olmadığı için bırakılanlar:** `truncated`/`truncated_note` (A10, passthrough), `error_signature`
  (A8, ileri için ayrılmış), `jenkins_console_log` (bağlı ama Jenkins alımı A16'da — bilinçli boş plumbing).
- **Doğrulama:** `pytest` → 47/47; `compileall` temiz.
- **Genel yön (kullanıcı):** Bundan sonra `# TODO(work-pc)` işlerinin çoğu BURADA yapılacak; iş
  bilgisayarına çok az iş bırakılacak (Jenkins console.log, Evidence-içi kırpma vb. sırada).

---
---

# [LLM entegrasyonu] Halka 4 gerçek gerçekleme (2026-07-23)

> Kullanıcı gerçek LLM servis sözleşmesini + gerçek VisiumGo payload değerlerini verdi (Network +
> Swagger'dan doğrulanmış). **Onaylı karar:** mesaj biçimi = **tek user mesajı** (A; Halka 3'e dokunma).

## [LLM Adım 1] Config + Provider + Registry — TAMAM (2026-07-23)
- **Dosyalar:**
  - `app/config.py` — `llm_api_url` → `llm_base_url` + `llm_endpoint_path` (=/api/v1/extension/send);
    `llm_max_tokens: int = 8000` (artık her istekte); `llm_model = "qwen3-coder-next"` (yalnız meta,
    body'de gönderilmez); `llm_api_key` opsiyonel (auth yok, boş=header yok).
  - `app/llm/openai_compatible.py` — URL = base+path; header `accept: application/json`, Authorization
    **yalnız api_key doluysa** (bu serviste yok); body = `{messages(user), temperature, max_tokens}`,
    **model body'de YOK**; cevap `choices[0].message.content` (boş → `LLMError`); meta model/usage;
    test için `transport` enjekte edilebilir.
  - `app/main.py` — LLM_REGISTRY openai_compatible yeni argümanlar (base_url+endpoint_path).
- **Sıradaki adım:** LLM Adım 2 — VisiumGo alan düzeltmeleri + mock hizalama.

## [LLM Adım 2] VisiumGo alan düzeltmeleri + mock hizalama — TAMAM (2026-07-23)
- **Dosyalar:** `app/source/visiumgo.py` — gerçek payload teyidiyle iki düzeltme: adım adı `stepLine`
  (satır no) yerine **`line`** (asıl metin); `startTime` ISO **string** olduğundan `max(..., default="")`.
  `app/llm/mock.py` — mock `model` artık `MOCK_` önekli (`MOCK_qwen3-coder-next`, A14.2). `app/source/mock.py`
  — `JobData`'ya `job_name="MOCK_nightly-test"` + gerçek şekilli `run_result` (state/totalScenarios/
  failScenarios/passScenarios/unstableScenarios) + `raw_run_response` (hepsi MOCK_).
- **Sıradaki adım:** LLM Adım 3 — testler + docs.

## [LLM Adım 3] Testler + docs — TAMAM (2026-07-23)
- **Dosyalar (yeni):** `tests/test_openai_compatible.py` — enjekte `httpx.MockTransport`: doğru URL,
  Authorization header YOK, body'de model YOK, temperature/max_tokens gönderiliyor, content/usage/model
  parse, boş choices→LLMError, HTTP 500→LLMError, boş base_url→fail-fast, api_key varsa Bearer.
- **Dosyalar (değişen):** `tests/test_llm_mock.py` (model `MOCK_mock-model`), `tests/test_api_smoke.py`
  (`meta.llm_model == MOCK_{llm_model}`), `.env.example` (LLM_BASE_URL/ENDPOINT_PATH/MAX_TOKENS=8000/
  MODEL=qwen3-coder-next; LLM_API_URL kaldırıldı), `README.md` (geçiş tablosu).
- **Doğrulama:** `pytest` → **52/52**; `compileall` temiz; statik grep → eski LLM referansı yok,
  `if mock/type` yok. Canlı mock smoke: `run_result` gerçek şekilde, `meta.llm_model=MOCK_qwen3-coder-next`,
  tokenlar dolu.

---

## [LLM entegrasyonu SONUÇ] Halka 4 gerçek — TAMAM (2026-07-23)
- **Bitmiş ölçütü:** `.env`'de `LLM_BASE_URL`+`LLM_PROVIDER=openai_compatible` set edilince gerçek
  servise istek gider (auth yok, model body'de yok), `content`+meta alınır; mock seçiliyken uçtan uca
  `MOCK_` etiketli çalışır; URL/yol/temperature/max_tokens/model hardcode yok; `if mock/type` yok.
- **İleriye açık kapı (§7):** base_url+path ayrı olduğu için doğrudan-LLM sunucusuna geçiş tek config;
  gerekirse `DirectLLMProvider` registry'ye eklenir, üst katman değişmez (bugün ekstra sınıf yazılmadı).
- **İş bilgisayarında kalan:** gerçek `.env` (LLM_BASE_URL) ile canlı doğrulama; (opsiyonel) Jenkins
  console.log; gerçek context penceresine göre kırpma.

## [SSL doğrulama anahtarı] — TAMAM (2026-07-23)
- **Neden:** Banka iç ağında self-signed/iç-CA sertifikaları SSL doğrulamasını patlatabilir.
  `verify=False` KOD'a gömülmez (HARDCODED YOK + güvenlik) → config anahtarı, güvenli varsayılan (açık).
- **Dosyalar:** `app/config.py` (`visiumgo_verify_ssl: bool = True`, `llm_verify_ssl: bool = True`),
  `app/source/visiumgo_client.py` + `app/llm/openai_compatible.py` (`verify_ssl` parametresi; gerçek
  transport'ta `httpx.AsyncClient(verify=...)`, enjekte transport'ta yok sayılır), `app/main.py`
  (registry'lerde `verify_ssl=s.*_verify_ssl` enjekte), `.env.example` (`VISIUMGO_VERIFY_SSL=true`,
  `LLM_VERIFY_SSL=true` + iç ağ notu), `tests/test_openai_compatible.py` (monkeypatch ile verify=False'ın
  httpx client'a geçtiği doğrulanır, ağa çıkmadan).
- **Kullanım:** iş-pc'de gerekiyorsa `.env`'de `VISIUMGO_VERIFY_SSL=false` / `LLM_VERIFY_SSL=false`.
  Daha güvenli alternatif (ileride): iç CA bundle yolunu `verify`'a vermek — bugün eklenmedi (kapsam).
- **Doğrulama:** `pytest` → 53/53; `compileall` temiz.

---
---

# [LLM ham cevap + parse düzeltmesi] — TAMAM (2026-07-23)

> İki sorun: (1) `TypeError: string indices...` → `analysis_failed`; (2) parse patlayınca LLM'in ham
> cevabı kayboluyordu. Kök neden: ara katman (`/api/v1/extension/send`) zarfı **çift kodlanmış** JSON
> string döndürüyor → `response.json()` bir `str` veriyor → `data["choices"]` string'i index'liyor →
> TypeError → LLMError → ham kayıp. Onaylı plan uygulandı.

- **Dosyalar:**
  - `app/llm/provider.py` — `LLMResponse`'a `raw_response: str` (tam zarf) + `request: dict` (gönderilen
    tam istek) eklendi. `content` = teşhis JSON'u (parse için); `raw_response` = tam zarf (kayıt için).
  - `app/llm/openai_compatible.py` — `complete()`: HTTP cevabı gelir gelmez **parse'tan ÖNCE**
    `response.text` `raw_response`'a alınır. `_extract()`: `response.json()` `str` ise `json.loads` ile
    **çift kodlama açılır**, sonra `choices[0].message.content`. Parse/erişim patlarsa **LLMError
    FIRLATMAZ** → `content=""` + dolu `raw_response` döner (ham korunur). Yalnız **transport hatası**
    (timeout/bağlantı yok) LLMError. `raise_for_status` kaldırıldı (500 gövdesi de saklanır).
  - `app/service.py` — `raw_llm_response` = `response.raw_response` (zarf boşsa `content`'e düşer);
    teşhis parse'ı **`response.content`'ten**; `database/prompts` satırına **`request`** (tam istek)
    eklendi (mevcut `prompt` + `raw_response` yanına). Parse başarılı olsun olmasın tam iz.
  - `app/llm/mock.py` — Mock artık gerçek `chat.completion` zarfını taklit ediyor: `raw_response`=tam
    MOCK zarf (id/choices/message/usage), `request`=MOCK istek, `content`=teşhis. Ham-kaydetme akışı
    mock'ta da aynı (A14).
- **Testler:** `test_openai_compatible` — çift-kodlanmış string zarf **açılır**; 500/bozuk zarf
  **fırlatmaz, ham korunur**; transport hatası → LLMError; ilk testte `raw_response`+`request` doğrulanır.
  `test_api_smoke` — `raw_llm_response` tam zarf; `prompts` satırında `request.messages` + tam zarf.
- **Doğrulama:** `pytest` → **55/55**; canlı mock smoke: `prompts/{id}.json` = `prompt`+`request`
  (url/model/messages)+`raw_response`(tam zarf); `raw_llm_response` tam zarf; status=ok.
- **Kapsam dışı bulgu (bildirim, düzeltmedim):** Transport hatasında (hiç cevap yok) `prompts.request`
  boş kalır — kaydedilecek istek/zarf yok; istenirse ileride provider isteği exception'a iliştirebilir.

## [LLM cevabı ayrı klasör] — TAMAM (2026-07-23)
- **İstek:** LLM'in ham cevabını görebilmek için `database/` altına ayrı bir klasör.
- **Dosyalar:**
  - `app/config.py` — `table_llm_responses: str = "llm_responses"` (tablo adı config'ten, hardcode yok).
  - `.env.example` — `TABLE_LLM_RESPONSES=llm_responses`.
  - `app/service.py` — her senaryo için `database/llm_responses/{result_id}.json` yazılıyor:
    `request` (gönderilen tam istek) + `raw_response` (LLM'in döndürdüğü tam ham zarf) + `content`
    (çıkarılan mesaj içeriği, okunur) + `model`/`input_tokens`/`output_tokens`/`duration_ms`. Parse
    başarılı olsun olmasın yazılır → boş/kısmi cevap da görünür.
  - `tests/test_api_smoke.py` — yeni klasörde satır + `raw_response`/`content`/`model` doğrulanır.
- **Geri alınan:** Önceki turdaki geçici debug `print`'ler (`[LLM RAW]`) kaldırıldı; teşhis artık
  terminal yerine `database/llm_responses/` üzerinden yapılır.
- **Doğrulama:** `pytest` → 55/55; canlı smoke: `database/llm_responses/` yazıldı (raw zarf + content + meta).
- **Not:** Bu klasör, `raw_llm_response`'un boş göründüğü durumda LLM'in gerçekte ne döndürdüğünü
  (boş gövde mi, farklı yapı mı) diske kalıcı yazar — iş-pc'de o satırı açıp bakabilirsin.
