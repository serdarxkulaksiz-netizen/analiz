# VisiumGo Test Analyzer

Başarısız otomasyon test koşumlarının ham kanıtını
(test.log, DOM, browser.log, ekran görüntüsü) lokal bir LLM'e yorumlatan FastAPI
backend. Çıktı: **güven seviyeli, gerekçeli ön teşhis** — "test hatası mı,
uygulama hatası mı, ortam mı, geçici mi (yoksa unknown/inconclusive mı)?"

Mimari ve tüm kararlar için tek doğru kaynak: [`plan.md`](plan.md) (v3).
Yapım geçmişi ve açık noktalar: [`CHANGELOG.md`](CHANGELOG.md).

## Mimari (tak-çıkar halkalar)

```
Source → Extraction → [PreCheck] → Prompt → LLM (tek atış) → Parse (JSON) → Persist + API
```

`PreCheck` eşleşirse Prompt + LLM **atlanır**; varsayılan `NoOpPreCheck` hiç eşleşmez.
Prompt'a girecek **hiçbir kanıt yoksa** da LLM çağrılmaz: senaryo `status="no_evidence"` ile
kaydedilir (boş prompt'un cevabı zaten "kanıt yok" olurdu).

- **Davranış dallanması YOK:** `if mock` / `if type ==` yerine
  ayrı sınıf + arayüz + registry + DI. Yeni varyant = registry'ye bir satır.
- **Agentless / tek-atış:** senaryo başına tek prompt, tek LLM çağrısı; tool-calling yok.
- **Parse-minimal:** ham kanıt etiketli bloklar halinde LLM'e gider; alan-parser yok.
- **Job bazlı özelleştirme:** `config/profiles.json`'daki **analiz profili**,
  `job_id`'ye göre otomatik seçilir (`parameter1` ile elle ezilebilir). Profil
  hem *hangi kanıt* prompt'a girer hem de *o kanıtın içine ne yapılır*
  (kes/seç/ekle) belirler. Yeni job = **config'e satır**, kod değişmez.
- **Evidence mimarisi:** 6 kanıt sınıfı + registry (`mimeType`+`deviceId` eşleme);
  her kanıtın content selector'ı profil kurallarını uygular.
- **Her şey kaydedilir, az şey gösterilir:** VisiumGo'dan gelen tüm ham cevaplar (run, results,
  senaryo detayı, attachment dosyaları, build log) `database/` altına yazılır; **GET cevabı**
  yalnız LLM'in teşhisini döndürür.
- **Config katıdır:** `.env`'de tanınmayan bir anahtar **açılışta hata** verir — yazım hatası
  ya da yeniden adlandırılmış ayar sessizce yok sayılmaz.
- **PreCheck:** varsayılan `NoOpPreCheck` (her senaryo LLM'e gider); `PRECHECK_PROVIDER=rules`
  ile bilinen hatalara LLM'e hiç gitmeden hazır cevap dönülür (kural listesi config'te, boş gelir).
- **DB simülasyonu:** `database/<tablo>/<id>.json`; Repository arayüzü arkasında
  (ileride SQLite/Oracle tak-çıkar).
- **Halka 1-2 gerçek:** `VisiumGoSource` gerçek API'ye bağlı (run çöz → FAILED
  senaryolar → detay → attachment indir); `deviceId`+`mimeType` ile Evidence
  eşlenir. `.env` boşken/`SOURCE_PROVIDER=mock` iken mock'larla uçtan uca çalışır.
- **Mock etiketleme:** tüm mock çıktıları `MOCK_` ile başlar (gerçek veriyle karışmasın).
- **Docker yok** (iş bilgisayarında mevcut değil).

## Kurulum

Gereksinim: Python 3.11+

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

### Windows (PowerShell)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

## Çalıştırma

```bash
uvicorn app.main:app --reload
```

`.env.example`'daki varsayılanlar her şeyi mock ile çalıştırır (dış bağımlılık yok):

```bash
# analizi başlat (hemen analyzer_run_id döner, arka planda çalışır)
# parameter1/parameter2 opsiyonel (verilmezse "default") — analiz profilini seçer
# job_id VEYA run_id verilir (ikisi de olursa run_id kazanır)
curl -X POST http://127.0.0.1:8000/analyze/visiumgo \
  -H "Content-Type: application/json" \
  -d '{"job_id": "job-42"}'

# özelleştirilmiş analiz (config/profiles.json'daki profil seçilir)
curl -X POST http://127.0.0.1:8000/analyze/visiumgo \
  -H "Content-Type: application/json" \
  -d '{"parameter1": "projeX", "parameter2": "minimal", "job_id": "job-42"}'

# durumu / sonuçları sorgula
curl http://127.0.0.1:8000/analyze/visiumgo/<analyzer_run_id>
```

**GET cevabı sadedir:** yalnızca LLM'in verdiği teşhis + koşum durumu döner
(`verdict`, `explanation`, `suggestion`, `confidence`, … + `status`, `meta`, `result_id`).
Ham veriler (`raw_run_response`, `raw_results_response`, `build_log`, `raw_llm_response`,
`screenshot_paths`, `profile_name` …) API cevabında **yoktur** — hepsi `database/` altında
tam hâliyle durur. `result_id` ile bir teşhisin ham izine ulaşılır.
İstisna: bir şeyin *alınamadığını* söyleyen kısa alanlar (`note`, `build_log_error`) cevapta
kalır — kanıtın içeriği değil, koşumun durumudur.

Tam iz `database/` altına düşer: `runs/` (koşum durumu + ham API cevapları + build log),
`evidence/` (ham kanıt), `prompts/` (**giden**: prompt + istek),
`llm_responses/` (**gelen**: LLM'in tam ham cevabı), `analysis_results/`
(teşhisler + sistem meta'sı). Hepsi insan-okunur JSON.

Mock kolaylığı: `job_id` sonu `-clean` biterse job hatasız kabul edilir
("analiz edilecek hata yok" yolu).

## Job bazlı özelleştirme — `config/profiles.json`

Her job için "hangi kanıt gitsin" ve "o kanıtın içine ne yapılsın" burada tanımlanır.
Kod değişmez; profil `job_id` ile otomatik bulunur.

```json
{
  "default":     { "evidence_to_llm": ["TestLogEvidence","HtmlEvidence","BrowserLogEvidence"],
                   "evidence_to_store": ["TestLogEvidence","HtmlEvidence","BrowserLogEvidence",
                                         "BuildLogEvidence","WebScreenshotEvidence","MobileScreenshotEvidence"] },

  "B_testlog":   { "job_ids": ["901"], "evidence_to_llm": ["TestLogEvidence"] },

  "C_buildlog":  { "job_ids": ["1204"], "evidence_to_llm": ["BuildLogEvidence"],
                   "rules": { "BuildLogEvidence": [
                     {"type":"keep_scenario_section",
                      "start":"> Scenario [{scenario_name}] started",
                      "end":"beforeScenario:"}]}},

  "D_dom_sec":   { "job_ids": ["1350"], "evidence_to_llm": ["TestLogEvidence","HtmlEvidence"],
                   "rules": { "HtmlEvidence": [
                     {"type":"strip_tags","tags":["script","style"]},
                     {"type":"select_nth","match":{"tag":"LinearLayout"},"index":0}]},
                   "extra_context": "Bu projede ilk layout kritiktir." }
}
```

**Profil seçimi:** `parameter1` bir profil adı verirse o kazanır → yoksa `job_ids`
eşleşmesi → yoksa `default`. Var olmayan profil adı verilirse koşum `failed` olur
(sessizce yanlış profille analiz etmez).

**Kural tipleri:** `keep_scenario_section` (job-seviyesi logu senaryo bazında dilimler) ·
`keep_last_lines` / `keep_first_lines` · `drop_matching` / `keep_matching` (regex) ·
`strip_tags` (etiketi alt ağacıyla siler) · `select_nth` (N'inci elementi alır) ·
`collapse_whitespace` · `max_chars`. Yeni kural tipi = 1 sınıf + registry'ye 1 satır.

> Kurallar **yalnız prompt'u** etkiler; `database/` altına ham içerik **tam** yazılır.
> Kesme olduysa sonuçta `truncated=true` + `truncated_note` görünür (sessiz kayıp yok).

**Eksik kanıt:** profil bir kanıt istediği hâlde o kanıt gelmediyse (ör. tarayıcı açılmadığı için
DOM yok) blok prompt'tan düşmez — `=== DOM ===` başlığı altında
`(bu kanıt alınamadı / bulunmuyor)` yazar. Böylece LLM eksiği bilir.

Prompt şablonu bu işaretin **ne demek olduğunu** modele ayrıca anlatır: eksik blok normaldir,
tek başına `unknown`/`inconclusive` gerekçesi değildir — yalnızca confidence'ı düşürebilir.
Aksi hâlde model teşhis üretmek yerine "kanıt eksik" raporlamaya başlıyor.

**Kanıt ne oldu, nereden bilinir:** her senaryonun `evidence` satırında `evidence_report` var —
gelen her dosya hangi Evidence sınıfına eşleşti (`""` = eşleşmedi), profil onu LLM'e gönderiyor
mu, hangi blok dolu hangisi yer tutucu, kural gerçekten kesti mi. "DOM gelmedi mi, geldi de
eşleşmedi mi" sorusu böylece tek koşumdan cevaplanır.

## Prompt şablonları — job grubuna göre

Prompt metni kodda değil, `config/prompts/` altındadır:
`default` · `web` · `mobile` · `hybrid` · `buildlog`. Profil hangisini kullanacağını söyler
(`"prompt": "buildlog"`). JSON şeması + verdict listesi + confidence kovaları **tek dosyadadır**
(`_contract.txt`) ve her şablonun sonuna sistem tarafından eklenir — beş kopya bakım edilmez.

Şablon içinde her kanıtın kendi alanı vardır: `$test_log`, `$dom`, `$browser_log`, `$build_log`
(ya da hepsi birden için `$evidence_blocks`). Tanınmayan bir alan adı ya da olmayan bir şablon
adı **açılışta hata** verir. Hangi şablonun hangi cevabı ürettiği `meta.prompt_template` +
`meta.prompt_version` ile her teşhiste kayıtlıdır.

## Build log — senaryo özelinde dilimleme

`build.log` **her koşumda bütün olarak** çekilir ve `runs` satırına kaydedilir — profilden bağımsız.
Çekilemezse koşum devam eder ve sebep `build_log_error` alanında görünür (yol hiç ayarlanmamışsa
bu kasıtlı atlamadır, alan boş kalır).
Ama LLM'e **gitmesi** ve **kesilmesi** job bazlıdır (profil kararı). Varsayılan profilde LLM'e gitmez.

Bazı joblarda senaryo özelinde `test.log`/DOM üretilmez; o joblarda tek kanıt build log olur.
Başarısız senaryoların listesi yine VisiumGo `/results`'tan gelir; build log yalnızca o senaryonun
**detayını** sağlar. Profilde tek yapılacak, logu senaryo bazında dilimlemek:

```json
"C_buildlog": {
  "job_ids": ["1204"],
  "evidence_to_llm": ["BuildLogEvidence"],
  "evidence_to_store": ["BuildLogEvidence"],
  "rules": { "BuildLogEvidence": [
    {"type": "keep_scenario_section",
     "start": "> Scenario [{scenario_name}] started",
     "end": "beforeScenario:"}]}
}
```

Log formatı: `beforeScenario:63 - [2]  > Scenario [Vadesiz Hesap Acilis] started` ile başlar, bir
sonraki `beforeScenario:` satırına kadar o senaryoya aittir (blok içinde
`TestCaseFinished ... result:FAILED` varsa senaryo başarısızdır).

> `{scenario_name}` VisiumGo'nun `/results`'ta verdiği adla değiştirilir — ad log'daki `[...]`
> içeriğiyle **birebir** eşleşmezse kural hiçbir şey kesmez (log olduğu gibi kalır, sessiz kayıp yok).

## PreCheck — bilinen hatalara LLM'siz cevap (`config/precheck_rules.json`)

Bazı hatalar analiz gerektirmez ("DB bilgileri değişmiş" gibi). Bir kural eşleşirse **LLM hiç
çağrılmaz**, hazır cevap döner:

```json
[
  { "name": "db_credentials",
    "match": "ORA-01017|invalid credentials",
    "verdict": "environment_error",
    "confidence": 0.99,
    "suggestion": "Lütfen veritabanı bilgilerinizi güncelleyin.",
    "error_signature": "db-credentials" }
]
```

Açmak için `.env`: `PRECHECK_PROVIDER=rules`. Varsayılan `noop` (her senaryo LLM'e gider) ve
dosya **boş listeyle** gelir.

- `match` regex'tir; varsayılan olarak hata mesajında aranır, `"search_in": "evidence"` denirse
  kanıt bloklarında aranır. **İlk eşleşen kural kazanır** (dosya sırası).
- Sonuçta `meta.llm_model = "precheck"` (LLM'e gidilmedi) ve `error_signature` (hangi kural).
- Bozuk regex / bilinmeyen verdict / kova dışı confidence → **açılışta** hata.

> ⚠️ Kural LLM'i **tamamen** atlar. Fazla geniş bir kalıp her senaryoyu yanlış etiketler ve kimse
> fark etmez. Kalıpları dar yazın (`ORA-01017` gibi kesin imzalar), `error`/`failed` gibi genel
> kelimeler **kullanmayın**, listeyi kısa tutun.

## Mock → Gerçek geçişi (kod değişmeden, yalnızca `.env`)

| Ne | `.env` değişikliği |
|---|---|
| Gerçek lokal LLM | `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=<url>`, `LLM_ENDPOINT_PATH=/api/v1/extension/send` (auth yok; `model` body'de gönderilmez) |
| Gerçek VisiumGo | `SOURCE_PROVIDER=visiumgo`, `VISIUMGO_BASE_URL=<url>`, `VISIUMGO_TOKEN=<JWT>` (extractor kaynaktan bağımsız, ayrı ayar yok) |
| Build log | `VISIUMGO_BUILD_LOG_PATH=/api/runs/{run_id}/logs` — endpoint **ZIP** döndürür, içinden `build.log` çıkarılır (`VISIUMGO_BUILD_LOG_ENTRY`); boş = atla |
| Kanıt akışı / kırpma | `config/profiles.json` → job bazlı profil + kurallar |
| Prompt şablonları | `PROMPTS_DIR=config/prompts` (eski `PROMPT_TEMPLATE_PATH` **kalktı**) |
| Paralellik | `MAX_CONCURRENCY=<n>` |
| Önbellek | `CACHE_ENABLED=true` → aynı **run_id + parametreler** daha önce analiz edildiyse LLM çağrılmaz, sonuç diskten döner (job bazlı değil: bir job'ın her koşumu ayrı analiz edilir) |

## Testler ve statik kontroller

```bash
pytest
```

Statik kontroller **isteğe bağlıdır** ve `[dev]` grubuna dahil DEĞİLDİR — kilitli iş
bilgisayarının `pip install -e ".[dev]"` komutu bunları indirmeye çalışmaz:

```bash
pip install -e ".[lint]"
ruff check .
mypy
```

`ruff` ayarları `pyproject.toml`'da; `mypy` `app/` ve `evals/`'i denetler (test yardımcıları
`**overrides` sözlükleri aldığı için bilinçli olarak gevşek bırakıldı).

## Prompt kalitesi ölçümü (golden set)

Prompt ya da profil değiştiğinde "cevaplar iyileşti mi kötüleşti mi" sorusu histen çıkıp sayıya
dönsün diye küçük bir ölçüm koşturucusu var:

```bash
python -m evals.runner
```

`evals/cases/*.json` altındaki **elle etiketlenmiş** vakaları gerçek zincirden geçirir
(extraction → profil → şablon → LLM → parse), modelin verdict'ini insanın yazdığıyla
karşılaştırır ve skoru **hangi prompt sürümünün** ürettiğini de yazarak basar. `--strict` ile
fark varsa çıkış kodu 1 olur.

Set **boş başlar**: uydurma vaka hiçbir şey ölçmez. Vaka biçimi `evals/runner.py` başında ve
`evals/cases/ornek-vaka.json.example` dosyasında.

Sözleşme-bazlı testler (Findings, çıktı şeması, Repository, parsing, Evidence
mimarisi/registry, profil çözümü, kırpma kuralları, önbellek, PreCheck, hata
dayanıklılığı) + mock'larla uçtan uca smoke testi.
