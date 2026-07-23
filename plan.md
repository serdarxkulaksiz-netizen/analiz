# VisiumGo Test Analyzer — Proje Planı (plan.md) — v2

> **Bu dosya tek doğru kaynaktır (single source of truth).** Önceki plan.md sürümünü tamamen
> değiştirir. Çelişki halinde bu dosya geçerlidir.
>
> İki bölüm:
> - **BÖLÜM A — PROJE PLANI:** ne inşa edilecek.
> - **BÖLÜM B — CLAUDE CODE'A TALİMATLAR:** nasıl inşa edilecek.
>
> Tüm kod/alan/değişken isimleri **İngilizce**. LLM'in ürettiği metin *içerikleri*
> (`explanation`, `suggestion`, `root_cause`, `summary`, `confidence_reason`) **Türkçe**;
> teknik terimler İngilizce kalabilir.

---

# BÖLÜM A — PROJE PLANI

## A0. Çatı İlkeleri (tüm projeye uygulanır)

### A0.1 — MERKEZİ İLKE: Kodda davranış dallanması YOK
`if mock:`, `if platform == "web":`, `if type == ...` gibi **davranış dallanmaları yasaktır.**
Her varyant **kendi sınıfıdır**, ortak bir **arayüzü (interface)** uygular, seçim bir
**registry/factory** ve **dependency injection** ile yapılır.
Yeni varyant eklemek = yeni sınıf + registry'ye bir satır. Eski kod dokunulmaz.
*(SOLID: Open/Closed + Dependency Inversion. Bu ilke mock, platform, evidence, precheck —
hepsine uygulanır.)*

### A0.2 — HARDCODED YOK
Tablo isimleri, URL'ler, banka bilgileri, model adı, paralellik sayısı, confidence kovaları,
kanıt bayrakları, kırpma eşikleri, prompt metni — hepsi **config / `.env` / şema katmanından**
gelir. Yalnızca değişmeyecek mimari sabitler kodda kalır.
Hedef: yarın bir değeri değiştirmek = tek yerde ayar, kod dokunulmaz.

### A0.3 — SOLID (her harfine)
- **S**RP: her sınıf tek sorumluluk (her kanıt kendi okunmasından/filtresinden sorumlu).
- **O**pen/Closed: genişlemeye açık, değiştirmeye kapalı (yeni platform/kanıt = yeni sınıf).
- **L**iskov: aynı arayüzü uygulayan sınıflar birbirinin yerine geçebilir (mock ↔ gerçek).
- **I**nterface Segregation: şişkin arayüz yok, dar ve amaca özel arayüzler.
- **D**ependency Inversion: üst katman somut sınıfa değil **arayüze** bağımlıdır.

### A0.4 — Gözlemlenebilirlik
Her adımın izi diske düşer (ham kanıt + Findings + gönderilen prompt + ham LLM cevabı +
parse sonucu + meta). Hiçbir şey sessizce olmaz.

### A0.5 — Taşınabilirlik
Kod MacBook'ta yazılır → GitHub → Windows iş bilgisayarında çalışır. Platform-bağımlı varsayım
yok. **Docker YOK** (iş bilgisayarında mevcut değil).

### A0.6 — Proje boyutuna oranlı
Bu bir POC. Global standartlar ve LLM best-practice'leri uygulanır ama **abartılmaz**
(mikroservis, event-sourcing, aşırı katman yok).

---

## A1. Amaç

Başarısız otomasyon test koşumlarını toplayıp, ham kanıtı (test.log, DOM/HTML, browser.log,
ekran görüntüsü, Jenkins console.log) bir **lokal LLM**'e yorumlatan FastAPI backend.

Hedef: QA analistinin elle log inceleme işini otomatikleştirmek; şu soruya **güven seviyeli,
gerekçeli ön teşhis** üretmek (kesin hüküm değil):
**"Neden patladı? Test hatası mı, uygulama hatası mı, ortam hatası mı? Ne yapılmalı?"**

Kısıt: Banka ortamı — veri/kod dışarı çıkamaz, on-premise lokal LLM kullanılır.

---

## A2. Mimari Deseni — Google Auto-Diagnose

Google'ın entegrasyon testi teşhis sistemi (Auto-Diagnose, ICSE 2026) ile aynı desen:

- **Agentless / tek-atış:** LLM'e tool-calling YOK, iteratif döngü YOK. Tüm ham kanıt tek
  prompt'ta verilir, **senaryo başına tek çağrı** yapılır.
  *(Gerekçe: lokal model qwen sınıfı; araştırmalar küçük/orta modellerde agentic döngülerin
  faydadan çok zarar getirebildiğini gösteriyor. Ayrıca mevcut LLM endpoint'i passthrough.)*
- **Parse-minimal:** Alan-çıkaran, bileşene-özel parser **YAZILMAZ**. Ham kanıt **etiketli
  bloklar** halinde verilir; anlamı LLM çıkarır. Kod yalnızca **kaba boyut yönetimi** yapar.
  *(Gerekçe: önceki projenin battığı yer buydu — uydurma parser'lar ve gereksiz katmanlar.)*
- **Katı prompt:** adım-adım akıl yürütme + sert negatif kısıtlar ("kanıtta olmayanı uydurma,
  emin değilsen söyle") + zorunlu JSON çıktı + kanıt gösterimi (hangi log satırlarına dayandı).

**ÜRÜNDE LLM DÖNGÜSÜ (LOOP) YOKTUR.** ("Loop" yalnızca Bölüm B'deki *kod yazdırma yöntemidir*.)

---

## A3. Zincir Mimarisi (tak-çıkar halkalar)

Platform değişimi yalnızca Halka 1–2'yi etkiler; üst halkalar sabit kalır.

```
Halka 1: Source        → veriyi çeker (VisiumGo API / ileride Jenkins log API)
Halka 2: Extraction    → ham kanıt → Evidence'lar → Findings
         PreCheck      → (boş kanca; bugün hep None döner)
Halka 3: Prompt Build  → Findings → prompt
Halka 4: LLM Call      → lokal LLM'e tek çağrı
Halka 5: Parsing       → LLM JSON cevabı → yapı
Halka 6: Persist + API → repository'ye kayıt + asenkron API
```

- **Halka 1–2:** ortama/platforma bağlı. Gerçek gerçekleme **iş bilgisayarında**;
  MacBook'ta mock + stub.
- **Halka 3–6:** platform-bağımsız, MacBook'ta tam yazılır.

**İki kilit sözleşme** (en başta sabitlenir, sonra değişmez): **Findings** (A6) ve
**JSON çıktı şeması** (A10).

---

## A4. Girdi — "Veriyi Nasıl Alıyoruz"

Bitmiş bir job'ın sonuçları toplanır. **Job'ı biz koşturmayız.**

### A4.1 Job seviyesi
- VisiumGo raporu (ör. "100 senaryodan 10'u hata aldı" + hangi senaryolar).
- Jenkins **console.log** — **ayrı bir API'den** alınır (VisiumGo'dan değil).
  → *Alma yöntemi henüz belirsiz; iş bilgisayarında çözülecek. Sözleşmede yeri açık, stub.*

### A4.2 Platform — **girdi olarak gelir, tahmin edilmez**
`platform` değerleri: **`web` | `mobile` | `hybrid`**

- **`hybrid`** = tek senaryo içinde hem web hem mobil adım olması.
  *(Örnek: internet bankacılığında işlem başlar → telefona push notification gelir →
  telefonda onaylanır → web'e dönülür. Bu **tek bir senaryodur**.)*
- Platform, **beklenen kanıt setini** belirler (registry üzerinden).
- Platform **dosya adlarından tahmin EDİLMEZ** (kırılgan olur: tarayıcı açılmazsa html yok,
  cihaza bağlanılamazsa png yok).
- İleride `mobile`'ı android/ios diye, ya da `web`'i başka bir eksende bölmek istenirse:
  **yeni sınıf + registry'ye satır** ile olur, üst yapı bozulmaz.

### A4.3 VisiumGo'dan gelen dosya tipleri (Evidence sınıflarının temeli)

| Dosya | Ne zaman gelir | `goes_to_llm` | `goes_to_store` |
|---|---|---|---|
| `test.log` | **her zaman** (web/mobile/hybrid). Zaman sıralı adım akışının omurgası. **Mobilde** hata anındaki UI ağacı ayrı dosya değildir, bazen **bu dosyanın içine** basılır. | ✅ | ✅ |
| `browser.default.html` | web adımları (sayfanın DOM'u). Tarayıcı açılmazsa **gelmeyebilir**. | ✅ | ✅ |
| `browser.default.log` | web adımları (tarayıcı logu) | ✅ | ✅ |
| `browser.default.png` | web adımları (ekran görüntüsü) | ❌ | ✅ |
| `mobile.{os}.{marka}.png` | mobile/hybrid adımları (ör. `mobile.android.samsung.png`; os=android/ios, marka değişken). Cihaza bağlanılamazsa **gelmeyebilir**. | ❌ | ✅ |

**Kritik notlar:**
- **Ayrı bir mobil XML/DOM dosyası YOKTUR.** Mobil UI ağacı `test.log` içinde gelir →
  ayrı Evidence sınıfı oluşturma; `TestLogEvidence` onu olduğu gibi taşır.
- Mobil png adı platform bilgisi içerir (`mobile.android...`) ama **akışı yönlendirmek için
  KULLANILMAZ**. Bilgi ileride android/ios ayrımı için oradadır.
- Platform bazlı tipik kombinasyonlar:
  - **web:** html + browser.log + png + test.log
  - **mobile:** test.log + mobil png
  - **hybrid:** web dosyaları (html + browser.log) + mobil png + test.log
- **Her kanıt gelmeyebilir.** Beklenen kanıt yoksa → **"eksik" işaretlenir**, akış devam eder,
  ve bu eksiklik teşhise yansır (LLM'e "beklenen X kanıtı yoktu" bilgisi verilir).
  *(Eksiklik başlı başına ipucudur: "web senaryosu ama html yok" → tarayıcı hiç açılamamış.)*
- **Kesin VisiumGo API/JSON şeması BİLİNMİYOR.** Source'un job'ı nasıl çektiği iş
  bilgisayarında netleşecek → `# TODO(work-pc):` ile stub bırakılır. Yukarıdaki dosya tipleri
  Evidence mimarisi için yeterlidir.

### A4.4 Flaky senaryolar
VisiumGo akışı: 100 senaryo koşar → 15 patlar → o 15 senaryo **tekrar koşar** → 10'u yine
patlar, 5'i geçer. Geçen 5'e **flaky** denir ve VisiumGo onların **başarılı** logunu döner.

→ **Flaky senaryolar analiz edilmez** (analiz edilecek hata yok). Analiz edilen: gerçekten
patlayan senaryolar.

---

## A5. Evidence (Kanıt) Mimarisi — her kanıt kendi sorumluluğunu taşır

**Bu, projenin esneklik omurgasıdır.**

### A5.1 Sınıflar (yalnızca bunlar)
`TestLogEvidence`, `HtmlEvidence`, `BrowserLogEvidence`, `WebScreenshotEvidence`,
`MobileScreenshotEvidence`

Her biri ortak **`Evidence` arayüzünü** uygular ve **registry'de kayıtlıdır.**

### A5.2 İki bağımsız bayrak (config'ten)
- **`goes_to_llm`** — bu kanıt LLM'e gider mi? *(bugün: png'ler `false`, diğerleri `true`)*
- **`goes_to_store`** — `database/` klasörüne yazılır mı? *(bugün: hepsi `true`, png dahil)*

→ "Bugün 3 kanıt gidiyor, yarın png'yi de gönder / browser.log'u gönderme" demek =
**tek config değişikliği.** Kod değişmez.

### A5.3 Content selector (kanıt-içi kırpma)
Her Evidence **kendi content selector'ını** taşır: o kanıttan neyin alınacağı.
- **Bugün: passthrough** — hiçbir şey kesilmez, içerik olduğu gibi geçer.
- İleride "browser.log'dan sadece şu kısmı al" / "Dinamik Banka html'inden script-style at"
  demek = **yalnızca o sınıfın selector'ını değiştir.** Diğer kanıtlar, üst kod, prompt
  etkilenmez. Selector kuralı **banka/platform bazında config'ten** okunabilir.
- **Ayrı/global bir "trimmer" katmanı YOKTUR.** Kırpma her Evidence'ın içindedir.

### A5.4 Eksik kanıt toleransı
Beklenen kanıt dosyası yoksa sistem **çökmez**: o Evidence "eksik" bayrağıyla döner, akış
devam eder, eksiklik prompt'a ve teşhise yansır.

---

## A6. Findings Sözleşmesi (Halka 2 → 3)

Platform-bağımsız, sabit yapı (alan adları İngilizce):

- `platform` — `web` | `mobile` | `hybrid`
- `bank`
- `scenario_name`
- `failed_step` — hangi adımda patladı
- `error_message` — asıl hata / stack trace (ham)
- `steps` — adım listesi + sonuçları (PASSED/FAILED/SKIPPED), **zaman sıralı**
- `evidence_blocks` — etiketli ham bloklar:
  `=== ADIMLAR ===`, `=== HATA ===`, `=== DOM ===`, `=== BROWSER LOG ===`, `=== CONSOLE.LOG ===`
- `missing_evidence` — beklenen ama gelmeyen kanıtların listesi
- `screenshot_paths` — png'lerin diskteki yolları (LLM'e gitmez; kanıt referansı)
- `retry_info` — varsa tekrar/deneme bilgisi

> **Not:** `dom_excerpt` gibi web-kokan isim KULLANMA. Kanıtlar `evidence_blocks` içinde
> etiketle taşınır; platform farkı isimde değil, hangi blokların dolu olduğunda yaşar.

---

## A7. PreCheck Kancası (boş — bugün hiçbir şey yapmaz)

Prompt kurulmadan önce çalışan bir **`PreCheck` arayüzü** tanımlanır:
girdi = senaryonun kanıtları; çıktı = `None` (normal LLM akışı devam eder) **veya** hazır sonuç
(LLM atlanır).

- **Bugün tek gerçekleme: `NoOpPreCheck` → her zaman `None` döner.**
- **Hiçbir kural, eşleşme listesi, known-issues tablosu, örüntü veritabanı OLUŞTURULMAZ.**
  Bu **bilinçli** bir karardır: eski projede kural birikmesi bakımı bozmuştu.
- İleride ihtiyaç doğarsa (ör. "Katılım mobilde 'uygulama açılmıyor' görürsen LLM'e gitme")
  yeni bir `PreCheck` gerçeklemesi yazılıp registry'ye eklenir; **üst kod değişmez.**

---

## A8. Prompt Sözleşmesi (Halka 3)

Katı prompt, şu bileşenlerle:
- **Rol:** QA otomasyon analisti / SDET.
- **Görev:** kesin hüküm değil, **gerekçeli ön teşhis** (test mi / uygulama mı / ortam mı).
- **Bağlam:** `bank` + `platform` bilgisi verilir (mobilde "element bulunamadı"nın sebebi
  webdekinden farklıdır — model bunu bilmeli). `hybrid` ise akışın web↔mobil geçişli olduğu
  açıkça söylenir.
- **Organize kanıt:** etiketli bloklar (`=== ADIMLAR ===`, `=== HATA ===`, `=== DOM ===` …),
  **zaman sıralı adım akışı** omurga olacak şekilde.
- **Eksik kanıt bildirimi:** "beklenen X kanıtı yoktu" açıkça yazılır.
- **Akıl yürütme:** adım adım düşün.
- **Sert negatif kısıtlar:** kanıtta olmayanı **uydurma**; emin değilsen **düşük confidence ver
  ve söyle**; sağlam sonuca varamıyorsan çıkarım yapma; **mutlak kesinlik nadirdir**.
- **Confidence öğretimi:** 5 kovanın anlamı + hangi durumda hangisi (A10).
- **Zorunlu JSON çıktı:** A10'daki şema, birebir, başka hiçbir metin olmadan.
- **Dil:** açıklamalar **Türkçe**; teknik terimler İngilizce kalabilir.
- Prompt metni **config/şablon dosyasından** gelir (hardcoded değil), versiyonlanabilir.

---

## A9. LLM Çağrısı (Halka 4)

- **`LLMProvider` arayüzü** arkasında. Gerçeklemeler:
  `OpenAICompatibleLLMProvider` (gerçek) ve `MockLLMProvider` (sahte).
- Endpoint passthrough (OpenAI-uyumlu: `messages` gönder, `choices[0].message.content` al).
- **`temperature = 0`** (deterministik hedef). Tüm çağrı parametreleri config'ten.
- **Senaryo başına tek çağrı.** Tool-calling yok, loop yok.
- **Paralellik parametrik:** `asyncio.Semaphore`, sayı **config'ten** (tek yerden değişir).
- **Hata dayanıklılığı:** timeout / geçersiz JSON / çöp cevap → o senaryo **`analysis_failed`**
  işaretlenir, **ham cevabıyla** kaydedilir, **job devam eder** (bir senaryo tüm koşuyu
  düşürmez).

---

## A10. Çıktı JSON Sözleşmesi (Halka 5) — flat, sabit şema

**LLM'in üreteceği alanlar:**

| Alan | Tip | Açıklama |
|---|---|---|
| `scenario_name` | string | senaryo adı |
| `root_cause` | string (TR) | kök neden |
| `error_type` | string | hata tipi — **LLM belirler** (kod tarafında regex kategorizasyon YOK) |
| `verdict` | enum | aksiyon kararı — 6 değerden biri (aşağıda) |
| `explanation` | string (TR) | açıklama |
| `suggestion` | string (TR) | ne yapılmalı |
| `confidence` | float | **yalnızca 5 kovadan biri** (aşağıda) |
| `confidence_reason` | string (TR) | bu güven değeri neden verildi |
| `summary` | string (TR) | 1–2 cümle özet |
| `most_relevant_log_lines` | list | teşhisin dayandığı en ilgili log satırları (şeffaflık) |
| `error_signature` | string | hata tipinin kısa imzası — **v1'de kullanılmaz**, ileride aynı-hata gruplaması için hazır dursun |

### `verdict` — 6 değer
- **`test_maintenance`** — testin kendisi bozuk/eskimiş (locator değişmiş, akış değişmiş);
  QA senaryoyu güncellemeli
- **`application_bug`** — gerçek uygulama hatası; geliştiriciye gitmeli
- **`environment_error`** — ortam/altyapı/yetki (ör. 401 Unauthorized); test de uygulama da
  suçsuz
- **`transient_error`** — geçici/kararsız; genelde tekrar koşunca geçer
- **`unknown`** — model hiçbir şey diyemedi / kanıt yok
- **`inconclusive`** — model baktı ama **tek bir karara varamadı**

### `confidence` — 5 kova
**`0.1` / `0.25` / `0.5` / `0.75` / `0.99`**

- LLM **ne döndürürse o yazılır** — çeviri/map/`_CONFIDENCE_MAP` **YOK**.
- Uçlar bilinçli olarak "mutlak" değil (`0.0` ve `1.0` yok): bir LLM ne mutlak emin olabilir,
  ne mutlak çaresiz. Bu sayede prompt'a "1.0 verme" gibi ekstra kural yazmaya gerek kalmaz.
- Ara değer (0.73 gibi) üretilmesi yasaktır; prompt bunu açıkça söyler.

### Sistem tarafı meta (LLM üretmez, kod ekler)
`platform`, `bank`, `truncated` (bool) + `truncated_note`, `screenshot_paths`,
`missing_evidence`, `raw_llm_response` (parse öncesi ham cevap),
`meta`: `llm_model`, `input_tokens`, `output_tokens`, `duration_ms`, `analyzed_at`,
`status` (`ok` | `analysis_failed`)

### Default kuralı
**Metin alanlarında uydurma default YOK.** LLM boş dönerse alan **boş kalır**
("Analiz tamamlanamadı" gibi sahte default YAZMA).

---

## A11. Boyut / Token Yönetimi

- Kanıtlar birleştirilip prompt kurulduktan **sonra token sayılır** (ölçüm **nihai birleşik
  metinde** yapılır — model limiti ona uygulanır).
- **Bugün her şey passthrough olduğu için kırpma devreye girmez.**
- İleride limit aşılırsa: **Evidence-seviyesinde** (content selector'lar üzerinden) kırpılır.
  **Öncelik: patlayan adım + hata mesajı ASLA kesilmez**; önce console.log gürültüsü, sonra
  DOM kesilir.
- Kırpma olursa çıktıya **görünür bayrak** düşer: `truncated=true` + `truncated_note`
  ("neyin kesildiği"). **Sessiz kayıp yasaktır.**
- Sistem kırpma gerektiğinde **durup sormaz** (asenkron akış korunur), ama **asla gizlemez**.
- Eşikler config'ten; başlangıç değeri **passthrough**.
- Gerçek model context penceresi **iş bilgisayarında** öğrenilip ayarlanacak.

---

## A12. Persistence — `database/` = DB Simülasyonu (Halka 6)

**İlk aşamada gerçek DB YOK.** `database/` klasörü bir veritabanını **simüle eder**:
- klasör = veritabanı
- alt klasörler = **tablolar**
- JSON dosyaları = **satırlar (rows)**

**`Repository` arayüzü** (kod yalnızca bunu tanır): `save()`, `get()`, `list()`, `exists()`.
Kod **asla** dosya yolu / tablo adı hardcode etmez; "şu tabloya kaydet / şu tablodan getir"
seviyesinde konuşur. Tablo isimleri ve şema **config/şema katmanından** gelir.

- **Bugünkü backend:** `FileRepository` → `database/{table}/{id}.json`
- **İleride:** `SqliteRepository` / `OracleRepository` **aynı arayüzü** uygular; DI ile enjekte
  edilir; **üst kod tek satır değişmez.**

### Tablolar (başlangıç)
- **`runs`** — her job koşusu (`analyzer_run_id`, bank, platform, job_id, status,
  scenario_count, timestamps)
- **`analysis_results`** — her senaryonun teşhisi → **yarın Oracle'a taşınacak asıl tablo**
- **`evidence`** — ham kanıt referansları (test.log/html/log/png yolları + eksik listesi)
- **`prompts`** — LLM'e giden **tam prompt** + **ham cevap** (gözlem/debug)

### Tam iz (gözlemlenebilirlik)
Bir senaryo için: ham kanıt + Findings + gönderilen prompt + ham LLM cevabı + parse sonucu +
meta — hepsi `database/` altında, **insan tarafından açılıp incelenebilir.**
*(Gerekçe: ihtiyaçlar zamanla değişecek; dosya editlemek tablo şeması değiştirmekten kat kat
kolaydır. Şema olgunlaşınca `analysis_results` DB'ye taşınır.)*

### Önbellek
Aynı run daha önce analiz edildiyse LLM'i tekrar çalıştırmayıp diskten dönebilir.
**Config ile açılıp kapanır**, varsayılan config'ten gelir.

---

## A13. API — Asenkron, iki endpoint

- **Başlat:** `POST /analyze/visiumgo` `{bank, job_id, platform}`
  → ham veriyi kaydeder, arka planda analizi başlatır, **hemen** `analyzer_run_id` döner.
  *(Format örneği: `20260611_114521_visiumgo_125188_b6924858`)*
- **Sorgula:** `GET /analyze/visiumgo/{analyzer_run_id}`
  → durum (`pending`/`running`/`done`), kaç senaryodan kaçı bitti, biten teşhisler.
  **Durum diskten okunur.**

- URL `visiumgo`'ya **sabit**. Kaynak parametreleştirme (`/analyze/{source}`) gerekirse
  ileride; bugün eklenmez. Ek endpoint (listeleme, detay, dosya erişimi, health) **bugün yok.**
- **Arka plan:** FastAPI **`BackgroundTasks`** (Docker/Redis yok). Senaryolar **parametrik
  paralellikle** işlenir; **her senaryo bittikçe diske yazılır.**
- **Redis'e hazır iki sınır** (baştan konur, geçiş ucuz olsun):
  1. Analizi tetikleyen yer **tek fonksiyon çağrısı** olsun (kuyruk değişince sadece o satır).
  2. Durum/sonuç **diskten** okunsun, bellekteki değişkenden değil.
- **Hiç hata yoksa:** "analiz edilecek hata yok" deyip temiz döner.

---

## A14. Mock Kuralları

1. **`if mock` / `is_mock` gibi dallanma YASAK** (A0.1). Mock, arayüzün **ayrı bir
   gerçeklemesidir**: `MockSource`, `MockExtractor`, `MockLLMProvider`.
   Hangi gerçeklemenin kullanılacağı **başlangıçta config/DI ile** belirlenir.
   → Soyut katmana mock verilirse mock, VisiumGo verilirse VisiumGo çalışır; **kod değişmez.**
2. **`MOCK_` etiketleme:** Mock gerçeklemelerin ürettiği/döndürdüğü **her değer ve default
   metin `MOCK_` ön ekiyle başlar** (ör. `root_cause = "MOCK_örnek kök neden"`,
   `summary = "MOCK_ bu sahte bir teşhistir"`, mock kayıt id'leri `MOCK_...`).
   → Gerçek sisteme bağlandığında mock verinin gerçek veriyle **karışmaması** için.
   Gerçek gerçeklemeler **asla** `MOCK_` yazmaz.

---

## A15. Taşınabilirlik (Mac → GitHub → Windows)

- **Yollar:** her yerde `pathlib`; elle `/` veya `\` **YOK**.
- **Ortam:** URL/banka/model/`database/` yolu → **`.env`'den**. Windows'ta yalnızca `.env`
  doldurulur, kod değişmez.
- **`.env.example`** dolu ve güncel, git'e girer. Gerçek `.env` git'e **girmez.**
- **Bağımlılıklar** net sürümlerle sabit (`pyproject.toml` / `requirements.txt`).
- **`.gitattributes`:** `* text=auto` (LF/CRLF satır sonu tuzağını önler).
- **`.gitignore`** baştan sağlam: `.venv/`, `__pycache__/`, `*.pyc`, `.env`, IDE dosyaları,
  `database/` **içeriği** — ama klasör yapısı **`.gitkeep`** ile korunur (Windows'ta boş gelir,
  ilk koşuda dolar).
- **Docker YOK.**
- **Mock'larla ayakta:** proje, Halka 1–2 mock/stub iken bile `uvicorn` ile açılır ve **uçtan
  uca çalışır.** Windows'ta önce mock'la doğrulanır, sonra gerçek VisiumGo/LLM `.env`'den
  açılır.

---

## A16. İş Bilgisayarında Yapılacaklar (MacBook'ta YAPILAMAZ)

- **Halka 1 (VisiumGo API)** gerçek gerçeklemesi — gerçek ham JSON şeması görülünce.
- **Halka 2 (Extraction)** gerçek gerçeklemesi — gerçek dosya içerikleri görülünce.
- **Jenkins console.log** alma API'si.
- **Lokal model context penceresi** öğrenilecek → kırpma eşiği ayarlanacak.
- **Gerçek prompt token ölçümü** → kırpma gerekli mi belirlenecek.
- İleride: job-seviyesi analiz (ayrı endpoint), png'nin multimodal modele verilmesi,
  Oracle'a geçiş, flaky liste raporu, aynı-hata gruplaması (`error_signature` üzerinden),
  `PreCheck` kurallarının doldurulması, `mobile` → android/ios ayrımı.

---

## A17. Kilitlenmiş Kararlar (özet)

1. **Merkezi ilke:** kodda `if mock` / `if platform` / `if type` dallanması **yok**;
   varyant = ayrı sınıf + arayüz + registry + DI.
2. **HARDCODED YOK** (config/`.env`/şema).
3. **SOLID** her harfine.
4. **Google Auto-Diagnose deseni:** agentless, tek-atış, parse-minimal, katı prompt.
   **Üründe LLM loop yok.**
5. **Platform:** `web` / `mobile` / `hybrid`; **girdi**, tahmin edilmez; eksik kanıt tolere
   edilir.
6. **Evidence mimarisi:** 5 sınıf, `goes_to_llm` + `goes_to_store` config'ten, her kanıtın
   kendi content selector'ı (bugün passthrough), ayrı global trimmer yok.
7. **Mobilde ayrı XML/DOM dosyası yok** (ağaç `test.log` içinde).
8. **Parsing:** yalnızca LLM JSON cevabını yapıya çevirme; alan-çıkaran parser **yok**.
9. **`verdict`:** 6 değer.
10. **`confidence`:** 5 kova `0.1/0.25/0.5/0.75/0.99`; LLM ne dönerse o; `confidence_reason`
    zorunlu.
11. **Persistence:** `database/` = DB simülasyonu (klasör=DB, alt klasör=tablo, JSON=satır),
    `Repository` arayüzü arkasında; ileride SQLite/Oracle tak-çıkar.
12. **Tam iz** gözlemlenebilir (kanıt + Findings + prompt + ham cevap + sonuç + meta).
13. **API:** iki endpoint, asenkron, `BackgroundTasks`, parametrik paralellik,
    Redis'e hazır iki sınır.
14. **PreCheck kancası** boş (`NoOpPreCheck`); kural listesi **oluşturulmaz.**
15. **Mock:** ayrı sınıf + DI; tüm mock çıktıları **`MOCK_`** ile başlar.
16. **Token:** birleşik metinde ölçülür; bugün passthrough; kırpılırsa `truncated` bayrağı.
17. **Docker yok.** Taşınabilirlik: `pathlib`, `.env`, `.gitattributes`, mock'larla ayakta.
18. Kod isimleri **İngilizce**, LLM metin içerikleri **Türkçe**.
19. **Flaky senaryolar analiz edilmez.**
20. **LLM hatası** → `analysis_failed`, ham cevap kaydedilir, **job devam eder.**

---

# BÖLÜM B — CLAUDE CODE'A TALİMATLAR

## B1. Çalışma Düzeni — Kaldığı Yerden Devam (dış hafıza)

- Dış hafıza dosyaları: **`plan.md`** (bu dosya) ve **`CHANGELOG.md`**.
- **Her oturuma başlarken:** `plan.md` + `CHANGELOG.md` oku, nerede kalındığını bul.
  **Bitmiş işi tekrar yazma.**
- **Her adım/halka bitince:** `CHANGELOG.md`'ye yaz — hangi dosyalar, hangi kararlar,
  ne eksik kaldı, **sıradaki adım ne.**
- Token biterse / oturum kesilirse: yeni oturumda changelog'daki "sıradaki adım"dan devam et.
  **Asla baştan başlama.**
- Tek hamlede "hepsini yaptım bitti" deme; **halka halka** ilerle.

## B2. Yapım / Düzeltme Sırası

1. **Sözleşmeleri çak:** Findings (A6) + JSON çıktı şeması (A10). Bunlar sabitlenmeden üstüne
   kod yazma.
2. **Domain katmanı:** enum'lar (`verdict` 6 değer, `platform` 3 değer), sonuç modeli,
   config/şema katmanı.
3. **Halka 6 — Persistence:** `Repository` arayüzü + `FileRepository` (DB simülasyonu;
   tablo isimleri config'ten).
4. **Halka 4 — LLM:** `LLMProvider` arayüzü + `OpenAICompatibleLLMProvider` +
   `MockLLMProvider` (`MOCK_` etiketli).
5. **Halka 5 — Parsing:** yalnızca `_try_json`. Regex / section-parse **yok**.
6. **Evidence katmanı (A5):** `Evidence` arayüzü + 5 sınıf + registry + `goes_to_llm` /
   `goes_to_store` + content selector (passthrough).
7. **Halka 3 — Prompt:** A8'e göre katı prompt kurucu (şablon config'ten).
8. **PreCheck (A7):** arayüz + `NoOpPreCheck` (her zaman `None`). Kural listesi **yok**.
9. **Halka 1 — Source:** `Source` arayüzü + `MockSource` (çalışır) + `VisiumGoSource` **stub**
   (`# TODO(work-pc):`). BankRegistry / BankConnection.
10. **Halka 2 — Extraction:** `Extractor` arayüzü + `MockExtractor` (çalışır) + gerçek
    extractor **stub**.
11. **API + arka plan:** iki endpoint, asenkron, `BackgroundTasks`, parametrik `Semaphore`,
    her senaryo bittikçe diske yaz.
12. **Testler:** sözleşme-bazlı testler + mock'larla uçtan uca smoke testi.
13. **Taşınabilirlik dosyaları:** `.env.example`, `.gitignore`, `.gitattributes`, `.gitkeep`,
    `pyproject.toml`/`requirements.txt`, `README` (Windows'ta çalıştırma adımları).

## B3. Sert Kurallar — İHLAL ETME

1. **Yeni dosya/sınıf/servis/orchestrator yaratma refleksi YOK.** Önce mevcut yapıyı ara ve
   genişlet. Yeni bir servis/orchestrator gerektiğini düşünüyorsan **DUR ve SOR.**
2. **İsim / imza / endpoint kararlarını DEĞİŞTİRME.** `plan.md`'deki alan adları, endpoint
   yolları, enum değerleri **aynen** kalır.
3. **Belirsizlikte kendi kafana göre karar VERME — DUR ve SOR.**
4. **`if mock` / `if platform` / `if type` YAZMA** (A0.1).
5. **HARDCODED YAZMA** (A0.2). Sabit değer görürsen config'e taşı.
6. **Alan-çıkaran parser YAZMA** (parse-minimal, A2/A5).
7. **Tool-calling / agent loop KURMA** (agentless, A2).
8. **PreCheck'e kural / known-issues listesi EKLEME** (A7).
9. **Metin alanlarına uydurma default YAZMA** (A10).
10. **Kapsam dışına ÇIKMA.** Fark ettiğin başka sorunları kendi başına düzeltme;
    `CHANGELOG.md`'ye **liste halinde bildir.**
11. **Taşınabilirlik:** `pathlib` kullan; platforma özel yol/komut varsayma; Docker ekleme.
12. **Mock çıktılarına `MOCK_` ön eki koy** (A14).

## B4. Bitmiş Sayılma Ölçütü (definition of done)

- `.env.example` kopyalanıp `uvicorn` ile açıldığında **mock source + mock LLM** ile uçtan uca
  çalışır:
  `POST /analyze/visiumgo {bank, job_id, platform}` → arka plan → `database/` altına **tam iz**
  yazılır → `GET /analyze/visiumgo/{analyzer_run_id}` sonucu döner.
- Mock çıktılarının hepsi **`MOCK_`** ile başlar.
- Gerçek VisiumGo/LLM **yalnızca `.env` değiştirilerek** açılır; kod değişmeden.
- Kodda **hiçbir** `if mock` / `if platform ==` / `if type ==` dallanması **yoktur.**
- Halka 1–2'nin gerçek gerçeklemesi `# TODO(work-pc): ...` ile net işaretli **stub**.
- Sözleşme-bazlı testler geçer.
