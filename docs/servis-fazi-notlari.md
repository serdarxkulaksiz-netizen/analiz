# Servis Fazı — Plan (2026-09-08)

> Bu faz **Halka 1 (VisiumGo kaynak katmanı) + kanıt tanıma/kaydetme** ile sınırlıdır.
> Prompt, profil içeriği ve kanıt kırpma **kapsam dışıdır** — hepsi Faz 2'de.
> Faz 1'in tek hedefi: **her veriyi ham ve eksiksiz, doğru isimle alabilmek.**
>
> **Durum: Faz 1 kodlandı** (2026-09-08). Ne yapıldığı `CHANGELOG.md`'nin son bölümünde,
> kalıcı hâli `plan.md`'de (A4.0, A4.2, A4.3, A5.1, A8.3, A17/28-31, A18).

## Kilitli kararlar (bu oturumda alındı)

| # | Karar |
|---|---|
| S1 | `run_id` verilirse **önce** `GET /api/runs/{run_id}` çağrılır; profil, cevaptaki `jobId` ile seçilir. |
| S2 | `runResult.state` **job sağlığıdır** (senaryo değil): `PASSED` / `FAILED` / `RUNNING`. |
| S3 | `state == FAILED` → profil eşlemesine **bakılmadan** sabit `job_failed` profiline gidilir. |
| S4 | `state == RUNNING` (run_id yolu) → **hata**; hiçbir log/ek indirilmez, analiz başlamaz. |
| S5 | `job_id` yolunda koşum seçimi: `RUNNING` elenir, kalan `PASSED`/`FAILED` içinden **en büyük `id`**. `startTime` sıralaması bırakılır. |
| S6 | Profil, kullanıcının verdiği `job_id` ile seçilir (run detayından türetilmez). |
| S7 | `parameter1` / `parameter2` prompt'a **kadar taşınır ama prompt'a yazılmaz**; yapı ileride açılabilir kalır. |
| S8 | Kanıt kimliği **`deviceId` + dosya uzantısı** (önyüzdeki etiketin aynısı). `mimeType` tek başına yetmez. |
| S9 | Ekler `attachments/<run_id>/<scenario_id>/<deviceId><uzantı>` altına, **her biri ayrı** kaydedilir. |
| S10 | `test.properties` ve mobil DOM (`.xml`) Faz 1'de **yalnız saklanır**, prompt'a girmez. |
| S11 | `properties.failedStep.*` şimdilik kullanılmaz (saklanır, bekler). |
| S12 | Tanınmayan ek artık **sessizce düşmez**; `evidence_report`'a yazılır. |
| S13 | Kaynak metotları agent'a hazır olacak şekilde **public + dönüş şeması dokümante**; davranış değişmez. |

---

## Servis referansı (gerçek cevaplardan doğrulandı)

### 1. `GET /api/runs?jobId={job_id}` — bir job'ın koşumları
```json
[{ "id": 149132, "jobId": 867, "jobName": "tor-mobile-log-ios", "userId": 0,
   "startTime": "2026-09-08T12:31:24.580678", "duration": 358540,
   "runResult": { "state": "PASSED", "totalScenarios": 1, "failScenarios": 1,
                  "passScenarios": 0, "unstableScenarios": 0 } }]
```
`id` = run_id. Liste elemanı, tek koşum detayıyla **aynı şemada**.

### 2. `GET /api/runs/{run_id}` — tek koşum *(YENİ — bugün çağrılmıyor)*
Yukarıdaki nesnenin tekli hâli. `state` burada da job sağlığıdır.
**Not:** örnek bir cevapta `state: "PASSED"` iken `failScenarios: 2` — yani `state`,
senaryo başarısını değil job'ın kendisinin çalışıp çalışmadığını söyler.

### 3. `GET /api/runs/{run_id}/logs` — build log
ZIP döner; içinden `build.log` çıkarılır. Mevcut, çalışıyor.

### 4. `GET /api/runs/{run_id}/results` — koşumun senaryoları
```json
[{ "id": "1:ParaTransferBloke/Bireysel/Havale.feature:610_1087272681:1",
   "jobId": "719", "name": "...", "resultType": "FAILED", "duration": 121119,
   "runId": 149126, "retryNumber": 1, "dateTime": "...",
   "featureName": "Havale", "feature": "...", "jobStep": "1" }]
```
`resultType`: `FAILED` | `PASSED` | `UNSTABLE`. **Sadece `FAILED` alınır.**
`UNSTABLE` başarılı sayılır, hiçbir şekilde ele alınmaz.
Her senaryo listede **bir kez** geçer (retry ayrı satır değildir).
`jobId` burada **string**, `/api/runs`'ta **sayı** → tip normalizasyonu gerekli.

### 5. `GET /api/runs/{run_id}/results/{scenario_id}` — senaryo detayı
```json
{ "id": "...", "name": "...", "resultType": "FAILED", "duration": 164277,
  "runId": 0, "retryNumber": 0,
  "errorText": "Expected condition failed: ...",
  "dateTime": "...",
  "stepResults": [{ "stepType": "STEP", "line": "...", "dateTime": "...",
                    "resultType": "PASSED|FAILED|SKIPPED", "duration": 4042, "stepLine": "7" }],
  "attachments": [{ "startTime": 1788858271109, "duration": 0,
                    "deviceId": "mobile.ios.iPhone 13 Pro Max",
                    "mimeType": "image/png",
                    "fileName": "-1643527934/mobile.ios.iPhone 13 Pro Max_779188588.png" }],
  "properties": { "<deviceId>": "Name:...-UDID:...",
                  "retryNumber": "1",
                  "failedStep.name": "...", "failedStep.line": "143",
                  "failedStep.location": "src/test/resources/features/...feature:143" } }
```
**Detaydaki `runId` ve `retryNumber` güvenilmez** (0 geliyor); gerçek değer listede ve
`properties`'tedir. Kullanılmıyor.

### 6. `GET /api/runs/{run_id}/attachments/{fileName}` — ek indirme
`fileName` içinde `/` ve boşluk var; tamamı tek path segmenti olarak encode edilir.

### Ek (attachment) deseni

Önyüz etiketi = **`deviceId` + uzantı**. Ham `fileName` = `<klasör>/<deviceId>_<sayı>.<uzantı>`
(ortadaki sayı yalnız benzersizlik içindir; `test.properties`'te yoktur).

| deviceId | uzantı | mimeType | ne |
|---|---|---|---|
| `browser.default` | `.html` | text/html | sayfa DOM'u |
| `browser.default` | `.log` | text/plain | tarayıcı konsolu |
| `browser.default` | `.png` | image/png | web ekran görüntüsü |
| `mobile.<platform>.<cihaz>` | `.xml` | text/xml | **mobil DOM (yeni — artık ayrı dosya)** |
| `mobile.<platform>.<cihaz>` | `.png` | image/png | mobil ekran görüntüsü |
| `test` | `.log` | text/plain | adım akışı |
| `test` | `.properties` | text/plain | **yeni — koşum özellikleri** |

Gözlenen setler: web = 5 ek · mobil = 4 ek · **cihaz düşerse yalnız `test.log`**
(sebep `properties` içinde: `"...-ERROR: device disconnected"`) · bazı joblarda **hiç ek yok**
(o joblarda tek kanıt build log'dur).

---

## İş kalemleri

### 1. Koşum çözümlemesi tek yere iniyor

- Yeni public metot: **`get_run(run_id)`** → `GET /api/runs/{run_id}`.
- Yeni public metot: **`list_runs(job_id)`** → `GET /api/runs?jobId=`.
- `resolve` sonucu tek bir **koşum özeti** nesnesi: `run_id`, `job_id`, `job_name`,
  `state`, `run_result`, ham cevap.
- `run_id` yolu → `get_run`; `job_id` yolu → `list_runs` + seçim kuralı (S5).
- `job_id` yolunda **bilinmeyen bir `state`** (ör. `ABORTED`) elenirse bu **sessiz olmaz**,
  koşum satırına not düşülür.
- Uygun koşum kalmazsa (hepsi RUNNING) → anlaşılır hata.
- `fetch_job` **artık çözümleme yapmaz**, çözülmüş id ile çağrılır → bugünkü
  **çift `/api/runs?jobId=` çağrısı** biter, `run_id` yolunda `raw_run` boş kalmaz.
- `jobId` her yerde `str()` ile normalize edilir (S: `886` ↔ `"886"` eşleşmesi).

### 2. `state` dallanması (tek noktada)

- `PASSED` → bugünkü senaryo analizi.
- `FAILED` → sabit **`job_failed`** profili; `job_ids` eşlemesine bakılmaz.
  Profil `config/profiles.json` + `profiles.example.json`'a **boş iskelet** olarak eklenir,
  içeriği Faz 2'de doldurulur.
- `RUNNING` (run_id yolu) → hata; build log dahil **hiçbir istek atılmaz**.
- Dallanma koda dağılmış `if` değil, **tek lookup** (B3.1).

### 3. `parameter1` / `parameter2`

- Findings'te taşınmaya devam eder; **varsayılan şablonlardan çıkarılır**, prompt'a yazılmaz.
- Placeholder mekanizması durur: istenirse bir job'ın şablonuna geri eklenebilir.
- `parameter1`'in **profil override'ı** görevi aynen kalır (bu prompt işi değil).
- `README.md`, `docs/proje-rehberi.md`, `docs/nasil-calisir.md`, `docs/akis-semasi.md`,
  `plan.md` bu değişikliğe göre güncellenir.

### 4. Kanıt tanıma: `deviceId` + uzantı

- Eşleşme anahtarı `mimeType + deviceId`'den **`deviceId` (önek) + uzantı**'ya geçer.
- Yeni kanıt türleri: **`MobileDomEvidence`** (`.xml`), **`TestPropertiesEvidence`**
  (`.properties`). İkisi de Faz 1'de yalnız saklanır (S10).
- Bu, bugünkü **gerçek bir hatayı** kapatır: `test.log` ile `test.properties` aynı
  `text/plain` + `test` olduğu için aynı türe düşüyor, ikisi de aynı prompt bloğuna giriyordu.
- **Tanınmayan ek** artık `continue` ile yok sayılmaz: `evidence_report`'a
  `deviceId + uzantı + fileName` ile "tanınmadı" satırı yazılır.

### 5. Kayıt düzeni

- `attachments/<run_id>/<scenario_id>/<deviceId><uzantı>`.
- `scenario_id` içindeki `/` ve `:` dosya adı güvenli hâle getirilir.
- Aynı senaryoda aynı `deviceId`+uzantıdan ikinci ek gelirse `-2` eklenir ve
  bu durum `evidence_report`'a yazılır — sessizce üzerine yazılmaz.

### 6. Agent'a hazırlık (maliyetsiz kısım)

- `get_run`, `list_runs`, `get_results`, `get_scenario_detail`, `download_attachment`,
  `fetch_build_log` → **public**, tek amaçlı, dönüş şeması docstring'de.
- `fetch_job` zinciri aynen kalır; davranış ve testler değişmez.
- Tool şeması, agent döngüsü, yeni tablo **yazılmaz** (B3.13).

### 7. Mock kaynak gerçeğe hizalanır

- `MockSource`, yeni ek türlerini (`.xml`, `.properties`) ve `properties` alanını üretir.
- `state` üç değeri de mock'ta üretilebilir (job_id sonekiyle, veri koşulu olarak).
- Aksi hâlde Mac'te yeşil olan testler iş-pc'de gerçeği temsil etmez.

### 8. Doğrulama

- `pytest` · `ruff check .` · `ruff format --check` · `mypy` — dördü de temiz.
- Yeni testler: koşum seçimi (RUNNING eleme + max id) · `state` dallanması ·
  `deviceId`+uzantı eşleşmesi · `test.log`/`test.properties` ayrımı · ek kayıt yolu ve
  çakışma · tanınmayan ek raporu.
- İş-pc'de ilk koşum: **her ekin diske düşüp düşmediği** ve `evidence_report`.

---

## Faz 2 — Plan: profil sözleşmesi, boş blok temizliği, kontrol aracı

> **Durum: Faz 2 kodlandı** (2026-09-09). Ayrıntı `CHANGELOG.md`'nin son bölümünde; kalıcı hâli
> `plan.md`'de (A5.2, A5.4, A5.5, A8.3, A20, A17/32-35).

> **Kapsam:** profilin *mekanizması*. Profillerin **içeriği** (gerçek `job_ids`, kurallar,
> şablon metinleri) **Faz 3**'te doldurulacak — bu fazda hiçbir job grubu tanımlanmaz.

### Kilitli kararlar (Faz 2)

| # | Karar |
|---|---|
| F1 | Profil üç şeyi söyler: **hangi kanıt iner ve DB'ye yazılır** (`evidence_to_store`) · **hangisi prompt'a girer** (`evidence_to_llm`) · **nasıl trimlenir** (`rules`). |
| F2 | Hiçbir listede olmayan ek **indirilmez**. Metadata'sı ve "profil istemedi" notu `evidence_report`'a yazılır — dosya yok ama bilgisi var. |
| F3 | `evidence_to_llm`'de olup `evidence_to_store`'da olmayan kanıt → **açılışta hata** (config sessizce yalan söylemez). |
| F4 | Trim **yalnız prompt'u** etkiler; `database/` altındaki ham içerik tam kalır. |
| F5 | **Gelmeyen kanıt prompt'ta hiç görünmez — başlığıyla birlikte.** `(bu kanıt alınamadı / bulunmuyor)` yer tutucusu kalkar; şablonlardaki "eksik kanıt normaldir" paragrafı silinir. İstisna yok, `=== HATA ===` dahil. |
| F6 | Fallback profil adı `default` → **`default_web`**. `parameter1`/`parameter2`'ye **dokunulmaz** (ileride kullanılmak üzere duruyorlar). |
| F7 | Profil seti: **`test_all`** (araç profili) · **`default_web`** (fallback) · **`job_failed`**. `config/profiles.example.json` **silinir**. |
| F8 | **`tools/inspect_run.py`**: tek komut, her zaman `test_all`, **hiçbir koşulda gerçek LLM'e gitmez**. |

---

### 1. İndirme kapısı — profil kararı, kaynak uygular

Bugün `VisiumGoSource` **her eki** indiriyor; profil ise iki halka sonra çözülüyor. İndirmeyi
profile bağlamak için kaynağın "bu ek isteniyor mu" sorusunu sorabilmesi lazım — ama kaynak
Evidence sınıflarını **bilmemeli** (katman ters çevrilmez).

Çözüm: karar dışarıdan enjekte edilir.

```python
# Halka 1: kaynak yalnız "isteniyor mu?" diye sorar, cevabı bilmez.
async def fetch_job(self, run: RunSummary, wants: AttachmentFilter = accept_all) -> JobData
```

- `wants(attachment_metadata) -> bool`. Metadata (`deviceId`, `fileName`, `mimeType`) senaryo
  detayında **indirmeden önce** geldiği için karar indirmeden verilebilir.
- Servis bu fonksiyonu profilden üretir (profil zaten orada çözülüyor: `forced_profile` +
  `profile_job_id`), Evidence eşleşmesini bilen tek katman yine `app/evidence/` kalır.
- İndirilmeyen ek **kaybolmaz**: `Attachment` metadata'sıyla döner, yeni bir bayrakla
  (`download_skipped`) işaretlenir, `evidence_report`'ta "profil istemedi" satırı olur.
- `test_all` her şeye `True` döner → araç tam kapsam görür.

**Bedeli açıkça yazılsın:** "her şeyi sakla" kuralı bilerek deliniyor. İndirilmeyen ek diskte
**hiç olmaz**; sonradan bakılmak istenirse koşum yeniden analiz edilmeli.

### 2. Boş blok = hiç blok (prompt temizliği)

Bugün şablonda `=== DOM ===` **elle yazılı**, altına `$dom` konuyor; kanıt gelmeyince başlık
duruyor, altına yer tutucu yazılıyor.

- Başlık **placeholder'ın içine** taşınır: `$dom` ya `=== DOM ===\n<içerik>` olarak açılır ya da
  **boş string**. Şablon yerleşimi kontrol etmeye devam eder, gelmeyen kanıt başlığını da götürür.
- `EVIDENCE_UNAVAILABLE` sabiti ve extraction'ın "yer tutucu blok ekleme" adımı **kaldırılır**.
- Beş şablondaki **"KANIT HAKKINDA (ÖNEMLİ)"** paragrafı silinir: modele artık hiç görmeyeceği
  bir işaret anlatılmaz.
- `has_evidence_for_llm` sadeleşir (yer tutucu ayıklaması gereksizleşir).
- `plan.md` A5.4 + kilitli karar listesi buna göre yeniden yazılır — bu bilinçli bir **geri
  dönüş**: yer tutucu, modelin "kanıt eksik" diye rapor yazmasını engellemek için konmuştu;
  blok hiç gitmeyince o risk de ortadan kalkıyor.

### 3. Profil seti + isim değişikliği

| Profil | `job_ids` | Rol |
|---|---|---|
| `test_all` | boş | Her kanıt iner + prompt'a girer, trim yok. Yalnız `tools.inspect_run` kullanır. |
| `default_web` | boş | **Fallback**: hiçbir profile eşleşmeyen job. Web şeklinde. |
| `job_failed` | — | `runResult.state == FAILED` koşumları (Faz 1'de eklendi). |

- `DEFAULT_PROFILE_NAME` sabiti `"default_web"` olur; `parameter1 == "default"` API sentinel'i
  **aynen kalır** (o "override yok" demektir, profil adı değildir).
- `config/profiles.example.json` ve onu doğrulayan test **silinir**; yerine `profiles.json`'ın
  kendisini doğrulayan test kalır. İki kaynağı bakım etmek bayatlama üretiyordu.
- **Bilinerek alınan risk:** fallback web şeklinde olduğu için, tanımlanmamış bir **mobil** job
  zayıf bir prompt'la analiz edilir. Job tanımlanınca düzelir; Faz 3'ün işi.

### 4. `tools/inspect_run.py` — tek komutluk kontrol

```bash
python -m tools.inspect_run --run-id 148918      # ya da --job-id 886
```

- `evals/` gibi **geliştirme aracı**: `app/` içinden import edilmez, `mypy` kapsamında.
- `--run-id` / `--job-id` verilmezse dosyanın başındaki `DEFAULT_RUN_ID` / `DEFAULT_JOB_ID`
  sabitleri kullanılır (iş bilgisayarında tek komut).
- **Profil:** her zaman `test_all` (Faz 1'in "zorla profil" mekanizmasıyla; `parameter1`
  kullanılmaz).
- **LLM:** servis `.env`'den bağımsız olarak **`mock` sağlayıcıyla** kurulur. Gerçek modele
  gitmenin yolu yoktur — bayrak da yok.
- **Basar:**
  - Koşum: `run_id` · `jobId` · `jobName` · `state` · toplam/başarısız senaryo ·
    build log karakter sayısı, alınamadıysa sebebi
  - Senaryo başına her ek: `deviceId+uzantı` · bayt · **diskte var mı** · eşleştiği Evidence
    sınıfı (eşleşmeyen ayrıca işaretli)
  - Prompt'a girecek bloklar: etiket · karakter · kural kesti mi
  - `prompt_chars` toplamı (timeout'un tek gerçek göstergesi)
- **Çıkış kodu 1:** eşleşmeyen ek · diskte olmayan dosya · profilin istediği hâlde gelmeyen kanıt.
  "Gözle bak" değil, cevap veren bir komut.

### 5. Doğrulama

`pytest` · `ruff check .` · `ruff format --check` · `mypy` (artık `tools/` de kapsamda).
Yeni testler: indirilmeyen ekin raporlanması · `evidence_to_llm ⊄ evidence_to_store` açılışta
hata · boş kanıtın başlığıyla birlikte prompt'tan düşmesi · `default_web` fallback'i ·
`inspect_run`'ın gerçek LLM'e gitmemesi ve çıkış kodu.

### Kapanan açık nokta

Önbellek anahtarı `run_id + parameter1 + parameter2` idi; parametreler koddan çıkınca yalnız
`run_id` kaldı, ardından **önbellek sistemi tamamen kaldırıldı** (geliştirme aşamasındayız,
mekanizma kullanılmıyordu ve `note` alanı yüzünden sağlıklı koşumların çoğunu zaten dışarıda
bırakıyordu). Artık her istek, adlandırdığı koşumu baştan analiz eder.

---

## Faz 3 (sonraki) — profiller ve prompt'lar

Gerçek `job_ids` ile profillerin doldurulması · `job_failed` içeriği · şablon metinleri ·
`properties.failedStep.*` kullanımı · prompt boyutu ölçümü (`prompt_chars`) ve gerekiyorsa
`max_chars` · `MAX_CONCURRENCY` · build log dilimlemesinin gerçek logla doğrulanması.
