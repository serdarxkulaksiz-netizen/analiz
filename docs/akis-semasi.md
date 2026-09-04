# Akış Şeması — VisiumGo Test Analyzer

> GitHub bu sayfadaki `mermaid` bloklarını otomatik olarak **görsel şema** olarak çizer.
> Detaylı anlatım: [nasil-calisir.md](nasil-calisir.md).

## 1) POST + Arka plan (analiz başlar ve çalışır)

```mermaid
flowchart TD
    C([İstemci]) -->|POST /analyze/visiumgo| A["main.start_analysis()"]
    A --> CR["service.create_run()<br/>runs/ tablosuna yazar · status=pending"]
    CR --> BG["background_tasks: run_analysis kuyruğa alınır"]
    A -->|HEMEN döner| R1([analyzer_run_id + pending])

    BG -.->|arka planda| RA["service.run_analysis()"]
    RA --> RJ["_run_job()<br/>status=running"]
    RJ --> RSV["source.resolve_run_id()<br/>hangi koşum? (ucuz)"]
    RSV --> CH{"cache açık ve bu koşum<br/>daha önce analiz edilmiş mi?"}
    CH -->|Evet| DC["status=done<br/>sonuçlar eski koşumdan · indirme YOK"]
    CH -->|Hayır| SRC["source.fetch_job()<br/>FAILED senaryolar + attachment'lar<br/>+ /logs ZIP → build.log"]
    SRC --> LOOP{Başarısız senaryo var mı?}
    LOOP -->|Hayır| D1["status=done<br/>note: analiz edilecek hata yok"]
    LOOP -->|Evet| AS["Her senaryo için: _analyze_scenario()<br/>paralel · asyncio.Semaphore"]

    AS --> EX["extractor.extract()<br/>profil seç · kanıt kurallarını uygula<br/>→ Findings"]
    EX --> PC{"precheck.check()<br/>bilinen hata kalıbı eşleşti mi?"}
    PC -->|"Evet · RuleBasedPreCheck"| CAN["hazır teşhis<br/>meta.llm_model=precheck<br/>LLM ÇAĞRILMAZ"]
    PC -->|"Hayır · varsayılan"| PB["builder.build()<br/>PromptBuilder → prompt"]
    PB --> LLM["llm.complete()<br/>OpenAICompatible / Mock · tek çağrı"]
    LLM --> PJ["_try_json()<br/>cevaptaki JSON'u ayrıştır"]
    PJ --> W["diske yaz · aynı result_id"]
    CAN --> W
    W --> EV[("evidence/<br/>ham kanıt")]
    W --> PR[("prompts/<br/>GİDEN: prompt + istek")]
    W --> LR[("llm_responses/<br/>GELEN: ham zarf")]
    W --> AR[("analysis_results/<br/>status: ok | analysis_failed")]
    AR --> D2["completed_count += 1<br/>hepsi bitince status=done"]
```

## 2) GET (durum ve sonuç sorgulanır)

```mermaid
flowchart TD
    C([İstemci]) -->|GET /analyze/visiumgo/id| G["main.get_analysis()"]
    G --> GR["service.get_run()<br/>TAM kaydı döndürür"]
    GR --> RD[("runs/ + analysis_results/<br/>DİSKTEN okunur, bellekten değil")]
    RD --> BV["build_run_view()<br/>API görünümüne indirger"]
    BV --> OUT([durum + kaç senaryo bitti<br/>+ YALNIZ LLM teşhisi])
    BV -.->|"API'ye GİRMEZ · diskte tam durur"| XX["build_log · raw_run_response<br/>raw_llm_response · screenshot_paths"]
    G -->|id yoksa| E404([404])
```

## Halkalar (kim ne yapar)

```mermaid
flowchart LR
    S["Source<br/>veri çeker"] --> X["Extraction<br/>kanıtı düzenler"]
    X --> C{"PreCheck<br/>kısa devre?"}
    C -->|"eşleşme yok · varsayılan"| P["Prompt<br/>soruyu yazar"]
    P --> L["LLM<br/>AI'ya sorar"]
    L --> PA["Parse<br/>cevabı ayrıştırır"]
    PA --> PE["Persist<br/>diske yazar"]
    C -->|"eşleşti → LLM atlanır"| PE
```

## Diske düşen tam iz (aynı result_id ile bağlı)

```mermaid
flowchart LR
    E[("evidence/<br/>ham kanıt")] --> PR[("prompts/<br/>giden soru")]
    PR --> LR[("llm_responses/<br/>AI ham cevap")]
    LR --> AR[("analysis_results/<br/>teşhis")]
    RUN[("runs/<br/>job durumu")]
```
