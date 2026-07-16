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
