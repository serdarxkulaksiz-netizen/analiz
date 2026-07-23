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
