# VisiumGo Test Analyzer

Başarısız otomasyon test koşumlarının ham kanıtını
(test.log, DOM, browser.log, ekran görüntüsü) lokal bir LLM'e yorumlatan FastAPI
backend. Çıktı: **güven seviyeli, gerekçeli ön teşhis** — "test hatası mı,
uygulama hatası mı, ortam mı, geçici mi (yoksa unknown/inconclusive mı)?"

Mimari ve tüm kararlar için tek doğru kaynak: [`plan.md`](plan.md) (v2).
Yapım geçmişi ve açık noktalar: [`CHANGELOG.md`](CHANGELOG.md).

## Mimari (tak-çıkar halkalar)

```
Source (VisiumGo) → Extraction (Evidence → Findings) → PreCheck → Prompt → LLM (tek atış) → Parse (JSON) → Persist + API
```

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
- **Her şey kaydedilir:** VisiumGo'dan gelen tüm ham cevaplar (run, results,
  senaryo detayı, attachment dosyaları) `database/` altına yazılır.
- **PreCheck kancası:** bugün `NoOpPreCheck` (her zaman LLM'e gider); kural listesi yok.
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

Tam iz `database/` altına düşer: `runs/` (koşum durumu + ham API cevapları),
`evidence/` (ham kanıt), `prompts/` (**giden**: prompt + istek),
`llm_responses/` (**gelen**: LLM'in tam ham cevabı), `analysis_results/`
(teşhisler). Hepsi insan-okunur JSON.

Mock kolaylığı: `job_id` sonu `-clean` biterse job hatasız kabul edilir
("analiz edilecek hata yok" yolu).

## Job bazlı özelleştirme — `config/profiles.json`

Her job için "hangi kanıt gitsin" ve "o kanıtın içine ne yapılsın" burada tanımlanır.
Kod değişmez; profil `job_id` ile otomatik bulunur.

```json
{
  "default":     { "evidence_to_llm": ["TestLogEvidence","HtmlEvidence","BrowserLogEvidence"],
                   "evidence_to_store": ["TestLogEvidence","HtmlEvidence","BrowserLogEvidence",
                                         "JenkinsLogEvidence","WebScreenshotEvidence","MobileScreenshotEvidence"] },

  "B_testlog":   { "job_ids": ["901"], "evidence_to_llm": ["TestLogEvidence"] },

  "C_jenkins":   { "job_ids": ["1204"], "evidence_to_llm": ["JenkinsLogEvidence"],
                   "rules": { "JenkinsLogEvidence": [
                     {"type":"keep_scenario_section","start":"Scenario: {scenario_name}","end":"Scenario: "}]}},

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
| Build log | `VISIUMGO_JENKINS_LOG_PATH=/api/runs/{run_id}/logs` — endpoint **ZIP** döndürür, içinden `build.log` çıkarılır (`VISIUMGO_JENKINS_LOG_ENTRY`); boş = atla |
| Kanıt akışı / kırpma | `config/profiles.json` → job bazlı profil + kurallar |
| Paralellik | `MAX_CONCURRENCY=<n>` |
| Önbellek | `CACHE_ENABLED=true` → aynı **run_id + parametreler** daha önce analiz edildiyse LLM çağrılmaz, sonuç diskten döner (job bazlı değil: bir job'ın her koşumu ayrı analiz edilir) |

## Testler

```bash
pytest
```

Sözleşme-bazlı testler (Findings, çıktı şeması, Repository, parsing, Evidence
mimarisi/registry, profil çözümü, kırpma kuralları, önbellek, PreCheck, hata
dayanıklılığı) + mock'larla uçtan uca smoke testi.
