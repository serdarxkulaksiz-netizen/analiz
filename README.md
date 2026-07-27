# VisiumGo Test Analyzer

Başarısız otomasyon test koşumlarının (`web` / `mobile` / `hybrid`) ham kanıtını
(test.log, DOM, browser.log, ekran görüntüsü) lokal bir LLM'e yorumlatan FastAPI
backend. Çıktı: **güven seviyeli, gerekçeli ön teşhis** — "test hatası mı,
uygulama hatası mı, ortam mı, geçici mi (yoksa unknown/inconclusive mı)?"

Mimari ve tüm kararlar için tek doğru kaynak: [`plan.md`](plan.md) (v2).
Yapım geçmişi ve açık noktalar: [`CHANGELOG.md`](CHANGELOG.md).

## Mimari (tak-çıkar halkalar)

```
Source (VisiumGo) → Extraction (Evidence → Findings) → PreCheck → Prompt → LLM (tek atış) → Parse (JSON) → Persist + API
```

- **Davranış dallanması YOK:** `if mock` / `if platform ==` / `if type ==` yerine
  ayrı sınıf + arayüz + registry + DI. Yeni varyant = registry'ye bir satır.
- **Agentless / tek-atış:** senaryo başına tek prompt, tek LLM çağrısı; tool-calling yok.
- **Parse-minimal:** ham kanıt etiketli bloklar halinde LLM'e gider; alan-parser yok.
- **Evidence mimarisi:** 5 kanıt sınıfı + registry; `goes_to_llm`/`goes_to_store`
  bayrakları config'ten; her kanıtın content selector'ı (bugün passthrough); eksik
  kanıt tolere edilir. Beklenen kanıt seti platforma göre registry'den gelir.
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
# platform GİRDİDİR (tahmin edilmez): web | mobile | hybrid
# job_id VEYA run_id verilir (ikisi de olursa run_id kazanır)
curl -X POST http://127.0.0.1:8000/analyze/visiumgo \
  -H "Content-Type: application/json" \
  -d '{"bank": "demo", "job_id": "job-42", "platform": "web"}'

# durumu / sonuçları sorgula
curl http://127.0.0.1:8000/analyze/visiumgo/<analyzer_run_id>
```

Tam iz `database/` altına düşer: `runs/`, `evidence/`, `prompts/` (giden tam
prompt + ham cevap), `analysis_results/` (teşhisler). Hepsi insan-okunur JSON.

Mock kolaylığı: `job_id` sonu `-clean` biterse job hatasız kabul edilir
("analiz edilecek hata yok" yolu).

## Mock → Gerçek geçişi (kod değişmeden, yalnızca `.env`)

| Ne | `.env` değişikliği |
|---|---|
| Gerçek lokal LLM | `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=<url>`, `LLM_ENDPOINT_PATH=/api/v1/extension/send` (auth yok; `model` body'de gönderilmez) |
| Gerçek VisiumGo | `SOURCE_PROVIDER=visiumgo`, `VISIUMGO_BASE_URL=<url>`, `VISIUMGO_TOKEN=<JWT>` (extractor kaynaktan bağımsız, ayrı ayar yok) |
| Kırpma eşiği | `TRUNCATION_THRESHOLD_TOKENS=<model context'ine göre>` (0 = kesme yok; kırpma Evidence içi) |
| Kanıt akışı | `EVIDENCE_FLAGS=<JSON>` → hangi kanıt LLM'e/depoya gider (varsayılan koddadır) |
| Paralellik | `MAX_CONCURRENCY=<n>` |
| Önbellek | `CACHE_ENABLED=false` → aynı job tekrar analiz edilir |

## Testler

```bash
pytest
```

Sözleşme-bazlı testler (Findings/A6, çıktı şeması/A10, Repository, parsing,
Evidence mimarisi/registry, eksik kanıt toleransı, PreCheck, hata dayanıklılığı)
+ mock'larla uçtan uca smoke testi.
