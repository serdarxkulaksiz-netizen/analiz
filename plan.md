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

### A4.0 Hangi koşum analiz edilir + job durumu

Çözümleme **tek yerde**, kanıt indirilmeden önce yapılır (`Source.resolve_run`) ve tek bir
**koşum özeti** üretir: `run_id` · `job_id` · `job_name` · `state` · `run_result` · ham cevap.

| İstek | Servis | Seçim |
|---|---|---|
| `run_id` verildi | `GET /api/runs/{run_id}` | o koşum |
| `job_id` verildi | `GET /api/runs?jobId=` | `RUNNING` elenir, kalan `PASSED`/`FAILED` içinden **en büyük `id`** |

- `id` **koşum id'sidir** ve her koşumda büyür; sıralama `startTime` ile değil bununla yapılır.
- **Bilinmeyen bir `state`** (ör. `ABORTED`) de elenir ama **sessizce değil**: atlandığı `runs`
  satırının `note` alanına yazılır.
- Analiz edilebilir koşum kalmazsa hata; koşum `failed` biter.

**`runResult.state` job'ın kendi sağlığıdır, senaryoların değil** — gerçek bir koşumda
`state=PASSED` iken `failScenarios=2` görüldü.

| `state` | Davranış |
|---|---|
| `PASSED` | normal zincir |
| `FAILED` | job'ın kendisi patlamış: `job_ids` eşlemesine **bakılmaz**, her senaryo sabit **`job_failed`** profiliyle analiz edilir; kullanılan profil `note`'a yazılır |
| `RUNNING` | analiz **yapılmaz**: build log dahil hiçbir istek atılmaz, koşum `failed` biter (yarım koşum teşhis edilmez) |

Dallanma koda dağılmış `if` değil **tek registry satırıdır** (`STATE_PROFILE_OVERRIDE`).

**Profil hangi job ile seçilir:** çağıranın verdiği `job_id`; yalnız `run_id` verilmişse koşum
cevabındaki `jobId`. Böylece run_id ile gelen istek de kendi job'ının profilini alır.

### A4.1 Job seviyesi
- VisiumGo raporu (kaç senaryo koştu, hangileri patladı).
- **build log** — `GET {BASE}/api/runs/{run_id}/logs`. Bu uç **ZIP** döndürür; içinden
  `build.log` çıkarılır (`VISIUMGO_BUILD_LOG_ENTRY`). Ham ZIP saklanmaz. Log her koşumda
  **bütün olarak** çekilip `runs` satırına yazılır; LLM'e gitmesi ve senaryo bazında kesilmesi
  **profil kararıdır** (A5.2/A5.3).
- **Çekilemezse job durmaz, sebebi kaydedilir:** `build_log_error` (runs satırı + GET cevabı)
  hangi yolun hangi hatayla düştüğünü söyler. Yol hiç ayarlanmamışsa bu **kasıtlı atlamadır**,
  alan boş kalır — "bu job'da build log yok" ile "alınamadı" birbirine karışmaz.

### A4.2 `parameter1` / `parameter2` — ayrılmış anahtarlar, hiçbir kararı etkilemez

- İstekle gelirler, **`runs` satırına yazılırlar** ve `GET` cevabında görünürler. **Bitti.**
- **Hiçbir yerde kullanılmazlar:** profil seçmezler · `Findings`'e taşınmazlar · prompt'ta yer tutucuları **yoktur** · teşhis satırında
  tekrarlanmazlar.
- Bilinmeyen bir değer **hata değildir**; hiçbir şeyi adlandırmıyorlar.
- İleride gerçek bir ihtiyaç çıkarsa buradan başlanır; o güne kadar **ölü anahtar** olarak
  dururlar.

> **Neden bu kadar keskin:** bu iki alan "ileride lazım olur" diye açık bırakıldıkça her fazda
> bir iş kuralına sızdı — önce profil seçimine, sonra prompt'a, sonra (kaldırılan) önbellek
> anahtarına.
> Kullanılabilecek bir kanal bırakmak, kullanılmasını garanti ediyor.

### A4.3 Dosya tipleri

Kanıtın kimliği **`deviceId` + dosya uzantısıdır** — VisiumGo önyüzünün gösterdiği adın aynısı.
Ham `fileName` `<klasör>/<deviceId>_<sayı>.<uzantı>` biçiminde gelir; ortadaki sayı yalnız
benzersizlik içindir (`test.properties`'te o da yoktur).

| Dosya | Ne zaman | Eşleşme anahtarı |
|---|---|---|
| `test.log` | çoğu koşumda; adım akışı | `test` + `.log` |
| `test.properties` | koşum özellikleri (cihaz UDID, `failedStep.*`, retry) | `test` + `.properties` |
| `browser.default.html` | web adımları (DOM) | `browser.default` + `.html` |
| `browser.default.log` | web adımları | `browser.default` + `.log` |
| `browser.default.png` | web ekran görüntüsü (LLM'e gitmez) | `browser.default` + `.png` |
| `mobile.{os}.{cihaz}.xml` | **mobil UI ağacı** — artık ayrı dosya | `mobile` öneki + `.xml` |
| `mobile.{os}.{cihaz}.png` | mobil ekran görüntüsü (LLM'e gitmez) | `mobile` öneki + `.png` |
| `build.log` | **job seviyesi**; sentetik attachment (`device_id="build"`) | `build` + `.log` |

- **`mimeType` kimliğin parçası DEĞİLDİR:** `test.log` ile `test.properties` aynı cihazda aynı
  `text/plain`'dir; mime ile eşleştirildiğinde ikisi tek sınıfa düşüyor ve properties içeriği
  adım akışı bloğuna giriyordu.
- **Her kanıt gelmeyebilir.** Gözlenen setler: web 5 ek · mobil 4 ek · cihaz düşerse yalnız
  `test.log` (sebebi `properties` içinde: `ERROR: device disconnected`) · bazı joblarda senaryo
  bazlı hiçbir dosya yok — orada tek kanıt **build log**'dur (bkz. A8.2 `buildlog` şablonu).
- **Kayıt yeri:** `database/attachments/<run_id>/<scenario_id>/<deviceId><uzantı>`. Senaryo
  klasörü şart: bir koşumun her senaryosu kendi `browser.default.html`'ini üretir. Aynı senaryoda
  aynı ad ikinci kez gelirse `-2` eklenir (üzerine yazılmaz).
- **Tanınmayan ek düşürülmez:** dosya yine indirilip saklanır ve `evidence_report.unmatched`
  içine yazılır — "gelmedi mi, eşleşmedi mi?" sorusu tek koşumla cevaplanır.

### A4.4 Flaky senaryolar
Tekrar koşumda geçen senaryolar **analiz edilmez** (analiz edilecek hata yok).

---

## A5. Evidence Mimarisi

### A5.1 Sınıflar (8)
`TestLogEvidence` · `TestPropertiesEvidence` · `HtmlEvidence` · `MobileDomEvidence` ·
`BrowserLogEvidence` · `BuildLogEvidence` · `WebScreenshotEvidence` · `MobileScreenshotEvidence`.
Ortak `Evidence` arayüzü, registry'de kayıtlı, anahtar **`(device_id, extension)`**.
Yeni tip = 1 sınıf + 1 satır.

`TestPropertiesEvidence` ve `MobileDomEvidence` bugün **hiçbir profilde `evidence_to_llm`
içinde değildir**: saklanırlar, prompt'a girmezler. İstenirse config satırıyla açılır.

### A5.2 Profil kararları (`config/profiles.json`)

Profil bir job grubu için **üç** şeyi söyler:

| Alan | Anlamı |
|---|---|
| **`evidence_to_store`** | **İnecek** kanıtlar → diske + `database/` satırına ham hâliyle. **Listede olmayan ek hiç indirilmez** (istek de atılmaz). |
| **`evidence_to_llm`** | Prompt'a girecek kanıtlar. `evidence_to_store`'un **alt kümesi olmak zorunda** — indirilmeyen kanıt prompt'a giremez; ihlal **açılışta hata**. |
| **`rules`** | Her kanıt için içerik kuralları (A5.3) — **yalnız prompt'a giden kopyayı** kırpar. |

Ek olarak **`prompt`** (şablon adı, A8) ve **`extra_context`** (job grubu cümlesi).

**İndirmeyi profil belirler:** kaynak katmanı Evidence sınıflarını bilmez; kendisine
"bu ek isteniyor mu?" sorusunu soran bir yordam **enjekte edilir** (`fetch_job(run, wants)`).
Metadata (`deviceId`, `fileName`, `mimeType`) senaryo detayında indirmeden önce geldiği için
istenmeyen dosya için **hiç istek atılmaz**. İndirilmeyen ek kaybolmaz: satırı
`download_skipped` bayrağıyla durur, `evidence_report.skipped` içine yazılır.

> **Bedeli bilerek ödeniyor:** "her şeyi sakla" kuralı burada deliniyor. İndirilmeyen ek diskte
> **hiç olmaz**; sonradan bakılmak istenirse koşum yeniden analiz edilmeli.

**Hiçbir Evidence sınıfının sahiplenmediği dosya her zaman indirilir** — bakmadan yargılayamayız;
zaten `unmatched` olarak raporlanır ve yeni bir cihaz/dosya tipini ancak böyle fark ederiz.

**Profil seçimi:** çağıranın verdiği profil (job durumu `FAILED` → `job_failed`; araç → A20) →
`job_ids` eşleşmesi → **`default_web`**. Başka girdi yoktur. Eksik `default_web` **veya
`job_failed`**, yinelenen `job_id`, bozuk kural, **olmayan şablon adı**, **tanınmayan kanıt adı**,
**prompt'a istenip indirilmeyen kanıt** → **açılışta** hata.

> **`default_web` build log GÖNDERMEZ.** Build log yalnız açıkça tanımlanmış job gruplarında
> prompt'a girer.

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

> Aynı çizgi projede zaten var: blok etiketleri (`=== DOM ===`) ve alan başlıkları da config'te
> değil koddadır — onlar da karar değil, formattır. **Config = karar, kod = bilgi.**

### A5.4 Eksik kanıt toleransı
Beklenen kanıt yoksa sistem çökmez, ayrı bir `missing_evidence` alanı **YOKTUR**.
**Gelmeyen kanıt prompt'ta hiç görünmez — başlığıyla birlikte.** Bloğun başlığı şablonda elle
yazılmaz, placeholder'ın içinden gelir (A8.3); kanıt yoksa placeholder boş string olur ve
arkasında kalan boşluk kapatılır.

> Bu bilinçli bir **geri dönüş**. Önce `(bu kanıt alınamadı / bulunmuyor)` yer tutucusu vardı;
> amacı bloğun sessizce kaybolmasını engellemekti. Ama boş bir başlık da modelin kendine
> açıklaması gereken bir şey ve şablonun bir paragrafını "bu işaret normaldir" demeye harcıyordu.
> "Gelmedi mi, eşleşmedi mi, profil mi istemedi?" sorusunun yeri prompt değil,
> `evidence_report`'tur (A5.5).

### A5.5 Kanıt eşleşme raporu (`evidence_report`) — YENİ
Her senaryo için `evidence` satırına yazılır:
- **`attachments`** — gelen her dosya: `file_name`, `mime_type`, `device_id`, eşleştiği Evidence
  sınıfı (**`""` = eşleşmedi**), profil onu LLM'e gönderiyor mu, kaç karakter geldi.
- **`blocks`** — prompt'a giden her blok: kaç karakter, dolu mu, kuralları gerçekten kesti mi.
- **`unmatched`** — hiçbir Evidence sınıfının sahiplenmediği dosya adları.
- **`skipped`** — profilin istemediği, bu yüzden **hiç indirilmemiş** dosya adları.

**Neden:** "DOM gelmedi mi, geldi de eşleşmedi mi?" sorusu sonradan cevaplanamıyordu. Artık tek
gerçek koşum cevabı kendi yazıyor. `BUILD LOG` bloğu `trimmed=false` + ham log boyutunda ise
dilimleme kuralı işaretini bulamamış demektir.

---

## A6. Findings Sözleşmesi (Halka 2 → 3)

`scenario_name` · `failed_step` · `error_message` · `steps` ·
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
| `mobile.txt` | test log (+ istenirse mobil UI ağacı: `$mobile_dom`) |
| `hybrid.txt` | tek akışta hem web hem mobil adım |
| `buildlog.txt` | senaryo bazlı kanıt üretmeyen joblar; **tek kanıt build log** |
| `_contract.txt` | **ortak çıktı sözleşmesi** — şablon değil |

Profil şunu der: `"prompt": "mobile"`. Demezse `default`.

### A8.2 Ortak sözleşme neden ayrı dosyada
JSON şeması + 6 verdict + 5 confidence kovası **tek yerde** yazılır ve her şablonun sonuna
sistem ekler. 5 şablonda elle bakım edilen bir şema er geç dolar; bir harf kayınca parse
**sessizce** bozulur. Şablon yazarı yalnız üst kısmı yazar.

### A8.3 Placeholder'lar
Ortak: `$scenario_name` `$failed_step` `$error_message` `$steps` `$extra_context`
`$confidence_buckets` · Toplu yerleşim: `$evidence_blocks` ·
**Kanıt bazlı:** `$test_log` `$dom` `$mobile_dom` `$browser_log` `$build_log` `$test_properties`.

`$parameter1` / `$parameter2` **yoktur** (A4.2) — tanınmayan placeholder olarak açılışta hata
verirler. Kullanılamayacak bir kanal bırakmak, er geç kullanılmasını sağlıyordu.

**Başlık placeholder'ın içindedir.** Şablon `=== DOM ===` yazmaz, yalnız `$dom` koyar; alan ya
`=== DOM ===` + içerik olarak açılır ya da **tamamen boş** kalır (A5.4). Aynısı sabit alanlar
için de geçerli: `$failed_step` → `=== PATLAYAN ADIM ===`, `$error_message` → `=== HATA MESAJI ===`,
`$steps` → `=== ADIM SONUÇLARI ===`. Düşen alanın bıraktığı boşluk kapatılır, yoksa prompt'un
şekli eksik olanı ilan eder.

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

**Sistem tarafı meta:** `profile_name` · `truncated(_note)` ·
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
- **`runs`** — koşum durumu, parametreler, senaryo sayıları, `note`, ham job cevapları,
  **`build_log`** + **`build_log_error`**
- **`analysis_results`** — her senaryonun teşhisi (yarın Oracle'a taşınacak asıl tablo)
- **`evidence`** — ham senaryo dökümü + **`evidence_report`** (A5.5)
- **`prompts`** — GİDEN: tam prompt + istek + **`prompt_chars`**
- **`llm_responses`** — GELEN: ham zarf + içerik + çağrı meta'sı

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

**Bitti:** Halka 1-6 gerçek gerçeklemeleriyle · **koşum çözümlemesi + job durumu dallanması
(A4.0)** · **`deviceId`+uzantı ile kanıt eşleşmesi, ayrı `.xml`/`.properties` kanıtları,
önyüz adıyla senaryo bazlı kayıt** · **profile bağlı indirme + boş bloğun prompt'tan düşmesi +
`tools/inspect_run` (A20)** · job bazlı profiller + 9 içerik kuralı ·
**job grubuna göre prompt şablonu (5 şablon + ortak sözleşme)** · PreCheck kural motoru ·
GET sadeleştirmesi · config katılığı · **build log hata sebebi** ·
**kanıt eşleşme raporu** · **kanıtsız senaryoda LLM'e gitmeme** · **prompt sürümü** ·
**ölçüm iskeleti**.

**Kalan:**
- Gerçek VisiumGo + gerçek LLM ile uçtan uca doğrulama (iş-pc).
- **Gerçek profilleri gerçek `job_ids` ile doldurmak** (config işi) — asıl kalan iş bu.
- **`job_failed` profilinin içeriği** bilerek boştur: gerçek bir FAILED job'ın kanıtı
  görülmeden doldurulmaz.
- **Faz 3 başlıkları:** profillerin gerçek `job_ids` ile doldurulması · `job_failed` içeriği ·
  şablon metinleri · `properties.failedStep.*` kullanımı · prompt boyutu ölçümü (340k karakter →
  timeout) · `MAX_CONCURRENCY` · build log dilimlemesinin gerçek logla doğrulanması.
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
5. `parameter1`/`parameter2` **ayrılmış anahtardır**: kaydedilir, gösterilir, hiçbir kararı
   etkilemez (A4.2).
6. Evidence mimarisi: 8 sınıf, profil bayrakları, 9 kural tipi, global trimmer yok.
7. **Kanıt kimliği `deviceId` + uzantıdır** (önyüzdeki adın aynısı); `mimeType` kimliğin parçası
   değildir. Mobil UI ağacı **ayrı `.xml` dosyası** olarak gelir (eski "test.log içinde gelir"
   kaydı gerçek koşumla çürütüldü).
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
27. **`default_web` profil build log göndermez;** build log yalnız tanımlı job gruplarında gider.
28. **`parameter1`/`parameter2` koddan tamamen çıkarıldı:** ne profil seçer, ne `Findings`'e
    taşınır, ne prompt yer tutucusu vardır. Yalnız `runs` satırında durur ve `GET` ile görünür.
29. **Job durumu analiz kararıdır (A4.0):** `RUNNING` → hiç indirme yok, koşum `failed`;
    `FAILED` → sabit `job_failed` profili; koşum seçimi `startTime` değil **en büyük `id`**.
30. **Ekler önyüzdeki adıyla, senaryo klasörü altında saklanır**
    (`<run_id>/<scenario_id>/<deviceId><uzantı>`); tanınmayan ek de saklanır ve raporlanır.
31. **Servis metotları tek amaçlı ve public'tir** (`get_run`, `list_runs`, `get_results`,
    `get_scenario_detail`, `download_attachment`, `fetch_build_log`): sırayı `fetch_job` kurar,
    metotlar sırayı bilmez. Bu, aynı servislerin ileride sırayı kendi kuran bir katmandan
    kullanılabilmesi içindir — bugün böyle bir katman **yoktur** (A2 hâlâ geçerli).
32. **Profil üç şeyi söyler:** hangi kanıt **iner** (`evidence_to_store`) · hangisi **prompt'a
    girer** (`evidence_to_llm`, store'un alt kümesi; ihlal açılışta hata) · **nasıl trimlenir**
    (`rules`, yalnız prompt kopyası). Listede olmayan ek indirilmez; kararı profil verir, kaynak
    uygular (enjekte edilen yordam).
33. **Gelmeyen kanıt prompt'ta hiç görünmez — başlığıyla birlikte.** Yer tutucu metin yoktur;
    "gelmedi mi, eşleşmedi mi, istenmedi mi" sorusunun yeri `evidence_report`'tur.
34. **Fallback profil `default_web`.** `config/profiles.example.json` **yoktur** — tek kaynak
    `profiles.json`.
35. **`tools/inspect_run.py` gerçek LLM'e asla gitmez** ve `test_all` profilini zorlar (A20).
36. **Önbellek YOKTUR.** Her istek, adlandırdığı koşumu baştan analiz eder; sonuç yeniden
    kullanılmaz. Kullanılmayan ve `note` alanı yüzünden zaten çoğu koşumu dışarıda bırakan
    mekanizma kaldırıldı (sadeleştirme).

---

## A18. Job-level analiz — yönlendirme var, içerik Faz 2'de

Job'ın **kendisi** patladığında (gradle build alınamadı, ortam ayağa kalkmadı) senaryo bazlı kanıt
üretilmez; o koşumu normal bir koşum gibi analiz etmek yanlış olur.

**Bugün yapılan (A4.0):** durum değerleri artık **biliniyor** — `PASSED` / `FAILED` / `RUNNING`.
`state == FAILED` ise `job_ids` eşlemesine bakılmadan sabit **`job_failed`** profiline gidilir ve
bu, koşum satırının `note` alanına yazılır. Yönlendirme tek registry satırıdır.

**Bugün YAPILMAYAN:** `job_failed` profilinin içeriği. `evidence_to_llm` bilerek **boştur**:
gerçek bir FAILED job'ın kanıtı (build log'un o hâlde ne söylediği) görülmeden doldurulursa
uydurma olur (B3.3/B3.13). Faz 2'de doldurulacak; şablonu (`buildlog.txt`) ve depolama listesi
hazır bekliyor.

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


---

## A20. Kontrol aracı — `tools/inspect_run.py`

```bash
python -m tools.inspect_run --run-id 148918      # ya da --job-id 886
```

Gerçek zinciri koşturur (koşum çöz → ekleri indir → sınıfa eşle → prompt kur) ve **ne geldi, ne
gelmedi, prompt kaç karakter** sorusunu tek komutta cevaplar. `evals/` gibi geliştirme aracıdır;
`app/` onu import etmez.

İki garanti, ikisi de bilerek:

- **Gerçek LLM'e asla gitmez.** Servis `.env` ne derse desin `mock` sağlayıcıyla kurulur; bunu
  değiştiren bir bayrak **yoktur**. Bu bir tesisat kontrolüdür, analiz değil — on-prem modeli
  meşgul etmemeli.
- **`test_all` profili zorlanır**, yani her ek indirilir. Sorulan soru "her şey inebiliyor mu",
  "bu job'ın profili neyi tutardı" değil. Zorlama `run_analysis(profile_override=...)` ile
  yapılır, koşum satırının `note`'una da yazılır.

**Çıkış kodu 1:** hiçbir sınıfın sahiplenmediği ek · indirildiği hâlde **diskte olmayan** dosya.
Job seviyesindeki build log dosya beklemez, "JOB LOGU" olarak işaretlenir. Böylece araç gözle
okunan bir rapor değil, cevap veren bir komuttur.

`--run-id`/`--job-id` verilmezse dosyanın başındaki `DEFAULT_RUN_ID` / `DEFAULT_JOB_ID` sabitleri
kullanılır: iş bilgisayarında tek komut.

---

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
