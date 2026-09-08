# VisiumGo Test Analyzer — Proje Planı (plan.md) — v4

> **Bu dosya tek doğru kaynaktır (single source of truth).** Çelişki halinde bu dosya geçerlidir.
>
> **v4 (2026-09-08):** Yeni faz. v3'ten farklar: **job grubuna göre prompt şablonu** (A8) ·
> **kanıt eşleşme raporu** (A5.5) · **kanıtsız senaryoya LLM çağrısı yok** → `no_evidence` (A10) ·
> **prompt sürümü meta'da** (A8.4) · **build log alınamazsa sebebi kaydediliyor** (A4.1) ·
> **ölçüm/eval iskeleti** (A19). Job-level analiz **kapsam dışı bırakıldı** (A18).
> Adım adım geçmiş: [`CHANGELOG.md`](CHANGELOG.md) · faz notları:
> [`docs/yeni-plan-notlari.md`](docs/yeni-plan-notlari.md).
>
> İki bölüm — **A:** ne inşa edildi/edilecek · **B:** nasıl inşa edilir.
>
> Kod/alan/değişken isimleri **İngilizce**. LLM'in ürettiği metin *içerikleri* **Türkçe**.

---

# BÖLÜM A — PROJE PLANI

## A0. Çatı İlkeleri

### A0.1 — MERKEZİ İLKE: Kodda davranış dallanması YOK
`if mock:`, `if platform == "web":`, `if type == ...` **yasaktır.** Her varyant kendi sınıfıdır,
ortak bir arayüzü uygular, seçim **registry + DI** ile yapılır. Yeni varyant = yeni sınıf +
registry'ye bir satır.

### A0.2 — HARDCODED YOK
Tablo isimleri, URL'ler, profil/kural bilgileri, model adı, paralellik, confidence kovaları,
**prompt şablonları** — hepsi config/`.env`/şema katmanından gelir.

### A0.3 — SOLID (her harfine)
SRP · Open/Closed · Liskov (mock ↔ gerçek) · Interface Segregation · Dependency Inversion.

### A0.4 — Gözlemlenebilirlik
Her adımın izi diske düşer. **Hiçbir şey sessizce olmaz** — alınamayan bir şey job'ı düşürmez ama
**sebebiyle** kaydedilir (build log: A4.1 · kanıt eşleşmesi: A5.5 · senaryo kaydı: A13).

### A0.5 — Taşınabilirlik
Mac'te yazılır → GitHub → Windows iş bilgisayarında koşar. **Docker YOK.**

### A0.6 — Proje boyutuna oranlı
POC. Best-practice uygulanır, abartılmaz.

---

## A1. Amaç

Başarısız otomasyon koşumlarını toplayıp ham kanıtı (test.log, DOM, browser.log, ekran görüntüsü,
build.log) **lokal bir LLM**'e yorumlatan FastAPI backend. Hedef: QA analistinin elle log
inceleme işini otomatikleştirmek; **güven seviyeli, gerekçeli ön teşhis** üretmek:
*"Neden patladı? Test hatası mı, uygulama hatası mı, ortam hatası mı? Ne yapılmalı?"*

Nihai hedef (kullanıcı ifadesi): job hata alınca inceleyen testçinin yerine bu sistem geçsin —
*"şu senaryolar bakım istiyor, bunlar sistem hatası, şu job gradle build yüzünden patlamış"*.

Kısıt: banka ortamı; veri/kod dışarı çıkmaz, on-premise LLM.

---

## A2. Mimari Deseni — Google Auto-Diagnose

- **Agentless / tek-atış:** tool-calling yok, döngü yok, **senaryo başına tek çağrı**.
- **Parse-minimal:** alan-çıkaran parser yazılmaz; ham kanıt etiketli bloklarla verilir, anlamı
  LLM çıkarır. Kod yalnız kaba boyut yönetimi yapar.
- **Katı prompt:** adım-adım akıl yürütme + sert negatif kısıtlar + zorunlu JSON + kanıt gösterimi.

**ÜRÜNDE LLM DÖNGÜSÜ YOKTUR.**

---

## A3. Zincir Mimarisi

```
Halka 1: Source        → VisiumGo API: run + results + detay + attachment + build log
Halka 2: Extraction    → ham kanıt → Evidence'lar → Findings (profil + içerik kuralları)
         PreCheck      → bilinen hataya config'ten hazır cevap; eşleşirse LLM ATLANIR
         Kanıt kapısı  → prompt'a girecek kanıt yoksa LLM ATLANIR (A10 `no_evidence`)
Halka 3: Prompt Build  → Findings → profilin şablonu + ortak sözleşme
Halka 4: LLM Call      → lokal LLM'e tek çağrı
Halka 5: Parsing       → LLM JSON cevabı → yapı
Halka 6: Persist + API → repository'ye kayıt + asenkron API
```

Mock↔gerçek geçişi yalnız `.env` ile; kod değişmez.

---

## A4. Girdi

### A4.1 Job seviyesi
- VisiumGo raporu (kaç senaryo koştu, hangileri patladı).
- **build log** — `GET {BASE}/api/runs/{run_id}/logs`. Bu uç **ZIP** döndürür; içinden
  `build.log` çıkarılır (`VISIUMGO_BUILD_LOG_ENTRY`). Ham ZIP saklanmaz. Log her koşumda
  **bütün olarak** çekilip `runs` satırına yazılır; LLM'e gitmesi ve senaryo bazında kesilmesi
  **profil kararıdır** (A5.2/A5.3).
- **Çekilemezse job durmaz, sebebi kaydedilir:** `build_log_error` (runs satırı + GET cevabı)
  hangi yolun hangi hatayla düştüğünü söyler. Yol hiç ayarlanmamışsa bu **kasıtlı atlamadır**,
  alan boş kalır — "bu job'da build log yok" ile "alınamadı" birbirine karışmaz.

### A4.2 `parameter1` / `parameter2` — girdi olarak gelir, tahmin edilmez
- **`parameter1`** verilirse analiz profilini **doğrudan** seçer. Bilinmeyen ad → koşum `failed`.
- **`parameter2`** serbest metin; yalnız kaydedilir.
- İkisi de yoksa `"default"`; profil o zaman **`job_id`** ile bulunur.
- Hiçbir şey **dosya adlarından tahmin EDİLMEZ.**

### A4.3 Dosya tipleri

| Dosya | Ne zaman | Eşleşme anahtarı |
|---|---|---|
| `test.log` | çoğu koşumda (mobilde UI ağacı bunun içinde) | `text/plain` + `test` |
| `browser.default.html` | web adımları (DOM) | `text/html` + `browser.default` |
| `browser.default.log` | web adımları | `text/plain` + `browser.default` |
| `browser.default.png` | web ekran görüntüsü (LLM'e gitmez) | `image/png` + `browser.default` |
| `mobile.{os}.{marka}.png` | mobil ekran görüntüsü (LLM'e gitmez) | `image/png` + `mobile` öneki |
| `build.log` | **job seviyesi**; sentetik attachment (`device_id="build"`) | `text/plain` + `build` |

- **Ayrı mobil XML/DOM dosyası YOKTUR.**
- **Her kanıt gelmeyebilir.** Bazı joblarda senaryo bazlı hiçbir dosya üretilmez; orada tek kanıt
  **build log**'dur (bkz. A8.2 `buildlog` şablonu).
- Attachment → Evidence eşlemesi **`mimeType` + `deviceId`** ile yapılır, dosya adıyla değil.

### A4.4 Flaky senaryolar
Tekrar koşumda geçen senaryolar **analiz edilmez** (analiz edilecek hata yok).

---

## A5. Evidence Mimarisi

### A5.1 Sınıflar (6)
`TestLogEvidence` · `HtmlEvidence` · `BrowserLogEvidence` · `BuildLogEvidence` ·
`WebScreenshotEvidence` · `MobileScreenshotEvidence`. Ortak `Evidence` arayüzü, registry'de kayıtlı,
anahtar `(mime_type, device_id)`. Yeni tip = 1 sınıf + 1 satır.

### A5.2 Profil kararları (`config/profiles.json`)

> Kopyalanabilir örnek: **`config/profiles.example.json`** (dört job grubu, gerçek kural
> yazımıyla). Bir testle geçerliliği kilitli — bayatlarsa CI değil, `pytest` yakalar.
- **`evidence_to_llm`** — hangi kanıtlar prompt'a girer.
- **`evidence_to_store`** — hangilerinin içeriği `database/` satırına gömülür.
- **`prompt`** — bu job grubunun **prompt şablonu** (A8).
- **`extra_context`** — prompt'a eklenecek job grubu cümlesi.
- **`rules`** — her kanıt için içerik kuralları (A5.3).

**Profil seçimi:** `parameter1` → `job_ids` eşleşmesi → `default`. Eksik `default`, yinelenen
`job_id`, bozuk kural, **olmayan şablon adı** → **açılışta** hata.

> **`default` profil build log GÖNDERMEZ** (kullanıcı kararı). Build log yalnız açıkça tanımlanmış
> job gruplarında prompt'a girer.

### A5.3 İçerik kuralları — 9 tip
`keep_scenario_section` (job logunu senaryo bazında dilimler) · `keep_first_lines` /
`keep_last_lines` · `keep_matching` / `drop_matching` (regex) · `strip_tags` · `select_nth` ·
`collapse_whitespace` · `max_chars`.

- HTML kuralları **stdlib `html.parser`** ile; bs4 gibi bağımlılık yok.
- Kurallar **yalnız prompt'u** etkiler; `database/` altına ham içerik tam yazılır.
- **Bir kuralın işareti bulunamazsa hiçbir şey yapmaz** (metni olduğu gibi bırakır). Sessiz kayıp
  olmaz — ama dilimleme de olmaz; bu durum A5.5 raporunda görünür.
- Ayrı/global bir "trimmer" katmanı YOKTUR. Yeni kural tipi = 1 sınıf + 1 satır.

**Build log senaryo dilimleme:** config yalnız kuralı ister —

```json
{ "type": "keep_scenario_section" }
```

İşaretler (`> Scenario [{scenario_name}] started` … bir sonraki `beforeScenario:`) **kuralın
kendi varsayılanıdır**, config'te tekrarlanmaz. Gerekçe: bunlar bir *job kararı* değil,
**VisiumGo build.log formatının kendisidir** — her job'da aynıdır. Her profile kopyalanırsa
birindeki bir harf hatası o job'ın logunu sessizce kesilmemiş bırakır. Formatı farklı bir job
çıkarsa `start`/`end` config'ten **üzerine yazılabilir** (`"end": ""` = dosya sonuna kadar).

> Aynı çizgi projede zaten var: blok etiketleri (`=== DOM ===`) ve "kanıt alınamadı" metni de
> config'te değil koddadır — onlar da karar değil, formattır. **Config = karar, kod = bilgi.**

### A5.4 Eksik kanıt toleransı
Beklenen kanıt yoksa sistem çökmez, ayrı bir `missing_evidence` alanı **YOKTUR**. Profilin
istediği (ya da şablonun andığı) kanıt yoksa blok yine yazılır, içeriği
`(bu kanıt alınamadı / bulunmuyor)` olur. Profilin **istemediği** kanıt için blok hiç oluşmaz.

### A5.5 Kanıt eşleşme raporu (`evidence_report`) — YENİ
Her senaryo için `evidence` satırına yazılır:
- **`attachments`** — gelen her dosya: `file_name`, `mime_type`, `device_id`, eşleştiği Evidence
  sınıfı (**`""` = eşleşmedi**), profil onu LLM'e gönderiyor mu, kaç karakter geldi.
- **`blocks`** — prompt'a giden her blok: kaç karakter, **dolu mu yer tutucu mu**, kuralları
  gerçekten kesti mi.
- **`unmatched`** — hiçbir Evidence sınıfının sahiplenmediği dosya adları.

**Neden:** "DOM gelmedi mi, geldi de eşleşmedi mi?" sorusu sonradan cevaplanamıyordu. Artık tek
gerçek koşum cevabı kendi yazıyor. `BUILD LOG` bloğu `trimmed=false` + ham log boyutunda ise
dilimleme kuralı işaretini bulamamış demektir.

---

## A6. Findings Sözleşmesi (Halka 2 → 3)

`parameter1` · `parameter2` · `scenario_name` · `failed_step` · `error_message` · `steps` ·
`evidence_blocks` (etiketli ham bloklar: `ADIMLAR`, `HATA`, `DOM`, `BROWSER LOG`, `BUILD LOG`) ·
`screenshot_paths` · `retry_info` · `profile_name` · **`prompt_template`** · `extra_context` ·
`excluded_from_store` · `truncated` / `truncated_note` · **`evidence_report`**.

Ayrıca **`has_evidence_for_llm`** (türetilmiş): tüm bloklar boş/yer tutucu **ve** hata metni de
adım listesi de yoksa `False` → LLM çağrılmaz (A10 `no_evidence`).

> `missing_evidence` YOKTUR · `dom_excerpt` gibi web-kokan isim KULLANILMAZ.

---

## A7. PreCheck — bilinen hataya LLM'siz hazır cevap

`PreCheck` arayüzü: girdi `Findings`, çıktı `None` (LLM akışı devam) **veya** hazır teşhis.
`NoOpPreCheck` **varsayılan** · `RuleBasedPreCheck` `config/precheck_rules.json`'daki ilk eşleşen
kuralı uygular. Eşleşince `meta.llm_model = "precheck"`.

Bozuk regex / bilinmeyen verdict / kova dışı confidence → **açılışta** hata.

> ⚠️ Kural birikmesi riski sürüyor: bir kural LLM'i tamamen atlar. Liste **boş** gelir, varsayılan
> `noop`'tur, kalıplar **dar** yazılmalıdır (`ORA-01017` gibi; `error`/`failed` **asla**).

---

## A8. Prompt Sözleşmesi (Halka 3) — job grubuna göre şablon

### A8.1 Şablon klasörü — `config/prompts/`

| Dosya | Kime |
|---|---|
| `default.txt` | profil şablon seçmezse |
| `web.txt` | test log + DOM + browser log |
| `mobile.txt` | test log (mobil UI ağacı onun içinde) |
| `hybrid.txt` | tek akışta hem web hem mobil adım |
| `buildlog.txt` | senaryo bazlı kanıt üretmeyen joblar; **tek kanıt build log** |
| `_contract.txt` | **ortak çıktı sözleşmesi** — şablon değil |

Profil şunu der: `"prompt": "mobile"`. Demezse `default`.

### A8.2 Ortak sözleşme neden ayrı dosyada
JSON şeması + 6 verdict + 5 confidence kovası **tek yerde** yazılır ve her şablonun sonuna
sistem ekler. 5 şablonda elle bakım edilen bir şema er geç dolar; bir harf kayınca parse
**sessizce** bozulur. Şablon yazarı yalnız üst kısmı yazar.

### A8.3 Placeholder'lar
Ortak: `$parameter1` `$parameter2` `$scenario_name` `$failed_step` `$error_message` `$steps`
`$extra_context` `$confidence_buckets` · Toplu yerleşim: `$evidence_blocks` ·
**Kanıt bazlı:** `$test_log` `$dom` `$browser_log` `$build_log`.

Şablonun andığı kanıt gelmediyse alan boş kalmaz, yer tutucu yazar (A5.4).
**Tanınmayan bir `$placeholder` açılışta hatadır** — yoksa LLM'e ham `$dom_excerpt` giderdi.

### A8.4 Prompt sürümü
Her şablonun (şablon + sözleşme) tam metninin kısa hash'i `meta.prompt_version`, adı
`meta.prompt_template` olarak her teşhise damgalanır. **Neden:** "cevaplar kötüleşti" iddiası
ancak hangi prompt sürümünün hangi cevabı ürettiği kayıtlıysa kanıtlanabilir.

### A8.5 İçerik ilkeleri (her şablonda)
Rol (QA/SDET) · görev (kesin hüküm değil, **gerekçeli ön teşhis**) · job grubu bağlamı
(web/mobil/hibrit yorum farkı, `extra_context`) · **zaman sıralı adım akışı omurga** ·
eksik kanıt normaldir ama teşhisten kaçış gerekçesi değildir · uydurma yasak ·
`unknown`/`inconclusive` **son çare** · açıklamalar **Türkçe**.

---

## A9. LLM Çağrısı (Halka 4)

`LLMProvider` arayüzü: `OpenAICompatibleLLMProvider` (gerçek) · `MockLLMProvider` (sahte).
OpenAI-uyumlu passthrough · **`temperature = 0`** · **senaryo başına tek çağrı** ·
paralellik `asyncio.Semaphore` ile **config'ten**.

**Hata dayanıklılığı:** timeout / geçersiz JSON / çöp cevap → o senaryo `analysis_failed`,
**ham cevabıyla** kaydedilir, **job devam eder**.

---

## A10. Çıktı JSON Sözleşmesi (Halka 5)

**LLM alanları:** `scenario_name` · `root_cause` · `error_type` · `verdict` · `explanation` ·
`suggestion` · `confidence` · `confidence_reason` · `summary` · `most_relevant_log_lines` ·
`error_signature`.

**`verdict` — 6 değer:** `test_maintenance` · `application_bug` · `environment_error` ·
`transient_error` · `unknown` · `inconclusive`.

**`confidence` — 5 kova:** `0.1 / 0.25 / 0.5 / 0.75 / 0.99`. LLM ne dönerse o yazılır; map YOK.

**Sistem tarafı meta:** `parameter1` · `parameter2` · `profile_name` · `truncated(_note)` ·
`screenshot_paths` · `raw_llm_response` · `meta` (`llm_model`, **`prompt_template`**,
**`prompt_version`**, tokenlar, `duration_ms`, `analyzed_at`) · `status`.

**`status` — 3 değer:**
- `ok` — teşhis üretildi
- `analysis_failed` — bir şey bozuldu (timeout, çöp cevap, parse)
- **`no_evidence`** — prompt'a girecek hiçbir kanıt yoktu, **LLM hiç çağrılmadı**. Bozulan bir şey
  yok; analiz edilecek şey yok. *(Boş prompt'la sorulan sorunun cevabı "kanıt yok" olurdu; bunu
  sistem zaten biliyor, çağrının parası ödenmez.)*

**Default kuralı:** metin alanlarında **uydurma default YOK.**

---

## A11. Boyut / Token Yönetimi

- Kırpma **deterministiktir**: profilin içerik kurallarıyla (A5.3), token eşiğiyle değil.
- **Ölçüm var:** her prompt'un karakter boyutu `prompts` satırında `prompt_chars` olarak durur.
  Eşik bazlı otomatik kırpma **hâlâ yok** — gerçek model penceresi ve gerçek boyut ölçüldükten
  sonra karara bağlanacak. **Ölçmeden konmayacak.**
- Patlayan adım + hata mesajı **asla kesilmez**.
- Kırpma olursa `truncated=true` + `truncated_note`. **Sessiz kayıp yasaktır.**

---

## A12. Persistence — `database/` = DB simülasyonu (Halka 6)

Klasör = veritabanı · alt klasör = tablo · JSON dosyası = satır. `Repository` arayüzü:
`save()` / `get()` / `list()` / `exists()`. Bugünkü backend `FileRepository`; ileride
`SqliteRepository` / `OracleRepository` aynı arayüzle takılır, **üst kod değişmez.**

### Tablolar (5)
- **`runs`** — koşum durumu, parametreler, senaryo sayıları, `note`, `cached_from`, ham job
  cevapları, **`build_log`** + **`build_log_error`**
- **`analysis_results`** — her senaryonun teşhisi (yarın Oracle'a taşınacak asıl tablo)
- **`evidence`** — ham senaryo dökümü + **`evidence_report`** (A5.5)
- **`prompts`** — GİDEN: tam prompt + istek + **`prompt_chars`**
- **`llm_responses`** — GELEN: ham zarf + içerik + çağrı meta'sı

### Önbellek
Anahtar **`run_id` + `parameter1` + `parameter2`** (job_id değil). İsabette indirme yapılmaz.
Yalnız tam analiz edilmiş koşumlar yeniden kullanılır. `run_id` boşsa cache devre dışı.
`CACHE_ENABLED` ile açılır, varsayılan **kapalı**.

---

## A13. API — asenkron, iki endpoint

- **Başlat:** `POST /analyze/visiumgo` `{parameter1?, parameter2?, job_id | run_id}` → hemen
  `analyzer_run_id`. `job_id` veya `run_id`'den biri zorunlu (yoksa 422); ikisi varsa `run_id`.
- **Sorgula:** `GET /analyze/visiumgo/{analyzer_run_id}` → durum, kaç senaryo bitti, teşhisler.
  Durum **diskten** okunur. Yoksa 404.

**GET yalnız teşhisi gösterir:** LLM alanları + `status` + `meta` + `result_id`; koşum seviyesinde
`note` ve `build_log_error`. **Ham iz API'ye girmez** (`raw_run_response`, `build_log`,
`raw_llm_response`, `evidence_report`, `screenshot_paths`, `profile_name`, `truncated`) — hepsi
`database/` altında, `result_id` ile bulunur.

> Projeksiyon **API sınırındadır** (`app/domain/api.py`), serviste değil. Pydantic tanımsız
> anahtarları düşürdüğü için yeni alanlar API'ye kazara sızmaz.

**Arka plan:** FastAPI `BackgroundTasks` · parametrik paralellik · her senaryo bittikçe diske
yazılır · senaryo çökerse job devam eder, sebep `note`'a yazılır.

**Config katılığı:** `.env`'de **tanınmayan anahtar açılışta hatadır** (`extra="forbid"`) ve
adını söyler. `app/main.py` import edilince app kurulmaz (PEP 562) — testler `.env`'e bağımlı değil.

---

## A14. Mock Kuralları

1. `if mock` dallanması **yasak**; mock ayrı bir gerçeklemedir (`MockSource`, `MockLLMProvider`),
   seçim config/DI ile yapılır.
2. Mock'un ürettiği **her değer `MOCK_` ön ekiyle başlar.** Gerçek gerçeklemeler asla yazmaz.

---

## A15. Taşınabilirlik

`pathlib` · `.env` · `.env.example` güncel · `.gitattributes` (`* text=auto`) · `.gitignore`
(`database/` içeriği hariç, `.gitkeep` ile yapı korunur) · **Docker yok** · mock'larla ayakta.

**İş-pc'ye inerken `.env` farkları:** `PROMPT_TEMPLATE_PATH` **kalktı** →
`PROMPTS_DIR=config/prompts`. Config katı olduğu için eski anahtar açılışta hata verir (kasıtlı).

---

## A16. Durum — ne bitti, ne kaldı

**Bitti:** Halka 1-6 gerçek gerçeklemeleriyle · job bazlı profiller + 9 içerik kuralı ·
**job grubuna göre prompt şablonu (5 şablon + ortak sözleşme)** · PreCheck kural motoru ·
`run_id` bazlı önbellek · GET sadeleştirmesi · config katılığı · **build log hata sebebi** ·
**kanıt eşleşme raporu** · **kanıtsız senaryoda LLM'e gitmeme** · **prompt sürümü** ·
**ölçüm iskeleti**.

**Kalan:**
- Gerçek VisiumGo + gerçek LLM ile uçtan uca doğrulama (iş-pc).
- **Gerçek profilleri gerçek `job_ids` ile doldurmak** (config işi) — asıl kalan iş bu.
- **Senaryo adı eşleşmesi:** `/results`'taki ad ile `build.log` içindeki `[...]` birebir aynı mı?
  Değilse dilimleme olmaz; artık `evidence_report` bunu söylüyor.
- Golden set'i gerçek vakalarla doldurmak (A19).
- Lokal model context penceresi + gerçek prompt boyutu ölçümü → eşik gerekli mi (A11).
- İleride: koşum sonu aksiyon listesi (verdict'e göre gruplu özet — ertelendi), png'nin
  multimodal modele verilmesi, Oracle'a geçiş, `error_signature` ile aynı-hata gruplaması.

---

## A17. Kilitlenmiş Kararlar

1. Kodda `if mock` / `if platform` / `if type` **yok**; varyant = sınıf + registry + DI.
2. **HARDCODED YOK.**
3. **SOLID** her harfine.
4. **Agentless, tek-atış, parse-minimal, katı prompt.** Üründe LLM loop yok.
5. `parameter1`/`parameter2` **girdidir**, tahmin edilmez.
6. Evidence mimarisi: 6 sınıf, profil bayrakları, 9 kural tipi, global trimmer yok.
7. Mobilde ayrı XML/DOM dosyası yok.
8. Parsing yalnız LLM JSON cevabı için (`try_json`); alan-çıkaran parser yok.
9. `verdict` **6 değer**.
10. `confidence` **5 kova**; LLM ne dönerse o.
11. Persistence `database/` simülasyonu, `Repository` arayüzü arkasında.
12. **Tam iz** gözlemlenebilir.
13. API iki endpoint, asenkron, Redis'e hazır iki sınır.
14. PreCheck varsayılan `noop`; kurallar config'te, dar kalıplarla.
15. Mock ayrı sınıf + `MOCK_` ön eki.
16. Kırpma deterministiktir; token eşiği **ölçmeden konmaz**.
17. **Docker yok.**
18. Kod İngilizce, LLM metinleri Türkçe.
19. Flaky senaryolar analiz edilmez.
20. LLM hatası → `analysis_failed`, ham cevap kaydedilir, job devam eder.
21. GET yalnız teşhis gösterir; ham iz diskte.
22. Config katıdır: `.env`'de tanınmayan anahtar açılışta hata.
23. **Config = karar, kod = bilgi.** Config "ne yapılsın"ı söyler (bu job'da build log senaryo
    bazında kesilsin); "nasıl bulunur"u (log formatı, blok etiketleri) kod bilir. Format bilgisi
    profillere kopyalanmaz; gerekirse config üzerine yazar.
24. **Sessiz kayıp yok:** alınamayan bir şey job'ı düşürmez ama **sebebiyle** kaydedilir;
    "yoktu" ile "alınamadı" ayırt edilebilir kalır.
25. **Prompt job grubuna göre şablondan gelir; çıktı sözleşmesi tek dosyadan.** Şablon çoğalır,
    sözleşme çoğalmaz.
26. **Boş prompt sorulmaz:** kanıt yoksa LLM çağrılmaz, sonuç `no_evidence`.
27. **`default` profil build log göndermez;** build log yalnız tanımlı job gruplarında gider.

---

## A18. Job-level analiz — KAPSAM DIŞI (kullanıcı kararı, 2026-09-08)

Konuşuldu, tasarlandı, **yapılmayacak.** Fikir şuydu: job'ın **kendisi** patladığında (gradle
build alınamadı, ortam ayağa kalkmadı) senaryo/attachment olmaz, `/results` boş gelir; o zaman
build log'dan "bu job neden patladı" sorusu ayrı bir prompt'la sorulsun.

**Neden yapılmadı:** (1) kullanıcı "gerek yok" dedi; (2) hatalı job'ın VisiumGo'da hangi durum
değerini döndürdüğü bilinmiyor (başarılıda `runResult.state == "PASSED"`), uydurma bir değerle
yazılan kod iş bilgisayarında **sessizce yanlış** çalışırdı.

> Yeniden istenirse: tespit `runResult.state` + config'ten durum listesi · kanıt build log
> (mevcut kural motoruyla, yeni parser yok) · ayrı şablon + aynı `_contract.txt` · seçim tek
> registry lookup'ı (koda dağılmış `if` değil). Bu kadarı tasarım olarak yeterli.

---

## A19. Ölçüm — golden set (`evals/`)

**Neden:** "cevaplar kötüleşti" bir his olarak kaldığı sürece hiçbir prompt değişikliği
değerlendirilemez. Ölçüm, hissi sayıya çevirir.

- `evals/cases/*.json` — elle etiketlenmiş vakalar: senaryo + **insanın verdiği doğru verdict**.
  Set **boş başlar**; uydurma vaka hiçbir şey ölçmez.
- `python -m evals.runner` — vakaları **gerçek zincirden** geçirir (extraction → profil → şablon →
  LLM → parse), verdict'leri karşılaştırır, skor tablosu basar ve **hangi prompt sürümünün**
  ürettiğini yazar. `--strict` ile fark varsa çıkış kodu 1 (CI).
- Servis bu koda bağımlı **değildir** (`app/` içinden import edilmez); aynı parser (`try_json`)
  kullanılır ki iki parser birbirinden ayrılmasın.
- Üretimdeki kanıt kapısı burada da geçerli: kanıtsız vaka LLM'e gitmez.

---

# BÖLÜM B — ÇALIŞMA TALİMATLARI

## B1. Çalışma Düzeni

- Dış hafıza: **`plan.md`** (bu dosya) + **`CHANGELOG.md`**.
- Her oturum başında ikisini oku, nerede kalındığını bul. **Bitmiş işi tekrar yazma.**
- Her adım bitince `CHANGELOG.md`'ye yaz: hangi dosyalar, hangi kararlar, ne eksik, **sıradaki adım**.
- Tek hamlede "hepsini yaptım" deme; **halka halka** ilerle.

## B2. Yapım / Düzeltme Sırası

Yeni yetenek eklenirken: **önce sözleşme, sonra halka, sonra test.**
1. Sözleşmeler (Findings A6 + çıktı şeması A10) — bunlar sabitlenmeden kod yazma.
2. Domain (enum'lar, sonuç modeli, API görünümü, config).
3. Halka 6 Persistence → 4 LLM → 5 Parsing → Evidence katmanı → 3 Prompt → PreCheck →
   1 Source → 2 Extraction → API/arka plan.
4. Testler (sözleşme-bazlı + uçtan uca smoke) ve taşınabilirlik dosyaları.
5. Statik kontroller: `ruff` + `mypy`, `pyproject.toml`'da **`[lint]`** opsiyonel grubunda —
   `[dev]`'de **değil** (kilitli iş bilgisayarı `.[dev]` kurar).

## B3. Sert Kurallar — İHLAL ETME

1. **Yeni dosya/sınıf/servis yaratma refleksi YOK.** Önce mevcut yapıyı ara ve genişlet.
2. **İsim / imza / endpoint kararlarını DEĞİŞTİRME.**
3. **Belirsizlikte kendi kafana göre karar VERME — DUR ve SOR.**
4. **`if mock` / `if platform` / `if type` YAZMA.**
5. **HARDCODED YAZMA.**
6. **Alan-çıkaran parser YAZMA.**
7. **Tool-calling / agent loop KURMA.**
8. **PreCheck'e kural listesi EKLEME.**
9. **Metin alanlarına uydurma default YAZMA.**
10. **Kapsam dışına ÇIKMA;** fark ettiğin başka sorunları `CHANGELOG.md`'ye liste hâlinde bildir.
11. **Taşınabilirlik:** `pathlib`, platforma özel varsayım yok, Docker yok.
12. **Mock çıktılarına `MOCK_` ön eki koy.**
13. **Spekülatif özellik yazma:** istenmeyen yeteneği "ileride lazım olur" diye ekleme;
    tasarımını plan.md'ye yaz, kodu istendiğinde yaz.

## B4. Bitmiş Sayılma Ölçütü

- `.env.example` kopyalanıp `uvicorn` ile açıldığında **mock source + mock LLM** ile uçtan uca
  çalışır: `POST` → arka plan → `database/` altına tam iz → `GET` teşhisi döner.
- Mock çıktılarının hepsi **`MOCK_`** ile başlar.
- Gerçek VisiumGo/LLM **yalnızca `.env` değiştirilerek** açılır.
- Kodda **hiçbir** `if mock` / `if job_id ==` / `if type ==` dallanması yoktur.
- Sözleşme-bazlı testler geçer; **`ruff check .`, `ruff format --check .` ve `mypy` temizdir.**
- Yeni bir job grubu eklemek **kod değil config** işidir (profil satırı + gerekirse şablon).
