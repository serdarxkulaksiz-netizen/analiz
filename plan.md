# VisiumGo Test Analyzer — Proje Planı (plan.md) — v3

> **Bu dosya tek doğru kaynaktır (single source of truth).** Çelişki halinde bu dosya geçerlidir.
>
> **v3 (2026-09-04):** Belge **inşa edilmiş sisteme göre** güncellendi. Kararların *gerekçeleri*
> korundu; değişen kararlarda hem yeni durum hem **neden değiştiği** yazılıdır. Başlıca farklar:
> `bank`+`platform` → `parameter1`/`parameter2` (A4.2) · Jenkins console.log → VisiumGo `/logs`
> ZIP'inden `build.log` (A4.1) · kanıt bayrakları → **analiz profilleri** (A5.2) · content
> selector → **9 kural tipi** (A5.3) · `missing_evidence` kaldırıldı → yer tutucu blok (A5.4) ·
> PreCheck artık boş değil (A7) · token eşiği kaldırıldı (A11) · `llm_responses` tablosu ve
> `run_id` bazlı önbellek (A12) · GET yalnız teşhis döner + config katılığı (A13).
> Adım adım geçmiş: [`CHANGELOG.md`](CHANGELOG.md).
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
Tablo isimleri, URL'ler, parametre/profil bilgileri, model adı, paralellik sayısı, confidence kovaları,
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
ekran görüntüsü, build.log) bir **lokal LLM**'e yorumlatan FastAPI backend.

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

Kaynak değişimi yalnızca Halka 1'i etkiler; üst halkalar sabit kalır.

```
Halka 1: Source        → veriyi çeker (VisiumGo API: run + results + detay + attachment + build log)
Halka 2: Extraction    → ham kanıt → Evidence'lar → Findings   (profil + içerik kuralları)
         PreCheck      → bilinen hataya config'ten hazır cevap; eşleşirse LLM ATLANIR
Halka 3: Prompt Build  → Findings → prompt
Halka 4: LLM Call      → lokal LLM'e tek çağrı
Halka 5: Parsing       → LLM JSON cevabı → yapı
Halka 6: Persist + API → repository'ye kayıt + asenkron API (GET yalnız teşhisi gösterir)
```

- **Hepsi yazıldı ve test edildi.** Mock↔gerçek geçişi yalnız `.env` ile olur; kod değişmez.
- Gerçek VisiumGo/LLM yalnız iş ağından erişilebilir → geliştirme mock'la yapılır.

**İki kilit sözleşme** (en başta sabitlenir, sonra değişmez): **Findings** (A6) ve
**JSON çıktı şeması** (A10).

---

## A4. Girdi — "Veriyi Nasıl Alıyoruz"

Bitmiş bir job'ın sonuçları toplanır. **Job'ı biz koşturmayız.**

### A4.1 Job seviyesi
- VisiumGo raporu (ör. "100 senaryodan 10'u hata aldı" + hangi senaryolar).
- **build log** — VisiumGo'nun kendi `GET {BASE}/api/runs/{run_id}/logs` ucundan alınır.
  Bu uç **düz metin değil ZIP** döndürür; içinden `build.log` çıkarılır
  (dosya adı `VISIUMGO_BUILD_LOG_ENTRY` ile ayarlanır). Ham ZIP saklanmaz.
  Log **her koşumda bütün olarak** çekilip `runs` satırına yazılır; LLM'e gitmesi ve
  senaryo bazında kesilmesi **profil kararıdır** (A5.2/A5.3).
  Kaynağı Jenkins'tir ama dosya adı `build.log` olduğu için isimlendirme buna göre yapılmıştır.

### A4.2 `parameter1` / `parameter2` — **girdi olarak gelir, tahmin edilmez**

Başlangıçtaki `bank` + `platform` alanları **kaldırıldı**; yerlerini iki serbest parametre aldı.
Sebep: sistem birçok farklı projeden veri alacak ve ayrım ekseni "banka" ya da "web/mobil"
olmak zorunda değil.

- **`parameter1`** — verilirse **analiz profilini doğrudan seçer** (`config/profiles.json`).
  Bilinmeyen bir profil adı verilirse koşum `failed` olur (sessizce yanlış profil kullanılmaz).
- **`parameter2`** — serbest metin; yalnızca **kaydedilir**, davranışı etkilemez.
- İkisi de verilmezse `"default"` olur; profil o zaman **`job_id`** ile bulunur.
- Hiçbir şey **dosya adlarından tahmin EDİLMEZ** (kırılgan olur: tarayıcı açılmazsa html yok,
  cihaza bağlanılamazsa png yok).

> Kanıt setini artık "platform" değil, **job'a bağlı profil** belirler (A5.2).

### A4.3 VisiumGo'dan gelen dosya tipleri (Evidence sınıflarının temeli)

| Dosya | Ne zaman gelir | `goes_to_llm` | `goes_to_store` |
|---|---|---|---|
| `test.log` | **her zaman** (web/mobile/hybrid). Zaman sıralı adım akışının omurgası. **Mobilde** hata anındaki UI ağacı ayrı dosya değildir, bazen **bu dosyanın içine** basılır. | ✅ | ✅ |
| `browser.default.html` | web adımları (sayfanın DOM'u). Tarayıcı açılmazsa **gelmeyebilir**. | ✅ | ✅ |
| `browser.default.log` | web adımları (tarayıcı logu) | ✅ | ✅ |
| `browser.default.png` | web adımları (ekran görüntüsü) | ❌ | ✅ |
| `mobile.{os}.{marka}.png` | mobile/hybrid adımları (ör. `mobile.android.samsung.png`; os=android/ios, marka değişken). Cihaza bağlanılamazsa **gelmeyebilir**. | ❌ | ✅ |
| `build.log` | **job seviyesi** (senaryo başına değil): VisiumGo `/logs` ZIP'inden çıkarılır. Tüm koşumu kapsar. Sentetik bir attachment (`device_id="build"`) olarak akışa girer, böylece profil+kural makinesi onu da yönetir. | ❌ *(profil açarsa ✅)* | ✅ |

**Kritik notlar:**
- **Ayrı bir mobil XML/DOM dosyası YOKTUR.** Mobil UI ağacı `test.log` içinde gelir →
  ayrı Evidence sınıfı oluşturma; `TestLogEvidence` onu olduğu gibi taşır.
- Mobil png adı platform bilgisi içerir (`mobile.android...`) ama **akışı yönlendirmek için
  KULLANILMAZ**. Bilgi ileride android/ios ayrımı için oradadır.
- Platform bazlı tipik kombinasyonlar:
  - **web:** html + browser.log + png + test.log
  - **mobile:** test.log + mobil png
  - **hybrid:** web dosyaları (html + browser.log) + mobil png + test.log
- **Her kanıt gelmeyebilir.** Profil bir kanıt istediği hâlde gelmediyse blok prompt'tan
  **düşmez**: başlığı kalır, içine `(bu kanıt alınamadı / bulunmuyor)` yazılır (A5.4).
- **VisiumGo API şeması artık biliniyor ve bağlandı.** Zincir: run çöz → `/results`'tan
  `resultType == "FAILED"` senaryolar → her senaryonun detayı → attachment'ları indir.
  Attachment → Evidence eşlemesi **`mimeType` + `deviceId`** ile yapılır (dosya adıyla değil).

### A4.4 Flaky senaryolar
VisiumGo akışı: 100 senaryo koşar → 15 patlar → o 15 senaryo **tekrar koşar** → 10'u yine
patlar, 5'i geçer. Geçen 5'e **flaky** denir ve VisiumGo onların **başarılı** logunu döner.

→ **Flaky senaryolar analiz edilmez** (analiz edilecek hata yok). Analiz edilen: gerçekten
patlayan senaryolar.

---

## A5. Evidence (Kanıt) Mimarisi — her kanıt kendi sorumluluğunu taşır

**Bu, projenin esneklik omurgasıdır.**

### A5.1 Sınıflar (yalnızca bunlar — 6 adet)
`TestLogEvidence`, `HtmlEvidence`, `BrowserLogEvidence`, `BuildLogEvidence`,
`WebScreenshotEvidence`, `MobileScreenshotEvidence`

Her biri ortak **`Evidence` arayüzünü** uygular ve **registry'de kayıtlıdır**. Eşleme anahtarı
`(mime_type, device_id)`. Yeni kanıt tipi = **1 sınıf + registry'ye 1 satır**.

### A5.2 İki bağımsız bayrak — **analiz profilinden** (`config/profiles.json`)

Bayraklar artık sınıf sabiti değil, **job bazlı profil** kararıdır:

- **`evidence_to_llm`** — hangi kanıtlar prompt'a girer.
- **`evidence_to_store`** — hangilerinin içeriği `database/` satırına gömülür.
  *(Dışarıda kalanın **metaverisi yine kalır** — dosya adı, tip, disk yolu — yalnız gömülü
  içerik düşer; indirilen dosyanın kendisi `database/attachments/` altında zaten durur.)*

**Profil seçimi:** `parameter1` bir profil adı verirse o kazanır → yoksa `job_ids` eşleşmesi →
yoksa `default`. Eksik `default` / yinelenen `job_id` / bozuk kural → **açılışta** hata.

→ "Bu job'da yalnız build log gitsin", "şu job'da png de gitsin" demek =
**config'e bir satır.** Kod değişmez.

### A5.3 Content selector — **içerik kuralları** (`RULE_REGISTRY`)
Her Evidence kendi content selector'ını taşır; kurallar **profilden** gelir ve sırayla uygulanır.

**9 kural tipi:** `keep_scenario_section` (job-seviyesi logu senaryo bazında dilimler) ·
`keep_first_lines` / `keep_last_lines` · `keep_matching` / `drop_matching` (regex) ·
`strip_tags` (etiketi alt ağacıyla siler) · `select_nth` (N'inci elementi alır) ·
`collapse_whitespace` · `max_chars`.

- HTML kuralları **stdlib `html.parser`** ile yazıldı; **bs4 gibi bir bağımlılık yok**.
- Kurallar **yalnız prompt'u** etkiler; `database/` altına ham içerik **tam** yazılır.
  Kesme olduysa sonuçta `truncated=true` + `truncated_note` görünür (sessiz kayıp yok).
- Bir kuralın işareti bulunamazsa **hiçbir şey yapmaz** (metni olduğu gibi bırakır) —
  sessizce boşaltmaz.
- **Ayrı/global bir "trimmer" katmanı YOKTUR.** Kırpma her Evidence'ın içindedir.
- Yeni kural tipi = **1 sınıf + registry'ye 1 satır**.

### A5.4 Eksik kanıt toleransı
Beklenen kanıt dosyası yoksa sistem **çökmez**. Ayrı bir `missing_evidence` alanı/raporu
**YOKTUR** (denendi, kaldırıldı — gereksiz karmaşıklıktı). Bunun yerine:

Profilin `evidence_to_llm` listesindeki bir kanıdın bloğu yoksa **blok yine yazılır**, içeriği
`(bu kanıt alınamadı / bulunmuyor)` olur. İki durumu da kapsar: attachment hiç gelmedi **ve**
geldi ama içeriği boş. Profilin **istemediği** kanıt için blok hiç oluşmaz.

Prompt şablonu bu işaretin anlamını modele ayrıca anlatır (A8): eksik blok normaldir, tek başına
`unknown`/`inconclusive` gerekçesi değildir.

---

## A6. Findings Sözleşmesi (Halka 2 → 3)

Kaynak-bağımsız, sabit yapı (alan adları İngilizce):

- `parameter1` / `parameter2` — istekten gelir (A4.2)
- `scenario_name`
- `failed_step` — hangi adımda patladı (ilk FAILED adım)
- `error_message` — asıl hata / stack trace (ham)
- `steps` — adım listesi + sonuçları (PASSED/FAILED/SKIPPED), **zaman sıralı**
- `evidence_blocks` — etiketli ham bloklar:
  `=== ADIMLAR ===`, `=== HATA ===`, `=== DOM ===`, `=== BROWSER LOG ===`, `=== BUILD LOG ===`
- `screenshot_paths` — png'lerin diskteki yolları (LLM'e gitmez; kanıt referansı)
- `retry_info` — varsa tekrar/deneme bilgisi
- `profile_name` — hangi analiz profili çalıştı (izlenebilirlik)
- `extra_context` — profilin prompt'a eklediği serbest metin
- `excluded_from_store` — profilin depoya yazmadığı kanıt adları
- `truncated` / `truncated_note` — içerik kuralları kesme yaptı mı, ne kesildi

> **`missing_evidence` YOKTUR** (kaldırıldı, A5.4): eksik kanıt ayrı bir alan değil, bloğun
> içindeki yer tutucu metinle taşınır.

> **Not:** `dom_excerpt` gibi web-kokan isim KULLANMA. Kanıtlar `evidence_blocks` içinde
> etiketle taşınır; platform farkı isimde değil, hangi blokların dolu olduğunda yaşar.

---

## A7. PreCheck — bilinen hataya LLM'siz hazır cevap

Prompt kurulmadan önce çalışan **`PreCheck` arayüzü**: girdi = `Findings`; çıktı = `None`
(normal LLM akışı devam eder) **veya** hazır bir teşhis (**LLM hiç çağrılmaz**).

| Gerçekleme | Ne yapar |
|---|---|
| `NoOpPreCheck` | Her zaman `None` — **varsayılan**, herkes LLM'e gider |
| `RuleBasedPreCheck` | `config/precheck_rules.json`'daki kurallardan **ilk eşleşen** kazanır |

**Neden yapıldı:** bazı hatalar analiz gerektirmiyor ("DB bilgileri değişti" gibi durumlar birçok
projede aynı görünüyor); orada son kullanıcıya doğrudan hazır cevap dönmek isteniyor.

**Kural alanları:** `name`, `match` (regex), `search_in` (`error_message` | `evidence`), `verdict`,
`confidence`, metin alanları (`suggestion`/`explanation`/…), `error_signature`.
Metinleri **insan yazar**, sistem üretmez (A10 "uydurma default yok" kuralına uyar).

**Görünürlük:** eşleşince `meta.llm_model = "precheck"` (LLM'e gidilmedi) ve `error_signature`
hangi kuralın cevapladığını söyler. `PreCheck.check` sözleşmesi ve `AnalysisStatus` **değişmedi**.

**Fail-fast:** bozuk regex / bilinmeyen verdict / kova dışı confidence / liste olmayan JSON →
**açılışta** hata.

> ⚠️ **Kural birikmesi riski (ilk planın bu kancayı bilinçli boş bırakma sebebi) sürüyor.**
> Bir kural LLM'i **tamamen** atlar; fazla geniş bir kalıp her senaryoyu yanlış etiketler ve kimse
> fark etmez. Bu yüzden: liste **config'te** (tek yerden gözden geçirilebilir), **boş** gelir,
> varsayılan `noop`'tur, kalıplar **dar** yazılmalıdır (`ORA-01017` gibi kesin imzalar;
> `error`/`failed` gibi genel kelimeler **asla**).

---

## A8. Prompt Sözleşmesi (Halka 3)

Katı prompt, şu bileşenlerle:
- **Rol:** QA otomasyon analisti / SDET.
- **Görev:** kesin hüküm değil, **gerekçeli ön teşhis** (test mi / uygulama mı / ortam mı).
- **Bağlam:** `parameter1` + `parameter2` verilir; profil isterse `extra_context` ile
  projeye özel bir cümle eklenir (ör. "bu projede ilk layout kritiktir").
- **Organize kanıt:** etiketli bloklar (`=== ADIMLAR ===`, `=== HATA ===`, `=== DOM ===` …),
  **zaman sıralı adım akışı** omurga olacak şekilde.
- **"KANIT HAKKINDA" bölümü (kritik):** hangi kanıtın geleceği koşuma göre **değişir**; bir blokta
  `(bu kanıt alınamadı / bulunmuyor)` yazması **normaldir**, arıza değildir. Görev eksikleri
  raporlamak değil, **eldeki kanıtla** teşhis üretmektir.
  → *Bu bölüm sonradan eklendi: yer tutucu blokları görünce model teşhis üretmek yerine sürekli
  "kanıt eksik" diyordu.*
- **Akıl yürütme:** adım adım düşün.
- **Sert negatif kısıtlar:** kanıtta olmayanı **uydurma**; gördüğünden fazlasını iddia etme.
- **Pes etme dengesi:** `HATA MESAJI` ve `ADIM SONUÇLARI` **her koşumda vardır** ve çoğu teşhis
  için yeterlidir. Eksik blok tek başına `unknown`/`inconclusive` gerekçesi **değildir**; yalnız
  confidence'ı bir kademe düşürebilir. `explanation`/`summary`'nin ana konusu "kanıt eksik"
  **olmamalıdır**; eksiklikten yalnız `confidence_reason` içinde söz edilir.
  `unknown`/`inconclusive` **son çaredir**.
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
`parameter1`, `parameter2`, `profile_name`, `truncated` (bool) + `truncated_note`,
`screenshot_paths`, `raw_llm_response` (parse öncesi ham cevap),
`meta`: `llm_model`, `input_tokens`, `output_tokens`, `duration_ms`, `analyzed_at`,
`status` (`ok` | `analysis_failed`)

> Bunlar **diskteki satırda** durur; **GET cevabında yalnız** `status` + `meta` + `result_id`
> gösterilir (A13).

### Default kuralı
**Metin alanlarında uydurma default YOK.** LLM boş dönerse alan **boş kalır**
("Analiz tamamlanamadı" gibi sahte default YAZMA).

---

## A11. Boyut / Token Yönetimi

- Kırpma **deterministiktir**: profilin içerik kurallarıyla yapılır (A5.3), token eşiğiyle değil.
  Yani "ne kesilecek" kararı **config'te yazılıdır**, koşuma göre değişmez.
- **`truncation_threshold_tokens` ve `token_chars_ratio` ayarları KALDIRILDI.** Sebep: karakter
  sayısından token tahmin etmek yanıltıcıydı ve hiç kullanılmıyordu — ölçmeden eşik koymak
  spekülasyondu.
- **Öncelik ilkesi korunur:** patlayan adım + hata mesajı **asla kesilmez** (zaten kural
  yazılmaz onlara); kesilecekse önce log gürültüsü, sonra DOM.
- Kırpma olursa çıktıya **görünür bayrak** düşer: `truncated=true` + `truncated_note`
  ("hangi profil, hangi kanıt"). **Sessiz kayıp yasaktır** — ham içerik `database/` altında tam.
- Sistem kırpma gerektiğinde **durup sormaz** (asenkron akış korunur), ama **asla gizlemez**.

> **Açık iş:** eşik bazlı otomatik kırpma **yok**. Gerekip gerekmediği, gerçek modelin context
> penceresi ve gerçek prompt boyutu **ölçüldükten sonra** kararlaştırılacak. Ölçmeden yapılmayacak.

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

### Tablolar (5 adet)
- **`runs`** — her job koşusu: `analyzer_run_id`, `parameter1/2`, `job_id`, `run_id`, `status`,
  senaryo sayıları, `note`, `cached_from`, timestamps + **job seviyesi ham iz**
  (`raw_run_response`, `raw_results_response`, **`build_log`**)
- **`analysis_results`** — her senaryonun teşhisi → **yarın Oracle'a taşınacak asıl tablo**
- **`evidence`** — ham senaryo dökümü (attachment'lar + `raw_detail`), profilin
  `evidence_to_store` kararına uygun
- **`prompts`** — **GİDEN** taraf: tam prompt + LLM'e gönderilen istek
- **`llm_responses`** — **GELEN** taraf: LLM'in tam ham zarfı + çıkarılan içerik + çağrı meta'sı

> `prompts` ve `llm_responses` **bilinçli olarak ayrıldı** (önce tek tabloydu): giden ve gelen
> aynı satırda olunca ham cevap kopyalanıyordu ve parse patladığında nereye bakılacağı belirsizdi.

### Tam iz (gözlemlenebilirlik)
Bir senaryo için: ham kanıt + Findings + gönderilen prompt + ham LLM cevabı + parse sonucu +
meta — hepsi `database/` altında, **insan tarafından açılıp incelenebilir.**
*(Gerekçe: ihtiyaçlar zamanla değişecek; dosya editlemek tablo şeması değiştirmekten kat kat
kolaydır. Şema olgunlaşınca `analysis_results` DB'ye taşınır.)*

### Önbellek
Anahtar: **`run_id` + `parameter1` + `parameter2`** — job_id **değil**.
*(İlk gerçekleme job_id ile anahtarlıyordu; bir job'ın onlarca koşumu olduğu için ikinci koşum
birincinin sonuçlarını görüyordu. Gerçek bir hataydı, düzeltildi.)*

- İsabet ederse **hiçbir indirme yapılmaz**: koşum çözümü (`resolve_run_id`) fetch'ten **önce**
  yapılır, bu yüzden isabette ağ maliyeti sıfıra yakındır.
- Yalnız **tam analiz edilmiş** koşumlar yeniden kullanılır (`note`'lu ya da kendisi cache'ten
  gelen satırlar kaynak olamaz).
- `run_id` boşsa cache **devre dışı** kalır (yanlış eşleşme riski yerine yeniden analiz).
- **Config ile açılıp kapanır** (`CACHE_ENABLED`), varsayılan **kapalı**.

---

## A13. API — Asenkron, iki endpoint

- **Başlat:** `POST /analyze/visiumgo` `{parameter1?, parameter2?, job_id | run_id}`
  → koşum satırını yazar, arka planda analizi başlatır, **hemen** `analyzer_run_id` döner.
  `job_id` veya `run_id`'den **biri zorunlu** (ikisi de yoksa 422); ikisi de verilirse `run_id`
  kazanır. Parametreler verilmezse `"default"`.
- **Sorgula:** `GET /analyze/visiumgo/{analyzer_run_id}`
  → durum (`pending`/`running`/`done`/`failed`), kaç senaryodan kaçı bitti, biten teşhisler.
  **Durum diskten okunur.** Yoksa 404.

**GET yalnız teşhisi gösterir (`RunView` / `DiagnosisView`, `app/domain/api.py`):**
LLM alanları + `status` + `meta` + `result_id`. **Ham iz API'ye girmez** (`raw_run_response`,
`raw_results_response`, `run_result`, `build_log`, `raw_llm_response`, `screenshot_paths`,
`profile_name`, `truncated`) — hepsi `database/` altında tam durur; `result_id` ile bulunur.

> Projeksiyon **API sınırındadır**, serviste değil: `AnalyzerService.get_run()` tam kaydı
> döndürmeye devam eder (iç hata ayıklama). Pydantic tanımsız anahtarları düşürdüğü için
> `runs` satırına ileride eklenecek alanlar API'ye **kazara sızmaz**.

- URL `visiumgo`'ya **sabit**. Kaynak parametreleştirme (`/analyze/{source}`) gerekirse
  ileride; bugün eklenmez. Ek endpoint (listeleme, detay, dosya erişimi, health) **bugün yok.**
- **Arka plan:** FastAPI **`BackgroundTasks`** (Docker/Redis yok). Senaryolar **parametrik
  paralellikle** işlenir; **her senaryo bittikçe diske yazılır.**
- **Redis'e hazır iki sınır** (baştan konur, geçiş ucuz olsun):
  1. Analizi tetikleyen yer **tek fonksiyon çağrısı** olsun (kuyruk değişince sadece o satır).
  2. Durum/sonuç **diskten** okunsun, bellekteki değişkenden değil.
- **Hiç hata yoksa:** "analiz edilecek hata yok" deyip temiz döner.
- **Senaryo çökerse job devam eder** (A9); kaydedilemeyen senaryo olursa koşumun `note` alanına
  yazılır — sessizce kaybolmaz.

### Config katılığı (sonradan eklendi)

`.env`'de **hiçbir ayara karşılık gelmeyen bir anahtar açılışta hata verir** (`extra="forbid"`)
ve anahtarın adını söyler. Sebep: yeniden adlandırılmış ya da yanlış yazılmış bir anahtar
sessizce yok sayılınca özellik kapalı kalıyor ve kimse fark etmiyordu (ör.
`VISIUMGO_JENKINS_LOG_PATH` → `VISIUMGO_BUILD_LOG_PATH` sonrası build log hiç çekilmezdi).
Makinenin alakasız ortam değişkenleri etkilenmez; yalnız `.env` dosyasının kendi anahtarları
denetlenir.

Aynı gerekçeyle `app/main.py` **import edilince** app kurulmaz (PEP 562 `__getattr__`):
`uvicorn app.main:app` çalışır ama modülü import etmek `.env` okumaz — testler makineye
bağımlı olmaz.

---

## A14. Mock Kuralları

1. **`if mock` / `is_mock` gibi dallanma YASAK** (A0.1). Mock, arayüzün **ayrı bir
   gerçeklemesidir**: `MockSource`, `MockLLMProvider`.
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
- **Ortam:** URL/token/model/`database/` yolu → **`.env`'den**. Windows'ta yalnızca `.env`
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

## A16. Durum — ne bitti, ne kaldı

**Bitti (kod tarafı tamam, mock'larla uçtan uca çalışıyor):**
- Halka 1 gerçek VisiumGo entegrasyonu (run çöz → FAILED senaryolar → detay → attachment indir).
- Halka 2 gerçek extraction; `mimeType`+`deviceId` ile Evidence eşleme.
- build log: VisiumGo `/logs` ZIP'inden `build.log` çıkarma.
- Gerçek LLM sağlayıcısı (OpenAI-uyumlu uç), ham cevap parse'tan **önce** kaydediliyor.
- Job bazlı profiller + içerik kuralları; PreCheck kural motoru; `run_id` bazlı önbellek;
  GET sadeleştirmesi; config katılığı.

**Kalan (yalnız gerçek servislere erişim gerektiriyor — kod işi değil):**
- Gerçek VisiumGo + gerçek LLM ile uçtan uca doğrulama.
- **Senaryo adı eşleşmesi:** `/results`'taki senaryo adı ile `build.log` içindeki
  `> Scenario [...]` **birebir** aynı mı? Değilse `keep_scenario_section` hiçbir şey kesmez
  (log tam kalır — sessiz kayıp yok, ama dilimleme de olmaz).
- Gerçek profilleri gerçek `job_ids` ile doldurmak (config işi).
- **Lokal model context penceresi + gerçek prompt token ölçümü** → eşik bazlı kırpma gerekli mi?
- İleride: job-seviyesi analiz (ayrı endpoint), png'nin multimodal modele verilmesi,
  Oracle'a geçiş, flaky liste raporu, aynı-hata gruplaması (`error_signature` üzerinden).

---

## A17. Kilitlenmiş Kararlar (özet)

1. **Merkezi ilke:** kodda `if mock` / `if platform` / `if type` dallanması **yok**;
   varyant = ayrı sınıf + arayüz + registry + DI.
2. **HARDCODED YOK** (config/`.env`/şema).
3. **SOLID** her harfine.
4. **Google Auto-Diagnose deseni:** agentless, tek-atış, parse-minimal, katı prompt.
   **Üründe LLM loop yok.**
5. **`parameter1` / `parameter2`:** **girdi**, tahmin edilmez (`bank`/`platform` kaldırıldı);
   eksik kanıt tolere edilir ve prompt'ta yer tutucuyla görünür kılınır.
6. **Evidence mimarisi:** 6 sınıf; `evidence_to_llm` + `evidence_to_store` **profilden**
   (`config/profiles.json`), her kanıtın kendi content selector'ı (9 kural tipi),
   ayrı global trimmer yok.
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
14. **PreCheck:** varsayılan `NoOpPreCheck`; `RuleBasedPreCheck` ile kurallar **config'ten**
    gelir (boş listeyle başlar). Kural birikmesi riski bilinçli olarak yönetilir: dar kalıplar,
    kısa liste, tek dosyadan gözden geçirme.
15. **Mock:** ayrı sınıf + DI; tüm mock çıktıları **`MOCK_`** ile başlar.
16. **Kırpma deterministiktir** (profil kuralları); token eşiği yok, ölçmeden konmayacak.
    Kesilirse `truncated` bayrağı + not; ham içerik `database/` altında tam.
17. **Docker yok.** Taşınabilirlik: `pathlib`, `.env`, `.gitattributes`, mock'larla ayakta.
18. Kod isimleri **İngilizce**, LLM metin içerikleri **Türkçe**.
19. **Flaky senaryolar analiz edilmez.**
20. **LLM hatası** → `analysis_failed`, ham cevap kaydedilir, **job devam eder.**
21. **GET yalnız teşhis gösterir**, ham iz diskte kalır (A13).
22. **Config katıdır:** `.env`'de tanınmayan anahtar açılışta hata (A13).

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

> **Durum: 1-13 tamamlandı.** Aşağıdaki liste hem yapılış sırasını hem bugünkü gerçeği anlatır;
> yeni bir yetenek eklenirken aynı sıra izlenir (önce sözleşme, sonra halka, sonra test).

1. **Sözleşmeleri çak:** Findings (A6) + JSON çıktı şeması (A10). Bunlar sabitlenmeden üstüne
   kod yazma.
2. **Domain katmanı:** enum'lar (`verdict` 6 değer, `StepStatus`, `RunStatus`,
   `AnalysisStatus`), sonuç modeli, API görünüm modeli (`api.py`), config katmanı.
3. **Halka 6 — Persistence:** `Repository` arayüzü + `FileRepository` (DB simülasyonu;
   tablo isimleri config'ten).
4. **Halka 4 — LLM:** `LLMProvider` arayüzü + `OpenAICompatibleLLMProvider` +
   `MockLLMProvider` (`MOCK_` etiketli).
5. **Halka 5 — Parsing:** yalnızca `_try_json`. Regex / section-parse **yok**.
6. **Evidence katmanı (A5):** `Evidence` arayüzü + 6 sınıf + registry +
   profil (`evidence_to_llm` / `evidence_to_store`) + content selector (9 kural tipi).
7. **Halka 3 — Prompt:** A8'e göre katı prompt kurucu (şablon config'ten).
8. **PreCheck (A7):** arayüz + `NoOpPreCheck` (varsayılan) + `RuleBasedPreCheck`
   (kurallar config'te, boş listeyle gelir).
9. **Halka 1 — Source:** `Source` arayüzü + `MockSource` + **gerçek `VisiumGoSource`**
   (run çöz → FAILED senaryolar → detay → attachment + build log).
10. **Halka 2 — Extraction:** `Extractor` arayüzü + **tek, kaynak-bağımsız `EvidenceExtractor`**.
    *(Ayrı bir `MockExtractor` YOK: mock ve gerçek Source aynı `RawScenario` şeklini ürettiği için
    extraction ikisinde de aynıdır — mock/gerçek farkı tamamen Source'ta yaşar.)*
11. **API + arka plan:** iki endpoint, asenkron, `BackgroundTasks`, parametrik `Semaphore`,
    her senaryo bittikçe diske yaz.
12. **Testler:** sözleşme-bazlı testler + mock'larla uçtan uca smoke testi.
13. **Taşınabilirlik dosyaları:** `.env.example`, `.gitignore`, `.gitattributes`, `.gitkeep`,
    `pyproject.toml`, `README` (Windows'ta çalıştırma adımları).
14. **Statik kontroller:** `ruff` + `mypy`, `pyproject.toml`'daki **`[lint]`** opsiyonel
    grubunda — `[dev]`'de **değil**, çünkü kilitli iş bilgisayarı `.[dev]` kurar ve bu paketleri
    indirmeye zorlanmamalıdır.

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
  `POST /analyze/visiumgo {parameter1?, parameter2?, job_id | run_id}` → arka plan →
  `database/` altına **tam iz** yazılır → `GET /analyze/visiumgo/{analyzer_run_id}` **teşhisi**
  döner.
- Mock çıktılarının hepsi **`MOCK_`** ile başlar.
- Gerçek VisiumGo/LLM **yalnızca `.env` değiştirilerek** açılır; kod değişmeden.
- Kodda **hiçbir** `if mock` / `if job_id ==` / `if type ==` dallanması **yoktur.**
- **Stub kalmaz:** Halka 1–2 gerçek gerçeklemeye sahiptir (`# TODO(work-pc)` işaretleri
  kaldırılmıştır).
- Sözleşme-bazlı testler geçer; **`ruff check .` ve `mypy` temizdir.**
