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

## Faz 2 (kapsam dışı — kayıt için)

1. Eşleştirmenin config'e taşınması (`evidence_map`).
2. İndirmeyi profile bağlama: profilin istemediği ek **hiç indirilmesin**
   (kazanç büyük, ama "her şeyi sakla" kuralını deler — konuşulacak).
3. Profillerin gerçek `job_ids` ile doldurulması, `job_failed` profilinin içeriği.
4. `properties.failedStep.*` ve cihaz hata metninin (`ERROR: device disconnected`) kullanımı.
5. Prompt tarafı: boyut (340k karakter → timeout), `strip_tags` + `collapse_whitespace`,
   `MAX_CONCURRENCY`, mobil DOM ve `test.properties`'in prompt'a girip girmeyeceği.
6. Build log dilimlemesinin gerçek log ile doğrulanması (marker eşleşmezse tüm log
   her senaryonun prompt'una giriyor).
