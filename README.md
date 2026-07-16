# VisiumGo Test Analyzer

Başarısız otomasyon test koşumlarının (web/Selenium + mobil/Android) ham kanıtını
(test.log, DOM, browser.log, ekran görüntüsü) lokal bir LLM'e yorumlatan FastAPI
backend. Çıktı: **güven seviyeli, gerekçeli ön teşhis** — "test hatası mı,
uygulama hatası mı, ortam mı, geçici mi?"

Mimari ve tüm kararlar için tek doğru kaynak: [`plan.md`](plan.md).
Yapım geçmişi ve açık noktalar: [`CHANGELOG.md`](CHANGELOG.md).

## Mimari (6 tak-çıkar halka)

```
Source (VisiumGo) → Extraction (Findings) → Prompt → LLM (tek atış) → Parse (JSON) → Persist + API
```

- **Agentless / tek-atış:** senaryo başına tek prompt, tek LLM çağrısı; tool-calling yok.
- **Parse-minimal:** ham kanıt etiketli bloklar halinde LLM'e gider; alan-parser yok.
- **DB simülasyonu:** `database/<tablo>/<id>.json`; Repository arayüzü arkasında
  (ileride SQLite/Oracle tak-çıkar).
- **Halka 1-2 stub:** gerçek VisiumGo erişimi iş bilgisayarında doldurulacak
  (`# TODO(work-pc)` işaretli); MacBook'ta mock'larla uçtan uca çalışır.

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
curl -X POST http://127.0.0.1:8000/analyze/visiumgo \
  -H "Content-Type: application/json" \
  -d '{"bank": "demo", "job_id": "job-42"}'

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
| Gerçek lokal LLM | `LLM_PROVIDER=openai_compatible`, `LLM_API_URL=<tam chat-completions URL>`, `LLM_MODEL=...` |
| Gerçek VisiumGo | `SOURCE_PROVIDER=visiumgo`, `EXTRACTOR_PROVIDER=visiumgo` + `config/banks.json` doldur (*iş bilgisayarında gerçeklenecek stub*) |
| Kırpma eşiği | `TRUNCATION_THRESHOLD_TOKENS=<model context'ine göre>` (0 = kesme yok) |
| Paralellik | `MAX_CONCURRENCY=<n>` |
| Önbellek | `CACHE_ENABLED=false` → aynı job tekrar analiz edilir |

## Testler

```bash
pytest
```

Sözleşme-bazlı testler (Findings/A6, çıktı şeması/A8, Repository, parsing,
kırpma önceliği, hata dayanıklılığı) + mock'larla uçtan uca smoke testi.
