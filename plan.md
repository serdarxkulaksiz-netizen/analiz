# VisiumGo Test Analyzer — Yeniden Yazım Planı (plan.md)

> Bu dosya, projeyi MacBook'ta Claude Code ile **sıfırdan yazdırmak** için hazırlanmıştır.
> İki bölümden oluşur:
> - **BÖLÜM A — PROJE PLANI:** ne inşa edilecek (mimari, kararlar, sözleşmeler, şemalar).
> - **BÖLÜM B — CLAUDE CODE'A TALİMATLAR:** nasıl inşa edilecek (davranış kuralları, çalışma düzeni).
>
> Tüm kod isimleri **İngilizce**. LLM'in ürettiği açıklama metinleri (explanation, suggestion vb. alanların *içeriği*) **Türkçe**, alan *adları* İngilizce.

---

# BÖLÜM A — PROJE PLANI

## A0. Çatı İlkeleri (tüm projeye uygulanır)

1. **HARDCODED YOK.** Tablo isimleri, banka bilgileri, URL'ler, model adı, kırpma eşikleri,
   paralellik sayısı, confidence kovaları, prompt metni — hepsi config/şema/ayar katmanından
   gelir. Yalnızca değişmeyecek mimari sabitler kodda kalır. Amaç: yarın bir değeri değiştirmek
   = tek yerde değişiklik, kod dokunulmaz.
2. **TAK-ÇIKAR SINIRLAR.** Değişmesi muhtemel her şey (kaynak, LLM sağlayıcı, persistence,
   kuyruk) bir **arayüz (interface)** arkasında soyutlanır. Backend değişince üst kod değişmez.
3. **GÖZLEMLENEBİLİRLİK.** Her adımın izi diske düşer; hiçbir şey "sessizce" olmaz.
4. **TAŞINABİLİRLİK.** Kod MacBook'ta yazılır, GitHub'a atılır, Windows iş bilgisayarında
   çalışır. Platform-bağımlı hiçbir varsayım olmaz (yol ayraçları, satır sonları, ortam).
5. **PROJE BOYUTUNA ORANLI.** Bu bir POC. Global yazılım standartları ve LLM best-practice'leri
   uygulanır ama **abartılmaz** (gereksiz mikroservis, event-sourcing, aşırı katman yok).

## A1. Amaç

Başarısız otomasyon test koşumlarını (web/Selenium + mobil/Android; ileride iOS) toplayıp,
ham kanıtı (test.log, DOM/HTML, browser.log, ekran görüntüsü, Jenkins console.log) bir lokal
LLM'e yorumlatan FastAPI backend. Hedef: QA analistinin elle log inceleme işini
otomatikleştirmek; "neden patladı, **test hatası mı uygulama hatası mı**, ne yapılmalı"
sorusuna **güven seviyeli, gerekçeli ön teşhis** üretmek (kesin hüküm değil).

Banka ortamı: veri/kod dışarı çıkamaz, on-premise lokal LLM kullanılır.

## A2. Mimari Deseni — Google Auto-Diagnose (referans alınan yaklaşım)

Google'ın entegrasyon testi teşhis sistemi (Auto-Diagnose, ICSE 2026) ile aynı desen:

- **Agentless / tek-atış:** LLM'e araç çağırtma (tool-calling) YOK. Tüm ham kanıt tek prompt'ta
  verilir, tek çağrıda cevap alınır. (Lokal model qwen sınıfı; araştırmalar küçük/orta
  modellerde agentic döngülerin faydadan çok zarar getirebildiğini gösteriyor.)
- **Parse-minimal:** Alan-çıkaran, bileşene-özel parser YAZILMAZ (önceki projenin battığı yer
  buydu). Ham loglar timestamp'e göre birleştirilip **etiketli bloklar** halinde verilir; anlamı
  LLM çıkarır. Kod yalnızca **kaba boyut yönetimi** (dilimleme) yapar, alan ayıklama değil.
- **Katı prompt:** Adım-adım akıl yürütme + sert negatif kısıtlar ("kanıtta olmayanı uydurma,
  emin değilsen söyle") + zorunlu JSON çıktı + kanıt gösterimi (hangi log satırlarına dayandı).

## A3. Zincir Mimarisi (6 halka — tak-çıkar)

Platform değişimi (web→mobil→iOS) yalnızca Halka 1-2'yi etkiler; üst halkalar sabit kalır.

1. **Source (Halka 1):** Veriyi VisiumGo API'den (ve ileride Jenkins log API'sinden) çeker.
   Ortama/bankaya bağlı. → *Gerçek gerçekleme iş bilgisayarında; MacBook'ta stub/mock.*
2. **Extraction (Halka 2):** Ham kanıt → **Findings** (etiketli bloklar + minimal alanlar).
   Platform farkının yaşandığı halka. → *Gerçek parse iş bilgisayarında; MacBook'ta stub.*
3. **Prompt Building (Halka 3):** Findings → prompt. Platform-bağımsız.
4. **LLM Call (Halka 4):** Lokal LLM'e tek çağrı. Platform-bağımsız.
5. **Parsing (Halka 5):** LLM JSON cevabı → yapılandırılmış sonuç. Platform-bağımsız.
6. **Persist + API (Halka 6):** Repository arkasında kayıt + asenkron API. Platform-bağımsız.

**İki kilit sözleşme** (en başta sabitlenir, sonra değişmez):
- **Findings sözleşmesi** (Halka 2→3 arası)
- **JSON çıktı sözleşmesi** (Halka 5)

## A4. Girdi — "Veriyi Nasıl Alıyoruz"

Bitmiş bir job'ın sonuçları toplanır (job'ı biz koşturmayız). Bir job koşusu şunları üretir:

**Job seviyesi:**
- VisiumGo raporu (ör. "100 senaryodan 10'u hata aldı" + hangi senaryolar).
- Jenkins **console.log** — ayrı bir API'den alınır. *(Alma yöntemi henüz belirsiz; iş
  bilgisayarında çözülecek. Şimdilik sözleşmede yeri açık, stub.)*

**Her başarısız senaryo için (platforma göre değişir):**
- **web:** `test.log`, `browser.default.log`, **DOM (HTML)**, `browser.default.png`
- **mobile:** `test.log`, `png`
- (ileride **ios:** ayrı; sözleşme hazır olacak)

Attachment URL deseni (gözlemlendi):
`.../api/runs/{run_id}/attachments/{attachment_id}/browser.default_{n}.html`

**Flaky senaryolar:** VisiumGo, ilk koşumda patlayıp tekrar koşumda geçen senaryoları "flaky"
sayıp **başarılı** logunu döner. Bunlar analiz edilmez (analiz edilecek hata yok). *(İleride:
flaky senaryo listesi ayrı not olarak tutulabilir — v1'de zorunlu değil.)*

## A5. Hazırlama — Minimal (Halka 2)

- Loglar timestamp'e göre birleştirilir, **etiketli bloklar** halinde toplanır:
  `=== ADIMLAR ===`, `=== HATA (stack trace) ===`, `=== DOM ===`, `=== CONSOLE.LOG ===`.
- Alan-çıkaran parser YOK. Yalnızca **koşullu, önceliklendirilmiş boyut yönetimi**:
  - **Varsayılan: passthrough** (kesme yok). Kanıt sığıyorsa olduğu gibi gider.
  - Prompt gönderilmeden önce **token sayılır**. Model limitini aşarsa **otomatik kırpma**
    devreye girer (durup sormaz — asenkron akış korunur).
  - **Kesme önceliği:** patlayan adım + hata mesajı **asla kesilmez**; sırasıyla önce
    console.log gürültüsü, sonra DOM kesilir.
  - Kırpma olursa çıktıya **görünür bayrak** düşer: `truncated=true` + `truncated_note`.
  - Kırpma eşiği **config'ten** (`0` = passthrough başlangıç değeri). Gerçek limit iş
    bilgisayarında, gerçek model context penceresi öğrenilince ayarlanır.

## A6. Findings Sözleşmesi (Halka 2 → 3)

Platform-bağımsız, sabit yapı (alan adları İngilizce):

- `platform` — `web` | `mobile` | `ios`
- `scenario_name`
- `failed_step` — hangi adımda patladı
- `error_message` — asıl hata / stack trace (ham)
- `steps` — adım listesi + her birinin sonucu (PASSED/FAILED/SKIPPED)
- `ui_excerpt` — DOM/UI dökümünün ilgili kısmı (web'de dolu, mobilde boş olabilir).
  *(Not: `dom_excerpt` gibi web-kokan isim KULLANMA; `ui_excerpt` platform-bağımsız.)*
- `evidence_blocks` — etiketli ham bloklar (yukarıdaki `=== ... ===` formatı)
- `screenshot_path` — png'nin diskteki yolu (LLM'e gitmez; kanıt referansı)
- `retry_info` — varsa tekrar/deneme bilgisi

## A7. Prompt Sözleşmesi — "Nasıl İletiyoruz" (Halka 3)

Katı prompt, şu bileşenlerle:
- **Rol:** QA otomasyon analisti / SDET.
- **Görev:** kesin hüküm değil, gerekçeli ön teşhis (test mi / uygulama mı / ortam mı).
- **Platform bilgisi:** prompt'a "bu bir web/mobil testidir" bilgisi verilir (yorum bağlamı).
- **Organize kanıt:** job bağlamı (gerekirse) + failed_step + error_message + ui_excerpt +
  adımlar + console.log parçası — net başlıklarla.
- **Akıl yürütme:** adım adım düşün.
- **Negatif kısıtlar (sert):** kanıtta olmayanı uydurma; emin değilsen düşük confidence ver ve
  söyle; mutlak kesinlik nadirdir.
- **Zorunlu JSON çıktı:** A8'deki şema, birebir.
- **Dil:** açıklamalar Türkçe; teknik terimler İngilizce kalabilir.

## A8. Çıktı JSON Sözleşmesi (Halka 5) — flat, sabit şema

LLM'in döndüreceği ve sistemin kaydedeceği yapı (flat; iç içe obje yok):

- `scenario_name` (string)
- `platform` (string)
- `root_cause` (string, TR) — kök neden
- `error_type` (string) — LLM'in belirlediği hata tipi (kod değil, LLM üretir)
- `verdict` (string) — aksiyon kararı; şu değerlerden biri:
  - `test_maintenance` — testin kendisi bozuk/eskimiş; QA senaryoyu güncellemeli
  - `application_bug` — gerçek uygulama hatası; geliştiriciye
  - `environment_error` — ortam/altyapı/yetki (ör. 401); test de uygulama da suçsuz
  - `transient_error` — geçici/kararsız; genelde tekrar koşunca geçer
- `explanation` (string, TR) — açıklama
- `suggestion` (string, TR) — öneri / ne yapılmalı
- `confidence` (float) — yalnızca şu 5 kovadan biri: **0.1 / 0.25 / 0.5 / 0.75 / 0.99**
  (LLM ne döndürürse o; çeviri/map YOK. Uçlar bilinçli olarak "mutlak" değil.)
- `confidence_reason` (string, TR) — bu güven değerinin neden verildiği
- `summary` (string, TR) — kısa özet (tek-iki cümle)
- `most_relevant_log_lines` (list) — teşhisin dayandığı en ilgili log satırları (şeffaflık)
- `error_signature` (string) — hata tipinin kısa imzası (v1'de kullanılmaz; ileride aynı-hata
  gruplaması için hazır dursun)

**Sistem tarafı meta (LLM üretmez, kod ekler):**
- `truncated` (bool) + `truncated_note` (string)
- `screenshot_path` (string)
- `raw_llm_response` (string) — ham cevap (parse öncesi)
- `meta`: `llm_model`, `input_tokens`, `output_tokens`, `duration_ms`, `analyzed_at`

**Metin alanlarında default YOK:** LLM ne döndürürse o; dönmezse boş kalsın (uydurma default
"Analiz tamamlanamadı" vb. YAZMA).

## A9. LLM Çağrısı (Halka 4)

- Sağlayıcı: `LLMProvider` arayüzü arkasında. Gerçekleme: `OpenAICompatibleLLMProvider`
  (mevcut çalışan yapı) + `MockLLMProvider` (test/geliştirme).
- Endpoint passthrough (OpenAI-uyumlu `messages` gönder, `choices[0].message.content` al).
- `temperature = 0` (deterministik yanıt hedefi). Tüm çağrı parametreleri config'ten.
- Senaryo başına **tek çağrı**.
- **Hata dayanıklılığı:** LLM timeout verir / geçersiz JSON / çöp dönerse → o senaryo
  `analysis_failed` işaretlenir, ham cevabıyla kaydedilir, **job devam eder** (bir senaryo tüm
  koşuyu düşürmez).

## A10. Persistence — "DB Simülasyonu" Klasörü (Halka 6)

**İlk aşamada gerçek DB YOK.** `database/` klasörü bir veritabanını **simüle eder**:
- Klasör = veritabanı
- Alt klasörler = **tablolar**
- JSON dosyaları = **satırlar (rows)**

**Repository arayüzü** (kod yalnızca bunu tanır): `save()`, `get()`, `list()`, `exists()`.
Kod asla dosya yolu/tablo adı hardcode etmez; "şu tabloya kaydet / şu tablodan getir"
seviyesinde konuşur. Tablo isimleri ve şema config/şema katmanından gelir.

- **Bugünkü backend:** `FileRepository` → `database/{table}/{id}.json`.
- **İleride:** `SqliteRepository` / `OracleRepository` aynı arayüzü uygular; connection string
  verilir; **üst kod tek satır değişmez** (dependency injection ile enjekte edilir).

**Tablolar (başlangıç):**
- `runs` — her job koşusu (run_id, bank, platform, status, scenario_count, timestamps)
- `analysis_results` — her senaryonun teşhisi (**yarın Oracle'a taşınacak asıl tablo**)
- `evidence` — ham kanıt referansları (test.log/DOM/png yolları)
- `prompts` — LLM'e giden tam prompt + ham cevap (gözlem/debug)

**Tam iz (gözlemlenebilirlik):** Bir senaryo için ham kanıt + Findings + gönderilen prompt +
ham LLM cevabı + parse sonucu + meta — hepsi `database/` altında, insan tarafından açılıp
incelenebilir. `analysis_results` yarın Oracle'a giden olgunlaşmış kısım; diğerleri dosyada
kalabilir.

## A11. API — Asenkron

- **Başlat:** `POST /analyze/visiumgo` `{bank, job_id}` → ham veriyi kaydeder, arka planda
  analizi başlatır, **hemen** bir `analyzer_run_id` döner (bağlantı beklemez).
- **Sorgula:** `GET /analyze/visiumgo/{analyzer_run_id}` → durum (`pending`/`running`/`done`),
  kaç senaryodan kaçı bitti, biten teşhisler. Durum **diskten** okunur.
- Arka plan: FastAPI **BackgroundTasks**. Senaryolar **parametrik paralellikle** işlenir
  (`asyncio.Semaphore`, sayı config'ten). Her senaryo bittikçe diske yazılır.
- **Redis'e hazır iki sınır** (baştan konur, geçiş ucuz olsun):
  1. Analizi tetikleyen yer **tek fonksiyon çağrısı** olsun (kuyruk değişince sadece o satır).
  2. Durum/sonuç **diskten** okunsun, bellekteki değişkenden değil.
- **Önbellek (config ile açılıp-kapanır):** aynı run_id daha önce analiz edildiyse LLM'i tekrar
  çalıştırmayıp diskten dönebilir. Varsayılan davranış config'ten.
- **Hiç hata yoksa:** "analiz edilecek hata yok" deyip temiz döner.

## A12. Taşınabilirlik (Mac → GitHub → Windows sorunsuz)

- **Yollar:** her yerde `pathlib`; elle `/` veya `\` YOK.
- **Ortam:** URL/banka/model/`database/` yolu → `.env`'den. Windows'ta yalnızca `.env` doldurulur.
- **`.env.example`** dolu ve güncel; git'e girer. Gerçek `.env` git'e **girmez**.
- **Bağımlılıklar** net sürümlerle sabit (`pyproject.toml` / `requirements.txt`).
- **`.gitattributes`:** `* text=auto` (satır sonu LF/CRLF tuzağını önler).
- **`.gitignore`** baştan sağlam: `.venv/`, `__pycache__/`, `*.pyc`, `.env`, IDE dosyaları,
  `database/` **içeriği** (ama klasör yapısı `.gitkeep` ile korunur → Windows'ta boş gelir,
  ilk koşuda dolar).
- **Mock'larla ayakta:** proje, Halka 1-2 stub/mock iken bile `uvicorn` ile açılır ve uçtan uca
  çalışır (mock source + mock LLM). Windows'ta çekilince önce mock'la "çalışıyor mu" doğrulanır,
  sonra gerçek VisiumGo/LLM `.env`'den açılır.

## A13. İş Bilgisayarında Yapılacaklar (MacBook'ta YAPILAMAZ)

- Halka 1 (VisiumGo API) gerçek gerçeklemesi — gerçek ham JSON yapısı görülünce.
- Halka 2 (test.log/DOM parse) gerçek gerçeklemesi — gerçek örnekler görülünce.
- Jenkins console.log alma API'si.
- Lokal model **context penceresi** öğrenilecek → kırpma eşiği ayarlanacak.
- Gerçek prompt token ölçümü → kırpma gerekli mi belirlenecek.
- (İleride) job-seviyesi analiz (ayrı endpoint), png'nin multimodal modele verilmesi,
  Oracle'a geçiş, flaky liste raporu, aynı-hata gruplaması.

## A14. Kilitlenen Kararlar (özet)

1. confidence = float, 5 kova **0.1/0.25/0.5/0.75/0.99**; LLM ne dönerse o; +`confidence_reason`.
2. DB yok → `database/` = DB simülasyonu; repository arkasında; hardcoded değil; ileride
   SQLite/Oracle tak-çıkar.
3. Paralellik parametrik (config).
4. Global standart + LLM best-practice, proje boyutuna oranlı.
5. Çıktı = bu tek dosya (plan.md), MacBook'ta Claude Code'a verilecek.
6. Halka 1-2 iş bilgisayarında gerçeklenecek; MacBook'ta sözleşme + stub.
7. Girdi = katmanlı kanıt paketi; platforma göre değişken.
8. png sadece kanıt (`screenshot_path`); DOM LLM'e gider (koşullu kırpma).
9. Asenkron: başlat + sorgula; BackgroundTasks.
10. Redis'e hazır iki sınır: tek tetik fonksiyonu + durumu diskten oku.
11. Sonuç flat sabit şemalı JSON; repository arkasında.
12. `database/`'de tam iz, gözlemlenebilir.
13. Google Auto-Diagnose deseni: agentless, tek-atış, parse-minimal, katı prompt.
14. Mobil/web/ios ayrımı: `platform` alanı; kanıt seti platforma göre değişir.
15. Yeni alan `verdict` (test_maintenance/application_bug/environment_error/transient_error).
16. Tüm kod isimleri İngilizce; LLM açıklama içerikleri Türkçe.
17. HARDCODED YOK (çatı ilkesi).
18. Taşınabilir (Mac→Windows); mock'larla ayakta.
19. Ürün mimarisinde **LLM döngüsü (loop) YOK**. ("Loop" yalnızca Bölüm B'deki kod yazdırma
    yöntemidir — üründe değil.)

---

# BÖLÜM B — CLAUDE CODE'A TALİMATLAR

Aşağıdakiler, bu projeyi yazan Claude Code oturumu için **davranış kurallarıdır.**

## B1. Çalışma Düzeni — Kaldığı Yerden Devam (dış hafıza)

- Bu depoda iki dosya dış hafıza görevi görür: **`plan.md`** (bu dosya) ve **`CHANGELOG.md`**.
- **Her oturuma başlarken:** önce `plan.md` ve `CHANGELOG.md`'yi oku. Nerede kalındığını
  changelog'dan bul. **Bitmiş halkaları tekrar yazma.**
- **Her halka bitince:** `CHANGELOG.md`'ye ne yapıldığını kısaca yaz (hangi dosyalar, hangi
  kararlar, ne eksik kaldı). Böylece token biter / oturum kesilirse, sonraki oturum oradan
  devam eder — baştan başlamaz.
- Model/agent seviyesi sabit tutulmalı; oturum ortasında zayıf bir modele düşülmemeli (bu,
  kullanıcının Claude Code tarafındaki ayarıdır; kod bunu zorlamaz ama changelog sayesinde
  geçiş güvenli olur).

## B2. Yapım Sırası (halka halka)

1. **Sözleşmeleri çak:** Findings (A6) + JSON çıktı şeması (A8). Bunlar sabitlenmeden üstüne
   kod yazma.
2. **Domain katmanı:** enum'lar (verdict değerleri, platform), sonuç modeli (A8), config/şema.
3. **Halka 6 (Persistence):** `Repository` arayüzü + `FileRepository` (DB simülasyonu). Tablo
   isimleri config'ten. Tak-çıkar hazır.
4. **Halka 4 (LLM):** `LLMProvider` arayüzü + `OpenAICompatibleLLMProvider` + `MockLLMProvider`.
5. **Halka 5 (Parsing):** yalnızca `_try_json` (regex / Türkçe-section parse YOK).
6. **Halka 3 (Prompt):** A7'ye göre katı prompt kurucu.
7. **Halka 1 (Source):** `Source` arayüzü + `MockSource` (çalışır) + `VisiumGoSource` **stub**
   (iş bilgisayarında doldurulacak). BankRegistry + BankConnection.
8. **Halka 2 (Extraction):** `Extractor` arayüzü + `MockExtractor` (çalışır) + gerçek extractor
   **stub**. Kırpma fonksiyonu var ama varsayılan passthrough.
9. **API + arka plan:** asenkron başlat/sorgula, BackgroundTasks, parametrik semaphore.
10. **Testler:** her halka için sözleşme-bazlı testler; mock'larla uçtan uca "smoke" testi.
11. **Taşınabilirlik dosyaları:** `.env.example`, `.gitignore`, `.gitattributes`, `.gitkeep`,
    `pyproject.toml`/`requirements.txt`, `README` (Windows'ta çalıştırma adımları).

## B3. Sert Kurallar (geçmiş derslerden — İHLAL ETME)

1. **Yeni dosya/sınıf/servis YARATMA refleksi yok.** Önce mevcut yapıyı ara ve genişlet. Yeni
   bir orchestrator/servis gerekiyorsa **önce DUR ve onay iste.** (Geçmişte eski kodu
   genişletmek yerine ikinci bir orchestrator yazılmış ve tekrar/karmaşa doğmuştu.)
2. **İsim/imza kararlarını DEĞİŞTİRME.** `plan.md`'deki alan adları, endpoint adları, sözleşme
   alanları aynen kalır. (Geçmişte `/analyze` → `/analyze/visiumgo` gibi sapmalar olmuştu.)
3. **Kapsam dışına ÇIKMA.** Fark ettiğin başka sorunları kendi kafana göre düzeltme; sadece
   `CHANGELOG.md`'ye **liste halinde bildir.**
4. **HARDCODED YOK** (A0.1). Sabit değer görürsen config'e taşı.
5. **Belirsizlikte DUR ve SOR.** Emin olmadığın bir tasarım kararında kendi kafana göre karar
   verme; kullanıcıya sor. (Kullanıcı bunu özellikle istedi.)
6. **Parse-minimal.** Alan-çıkaran, bileşene-özel parser yazma. Ham kanıtı etiketli blok olarak
   ver; yorumu LLM yapar. Kod yalnızca kaba boyut yönetimi yapar.
7. **Agentless.** LLM'e tool-calling / iteratif döngü kurma. Tek prompt, tek çağrı.
8. **Taşınabilirlik.** `pathlib` kullan; platforma özel yol/komut varsayma. Proje mock'larla
   `uvicorn`'da ayağa kalkmalı.
9. **Metin alanlarında uydurma default YOK.** LLM boş dönerse alan boş kalır.

## B4. Bitmiş Sayılma Ölçütü (definition of done)

- Proje `.env.example` kopyalanıp `uvicorn` ile açıldığında **mock source + mock LLM** ile
  uçtan uca çalışır: `POST /analyze/visiumgo` → arka plan → `database/` altına tam iz yazılır →
  `GET .../{id}` sonucu döner.
- Gerçek VisiumGo/LLM yalnızca `.env` değiştirilerek açılır; kod değişmeden.
- Tüm sözleşme-bazlı testler geçer.
- Halka 1-2'nin gerçek gerçeklemesi **stub** olarak, iş bilgisayarında doldurulmak üzere net
  işaretlenmiş bırakılır (`# TODO(work-pc): ...`).
