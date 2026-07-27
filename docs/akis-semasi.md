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
    RJ --> SRC["source.fetch_job()<br/>VisiumGoSource / MockSource → JobData"]
    SRC --> LOOP{Başarısız senaryo var mı?}
    LOOP -->|Hayır| D1["status=done<br/>note: analiz edilecek hata yok"]
    LOOP -->|Evet| AS["Her senaryo için: _analyze_scenario()<br/>paralel · asyncio.Semaphore"]

    AS --> EV[("evidence/ yaz")]
    AS --> EX["extractor.extract()<br/>EvidenceExtractor → Findings"]
    EX --> PC["precheck.check()<br/>NoOpPreCheck → None"]
    PC --> PB["builder.build()<br/>PromptBuilder → prompt"]
    PB --> LLM["llm.complete()<br/>OpenAICompatible / Mock · tek çağrı"]
    LLM --> PR[("prompts/ yaz")]
    LLM --> LR[("llm_responses/ yaz")]
    LLM --> PJ["_try_json()<br/>cevaptaki JSON'u ayrıştır"]
    PJ --> AR[("analysis_results/ yaz<br/>status: ok | analysis_failed")]
    AR --> D2["completed_count += 1<br/>hepsi bitince status=done"]
```

## 2) GET (durum ve sonuç sorgulanır)

```mermaid
flowchart TD
    C([İstemci]) -->|GET /analyze/visiumgo/id| G["main.get_analysis()"]
    G --> GR["service.get_run()"]
    GR --> RD[("runs/ + analysis_results/<br/>DİSKTEN okunur, bellekten değil")]
    RD --> RES([durum + kaç senaryo bitti + teşhisler])
    G -->|id yoksa| E404([404])
```

## Halkalar (kim ne yapar)

```mermaid
flowchart LR
    S["Source<br/>veri çeker"] --> X["Extraction<br/>kanıtı düzenler"]
    X --> P["Prompt<br/>soruyu yazar"]
    P --> L["LLM<br/>AI'ya sorar"]
    L --> PA["Parse<br/>cevabı ayrıştırır"]
    PA --> PE["Persist<br/>diske yazar"]
```

## Diske düşen tam iz (aynı result_id ile bağlı)

```mermaid
flowchart LR
    E[("evidence/<br/>ham kanıt")] --> PR[("prompts/<br/>giden soru")]
    PR --> LR[("llm_responses/<br/>AI ham cevap")]
    LR --> AR[("analysis_results/<br/>teşhis")]
    RUN[("runs/<br/>job durumu")]
```
