# Proje Rehberi — Her Şey Tek Yerde (çok detaylı, sade)

> Bu dosya projenin **tam haritası**: her sınıf, her method, her ayar, her veri modeli.
> Amaç: kod okumadan "proje neleri yapabilir, hangi parça ne iş görür" görebilmek.
> Akış şeması: [akis-semasi.md](akis-semasi.md) · Adım adım anlatım: [nasil-calisir.md](nasil-calisir.md).

---

## 0. Tek cümlede

Başarısız test senaryolarını (VisiumGo'dan) çekip, ham kanıtı bir LLM'e yorumlatan, sonucu
diske yazan **asenkron FastAPI backend**. İki endpoint: **başlat** (POST) ve **sorgula** (GET).

Tasarımın özü: **6 halka**, her biri bir **arayüz** arkasında; hangi gerçeklemenin kullanılacağı
`.env`/config'ten seçilir. Kodda `if mock` / `if type ==` **yoktur** — her varyant ayrı sınıf +
registry + dependency injection.

```
Source → Extraction(+Evidence) → PreCheck → Prompt → LLM → Parse → Persist
```

---

## 1. Klasör haritası

| Yol | Ne var |
|---|---|
| `app/main.py` | FastAPI app, 2 endpoint, registry'ler, `build_service` (DI kökü) |
| `app/service.py` | `AnalyzerService` — asıl orchestrator (akışı yöneten beyin) |
| `app/config.py` | `Settings` — tüm ayarlar (kontrol paneli) |
| `app/domain/` | Sözleşmeler: enum'lar, `Findings`, `LLMAnalysis`/`AnalysisResult` |
| `app/source/` | Halka 1 — veri çekme (Mock + VisiumGo + HTTP client) |
| `app/evidence/` | Kanıt sınıfları + registry (mimeType+deviceId eşleme) |
| `app/extraction/` | Halka 2 — ham veri → `Findings` |
| `app/precheck/` | LLM öncesi kısa devre kancası (bugün boş) |
| `app/prompting/` | Halka 3 — `Findings` → prompt metni |
| `app/llm/` | Halka 4 — LLM'e çağrı (Mock + gerçek) |
| `app/parsing/` | Halka 5 — LLM cevabından JSON çıkar |
| `app/persistence/` | Halka 6 — diske yaz/oku (Repository) |
| `config/prompt_template.txt` | Prompt metni (kodda değil, dosyada) |
| `database/` | Sahte veritabanı (klasör=tablo, JSON=satır) |
| `tests/` | Sözleşme + uçtan uca testler |

---

## 2. Ayarlar (config) — açılıp kapanan her şey

Hepsi `app/config.py` → `Settings`; `.env` ile ezilir. Kodda hardcode yok.

| Ayar | Varsayılan | Ne işe yarar |
|---|---|---|
| `database_dir` | `database` | Sahte DB kök klasörü |
| `table_runs` / `table_analysis_results` / `table_evidence` / `table_prompts` / `table_llm_responses` | runs / … | Tablo (klasör) adları |
| `source_provider` | `mock` | Veri kaynağı: `mock` \| `visiumgo` |
| `visiumgo_base_url` / `visiumgo_token` | boş | Gerçek VisiumGo adres + JWT (Bearer header) |
| `visiumgo_timeout_seconds` | `60` | VisiumGo HTTP timeout |
| `visiumgo_verify_ssl` | `False` | VisiumGo SSL doğrulama (iç ağ için kapalı) |
| `profiles_config_path` | `config/profiles.json` | Analiz profilleri: job bazlı — hangi kanıt LLM'e/depoya gider + kırpma kuralları |
| `visiumgo_build_log_path` | boş | VisiumGo `/logs` endpoint'i (`{run_id}`) — **ZIP** döner; boş = atla |
| `visiumgo_build_log_entry` | `build.log` | ZIP içinde okunacak dosya (sonuna göre eşleşir) |
| `precheck_provider` | `noop` | `noop` = hep LLM'e git · `rules` = bilinen hatalara LLM'siz hazır cevap |
| `precheck_rules_path` | `config/precheck_rules.json` | PreCheck kural listesi (boş listeyle gelir) |
| `prompt_template_path` | `config/prompt_template.txt` | Prompt şablonunun yolu |
| `confidence_buckets` | `[0.1,0.25,0.5,0.75,0.99]` | İzin verilen güven değerleri |
| `llm_provider` | `mock` | LLM: `mock` \| `openai_compatible` |
| `llm_base_url` + `llm_endpoint_path` | boş + `/api/v1/extension/send` | Tam URL = ikisinin toplamı |
| `llm_api_key` | boş | Bu serviste yok; doluysa Bearer eklenir |
| `llm_model` | `qwen3-coder-next` | Sadece meta; **body'de gönderilmez** |
| `llm_temperature` / `llm_max_tokens` / `llm_timeout_seconds` | 0 / 8000 / 120 | LLM çağrı parametreleri |
| `llm_verify_ssl` | `False` | LLM SSL doğrulama |
| `max_concurrency` | `2` | Aynı anda kaç senaryo işlenir (`Semaphore`) |
| `cache_enabled` | `False` | Aynı **koşumu** (run_id + parametreler) tekrar analiz etmeme (kapalı) |

`get_settings()` → süreç boyunca tek `Settings` örneği döndürür (`@lru_cache`).

---

## 3. Enum'lar (sabit değerler)

| Enum | Değerler |
|---|---|
| `Verdict` | `test_maintenance`, `application_bug`, `environment_error`, `transient_error`, `unknown`, `inconclusive` |
| `StepStatus` | `PASSED`, `FAILED`, `SKIPPED` |
| `RunStatus` | `pending`, `running`, `done`, `failed` |
| `AnalysisStatus` | `ok`, `analysis_failed` |

---

## 4. Veri modelleri (kutular)

**`Attachment`** (bir ham dosya) — `file_name`, `mime_type`, `device_id`, `content` (metin), `stored_path` (diskteki yolu).

**`RawScenario`** (bir başarısız senaryonun ham hali) — `scenario_name`, `scenario_id`,
`error_text`, `steps: list[Step]`, `attachments: list[Attachment]`, `retry_info`,
`raw_detail` (senaryo-detay API cevabının HAM hali — her şey kaydedilir kuralı).

**`JobData`** (bir job koşusunun tamamı) — `job_id`, `run_id`, `job_name`,
`run_result` (özet dict), `total_scenario_count`, `failed_scenarios: list[RawScenario]`,
`build_log`, `raw_run_response`, `raw_results_response` (ham /results dizisi).

**`Findings`** (Halka 2 → 3 sözleşmesi) — ayrıca `profile_name`, `extra_context`, `truncated`,
`truncated_note`, `excluded_from_store` (hangi profil çalıştı, ek bağlam, kırpma/saklama bayrakları) —
`parameter1`, `parameter2`, `scenario_name`, `failed_step`,
`error_message`, `steps: list[Step]`, `evidence_blocks: list[EvidenceBlock]`,
`screenshot_paths: list`, `retry_info`.

**`Profile`** (analiz profili) — `name`, `job_ids: list`, `evidence_to_llm: list`,
`evidence_to_store: list`, `rules_for(evidence_name) -> list[Rule]`, `extra_context`
(`config/profiles.json`'dan; job_id ya da parameter1 ile seçilir).

**`Rule`** (içerik kuralı) — `apply(text, ctx) -> str`. `RuleContext`: `scenario_name`.

**`Step`** — `name`, `status` (StepStatus). **`EvidenceBlock`** — `label`, `content`.

**`LLMAnalysis`** (LLM'in döndürmesi gereken alanlar) — `scenario_name`, `root_cause`, `error_type`,
`verdict` (zorunlu), `explanation`, `suggestion`, `confidence` (zorunlu), `confidence_reason`,
`summary`, `most_relevant_log_lines: list`, `error_signature`.

**`AnalysisResult`** (diske yazılan teşhis satırı) — `result_id`, `analyzer_run_id` + tüm LLM alanları
+ sistem meta: `parameter1`, `parameter2`, `profile_name`, `truncated`, `truncated_note`, `screenshot_paths`,
`raw_llm_response`, `status` (AnalysisStatus), `meta`.

**`AnalysisMeta`** — `llm_model`, `input_tokens`, `output_tokens`, `duration_ms`, `analyzed_at`.

---

## 5. HALKALAR — her sınıf ve her method

### Halka 1 — Source (veri çekme) · `app/source/`

**`Source`** (arayüz)
| Method | Ne yapar |
|---|---|
| `resolve_run_id(job_id, run_id="")` | **Hangi koşum?** — ucuz; `run_id` verilmişse ağa hiç çıkmaz, yoksa en yeni koşumu bulur. Cache kontrolü bunun sonucuyla yapılır (isabet ederse indirme hiç olmaz) |
| `fetch_job(job_id, run_id="")` | Bir job'ın başarısız senaryolarını `JobData` olarak döndürür. `job_id` veya `run_id`'den biri koşumu belirler (parametreler source'a gitmez — yalnız analiz tarafını özelleştirir) |

**`MockSource`** (sahte veri; VisiumGo kapalıyken çalışır)
| Method | Ne yapar |
|---|---|
| `fetch_job(...)` | 2 başarısız sahte senaryo döndürür (hepsi `MOCK_` etiketli). `job_id` sonu `-clean` → hatasız job. Her senaryo TÜM attachment tiplerini taşır; prompt'a ne gireceğini profil seçer |

**`VisiumGoSource`** (gerçek VisiumGo API)
| Method | Ne yapar |
|---|---|
| `__init__(client, attachments_dir, build_log_path="", build_log_entry="build.log")` | HTTP client + indirme klasörü + (varsa) `/logs` yolu ve ZIP içinden okunacak dosya |
| `fetch_job(...)` | Zincir A-D'yi çalıştırır, `JobData` döndürür |
| `_resolve_run(job_id, run_id)` | **Adım A**: `run_id` verildiyse onu kullanır; yoksa `/api/runs?jobId=` → `startTime` en büyük koşum |
| `_build_scenario(run_id, record)` | **Adım C**: senaryo detayını çeker (`errorText`, `stepResults`, `attachments`) → `RawScenario`; ham detay cevabı `raw_detail`'de saklanır. Adım adı `line`'dan alınır |
| `_download_attachment(run_id, meta)` | **Adım D**: dosyayı indirir (URL-encode), diske kaydeder; inmezse boş `Attachment` (o kanıt "eksik" sayılır) |
| `_save(run_id, file_name, data)` | İnen dosyayı `database/attachments/...` altına yazar (pathlib) |
| `_fetch_build_log(run_id)` | VisiumGo `/logs`'tan **ZIP** indirir, `_extract_log` ile `build.log`'u çıkarır (yol boşsa atlar; ağ/ZIP/dosya hatasında boş döner, job devam eder) |
| `_extract_log(archive)` | ZIP'ten yapılandırılmış dosyayı okur (ham ZIP saklanmaz) |

> **Adım B** (`fetch_job` içinde): `/api/runs/{run_id}/results` → `resultType == "FAILED"` filtresi; PASSED/flaky atlanır.

**`VisiumGoClient`** (ince HTTP sarmalayıcı — orchestrator DEĞİL)
| Method | Ne yapar |
|---|---|
| `__init__(base_url, token, timeout, verify_ssl=True, transport=None)` | Bağlantı ayarları; `transport` testlerde sahte HTTP için |
| `get_json(path, params)` / `get_text(path)` / `get_bytes(path)` | Kimlik doğrulamalı GET (Bearer yalnız token varsa) |
| `encode_segment(segment)` | URL yol parçasını percent-encode eder (`/`, `:`, boşluk için) |

---

### Halka 2 — Extraction + Evidence · `app/extraction/`, `app/evidence/`

**`Extractor`** (arayüz)
| Method | Ne yapar |
|---|---|
| `extract(scenario, *, parameter1="default", parameter2="default", job_id="", build_log="")` | `RawScenario` → `Findings` (profil job_id/parameter1 ile seçilir) |

**`EvidenceExtractor`** (tek, kaynaktan bağımsız gerçekleme)
| Method | Ne yapar |
|---|---|
| `__init__(registry, profiles)` | `EvidenceRegistry` + `ProfileRegistry` enjekte edilir |
| `extract(...)` | Profili seçer; build log'u **sentetik attachment** yapar (böylece profil+kural onu da yönetir); Attachment'ları Evidence'lara çevirip LLM bloklarını ve screenshot yollarını toplar; `error_text`'ten HATA bloğu, FAILED adımdan `failed_step`; kırpma olduysa `truncated`+not → `Findings`. **Alan-çıkaran parser yok** (parse-minimal) |

**`Evidence`** (kanıt arayüzü — 2 aile: metin ve ekran görüntüsü)
| Üye | Ne yapar |
|---|---|
| `mime_type` / `device_id` (sınıf özelliği) | Bu kanıtın hangi attachment'a uyduğu |
| `matches(attachment)` | mimeType eşit + deviceId tam/prefix eşleşiyor mu (mobil için `mobile.` prefix) |
| `is_present` | Kanıt geldi mi (eksik tolere edilir) |
| `to_block()` | LLM'e gidecek `=== etiket ===` bloğu (uygunsa), yoksa `None` |
| `screenshot_path` | Ekran görüntüsü yolu (metin kanıtlarında boş) |
| `from_attachment(attachment, *, goes_to_llm, goes_to_store, rules, ctx)` | Attachment'tan kendini kurar (tip-dallanması gerekmeden) |
| `select_content()` (metin) | İçerik seçici — profilin kurallarını **sırayla** uygular (kural yoksa passthrough) |
| `was_trimmed` | Kurallar içeriği gerçekten değiştirdi mi (görünür bayrak) |

**6 kanıt sınıfı** (yalnızca bunlar):
| Sınıf | mimeType + deviceId | Varsayılan profilde LLM'e |
|---|---|---|
| `TestLogEvidence` | text/plain + `test` → **ADIMLAR** | ✅ |
| `BrowserLogEvidence` | text/plain + `browser.default` → **BROWSER LOG** | ✅ |
| `BuildLogEvidence` | text/plain + `build` → **BUILD LOG** | ❌ (job-seviyesi; profil açar) |
| `HtmlEvidence` | text/html + `browser.default` → **DOM** | ✅ |
| `WebScreenshotEvidence` | image/png + `browser.default` | ❌ (sadece diske) |
| `MobileScreenshotEvidence` | image/png + `mobile.*` | ❌ (sadece diske) |

**`EvidenceRegistry`**
| Method | Ne yapar |
|---|---|
| `build_for(scenario, profile, ctx=None)` | Attachment'ları (mimeType+deviceId ile) Evidence'lara eşler; bayrakları **ve kuralları** profilden enjekte eder |

**`ProfileRegistry`** (`app/evidence/profiles.py`)
| Method | Ne yapar |
|---|---|
| `__init__(config_path)` | `profiles.json`'ı yükler, kuralları **açılışta derler**; `default` profili yoksa / aynı job_id iki profildeyse / kural config'i bozuksa **açılışta patlar** (fail-fast) |
| `get(job_id="", parameter1="")` | Profili döndürür; sıra: `parameter1` (profil adı) → `job_ids` eşleşmesi → `default`. Bilinmeyen profil adı → hata |

**Kural motoru** (`app/evidence/rules.py`) — `Rule.apply(text, ctx)`; `RULE_REGISTRY`'den seçilir.
| Kural | Ne yapar |
|---|---|
| `keep_scenario_section` | Job-seviyesi logdan yalnız bu senaryonun bölümü (`{scenario_name}`) |
| `keep_last_lines` / `keep_first_lines` | Son/ilk N satır |
| `drop_matching` / `keep_matching` | Regex ile satır ele/tut |
| `strip_tags` | Etiketi **alt ağacıyla** siler (script/style/comment) |
| `select_nth` | N'inci elementi alt ağacıyla alır (ör. ilk `LinearLayout`) |
| `collapse_whitespace` · `max_chars` | Boşluk sıkıştır · karakter sınırı |

Yeni kural tipi = 1 sınıf + registry'ye 1 satır. Kural eşleşmezse içerik **bozulmaz**.
Kurallar yalnız prompt'u etkiler; `database/` ham içeriği tam tutar.

---

### PreCheck (LLM öncesi kanca) · `app/precheck/`

**`PreCheck`** (arayüz) → `check(findings) -> LLMAnalysis | None`. `None` → LLM'e git;
bir analiz → **LLM atlanır**, o cevap kaydedilir.

| Gerçekleme | Ne yapar |
|---|---|
| `NoOpPreCheck` | Her zaman `None` — herkes LLM'e gider (varsayılan) |
| `RuleBasedPreCheck` | `precheck_rules.json`'daki kurallardan **ilk eşleşen** kazanır → hazır cevap döner, LLM çağrılmaz |

**Kural alanları:** `name`, `match` (regex), `search_in` (`error_message` \| `evidence`),
`verdict`, `confidence` (5 kovadan biri), `suggestion`/`explanation`/`root_cause`/`summary`/
`error_type`/`confidence_reason`, `error_signature` (hangi kuralın cevapladığı sonuçta görünür).
Bozuk regex / bilinmeyen verdict / kova dışı confidence → **açılışta** hata (fail-fast).

⚠️ Kural LLM'i tamamen atlar: kalıplar dar olmalı, liste kısa tutulmalı (plan.md A7).

---

### Halka 3 — Prompt · `app/prompting/`

**`PromptBuilder`**
| Method | Ne yapar |
|---|---|
| `__init__(template_path, confidence_buckets)` | Şablonu dosyadan yükler (yoksa açılışta patlar = fail-fast) |
| `build(findings)` | Şablondaki `$parameter1`, `$parameter2`, `$scenario_name`, `$failed_step`, `$error_message`, `$steps`, `$evidence_blocks`, `$confidence_buckets` yerlerini doldurur → prompt metni. **Prompt metni koddan değil, `config/prompt_template.txt`'ten gelir** |

---

### Halka 4 — LLM · `app/llm/`

**`LLMProvider`** (arayüz) → `complete(prompt) -> LLMResponse`. `LLMError` = çağrı hatası.

**`LLMResponse`** — `content` (mesaj içeriği, parse edilecek), `raw_response` (LLM'in döndürdüğü **tam
zarf**), `request` (gönderilen tam istek), `model`, `input_tokens`, `output_tokens`, `duration_ms`.

**`OpenAICompatibleLLMProvider`** (gerçek servis)
| Method | Ne yapar |
|---|---|
| `__init__(base_url, endpoint_path, api_key, model, temperature, timeout, max_tokens, verify_ssl=True, transport=None)` | Tam URL = base+path; parametreler config'ten |
| `complete(prompt)` | POST atar (body: `messages`(tek user)+`temperature`+`max_tokens`; **model body'de yok**). Cevabı **parse'tan önce** ham olarak yakalar; sonra `_extract` ile içeriği çıkarır. Transport hatası → `LLMError`; başka hata → içerik boş ama ham korunur |
| `_extract(response, raw)` | `response.json()`; **string dönerse `json.loads` ile çift-kodlamayı açar**; `choices[0].message.content` + `usage`/`model`. Patlarsa boş içerik döner (ham kaybolmaz) |
| `_headers()` | `accept: application/json`; token varsa `Authorization` |

**`MockLLMProvider`** (sahte LLM; gerçek zarfı taklit eder)
| Method | Ne yapar |
|---|---|
| `__init__(model, confidence=0.75)` | Model adını `MOCK_` ile etiketler |
| `complete(prompt)` | Sabit, şema-geçerli bir teşhis döndürür (serbest metinler `MOCK_`; verdict/confidence geçerli). `raw_response`'a gerçek `chat.completion` zarfını taklit eder |
| `_echo_scenario_name(prompt)` | Prompt'taki `Senaryo:` satırından adı yansıtır (izler hizalı kalsın) |

---

### Halka 5 — Parse · `app/parsing/`

**`_try_json(text) -> dict | None`** — LLM cevabındaki JSON objesini bulmaya çalışır: düz JSON →
markdown fence → en dış `{...}` sırasıyla dener. Obje bulamazsa `None` (senaryo `analysis_failed`,
ham cevap saklı). **Regex/alan-çıkarma yok.**

---

### Halka 6 — Persist · `app/persistence/`

**`Repository`** (arayüz) → `save(table, id, data)`, `get(table, id)`, `list(table)`, `exists(table, id)`.
İleride SQLite/Oracle aynı arayüzle takılır; üst kod değişmez.

**`FileRepository`** — satırları `database/<tablo>/<id>.json` olarak yazar. `save` önce geçici dosyaya
yazıp `os.replace` ile atomik değiştirir (yarım satır okunmaz). UTF-8, insan-okunur indent.

---

## 6. Orchestrator — `AnalyzerService` (beyin)

Tüm halkaları enjekte alır; hiçbirini kendisi yaratmaz.

| Method | Ne yapar |
|---|---|
| `__init__(settings, repository, source, extractor, prompt_builder, llm_provider, precheck)` | Parçaları takar; run satırı kilidi kurar |
| `create_run(parameter1, job_id, parameter2, run_id="")` | `runs/` tablosuna `pending` satır yazar, `analyzer_run_id` döndürür (POST bunu çağırır) |
| `run_analysis(analyzer_run_id)` | **Tek tetik** (arka plan girişi). `_run_job`'u sarar; job-seviyesi hata → `status=failed` + not |
| `_run_job(run)` | `running` yapar → (cache açıksa kontrol) → `source.fetch_job` → run'ı günceller → hata yoksa `done` → varsa her senaryo için `_analyze_scenario` (paralel, `Semaphore`) → `done` |
| `_analyze_scenario(...)` | **Asıl zincir** (aşağıda). Asla exception fırlatmaz (bir senaryo koşuyu düşürmez) |
| `_find_cached_run(run)` | Aynı **run_id** + parametrelerin daha önce tam analizli koşumunu bulur. job_id ile eşleşmez (bir job'ın çok koşumu olur); run_id boşsa cache aranmaz |
| `_screenshot_paths(scenario)` | Ham iz satırı için image attachment yollarını toplar |
| `_increment_completed(id)` | Kilit altında `completed_count += 1` |
| `_update_run(run, **fields)` | Run satırını güncelleyip diske yazar |
| `get_run(id)` | `runs/` satırını + o run'a ait `analysis_results/` satırlarını **diskten** okur (GET bunu çağırır) |

**`_analyze_scenario` içinde sırayla:**
1. `result_id` üret → `evidence/` yaz (ham senaryo).
2. `extractor.extract()` → `Findings`.
3. `precheck.check()` → None değilse LLM atlanır.
4. `prompt_builder.build()` → prompt.
5. `llm.complete()` → cevap (ham + içerik).
6. `prompts/` yaz (prompt + request + ham) ve `llm_responses/` yaz (LLM'in ham cevabı).
7. `_try_json(content)` → geçerliyse `AnalysisResult(status=ok)`, değilse `status=analysis_failed`.
8. `analysis_results/` yaz → `completed_count += 1`.

---

## 7. API — `app/main.py`

| Parça | Ne yapar |
|---|---|
| `AnalyzeRequest` | POST gövdesi: `parameter1?`, `parameter2?` (verilmezse "default"), `job_id`/`run_id` (biri zorunlu, yoksa 422) |
| `SOURCE_REGISTRY` / `LLM_REGISTRY` / `PRECHECK_REGISTRY` | ad→fabrika sözlükleri; `.env`'deki isme göre gerçekleme seçilir (dallanma yok) |
| `_select(registry, key, kind)` | Registry'den fabrika bulur; bilinmeyen ad → net hata |
| `build_service(settings)` | **DI kökü**: config'e göre tüm parçaları kurup `AnalyzerService` döndürür |
| `create_app(settings=None)` | FastAPI app'i kurar; 2 endpoint'i tanımlar |
| `POST /analyze/visiumgo` → `start_analysis` | `create_run` çağırır, `run_analysis`'i arka plana atar, **hemen** `analyzer_run_id` döner |
| `GET /analyze/visiumgo/{id}` → `get_analysis` | `get_run` çağırır; yoksa 404 |

---

## 8. database/ — sahte veritabanı (tam iz)

| Tablo (klasör) | Bir satırda ne var |
|---|---|
| `runs/` | Job durumu: parameter1/2, job_id/run_id, status, sayaçlar, `run_result`, `raw_run_response`, `raw_results_response` |
| `evidence/` | Senaryonun ham hali (`raw_scenario` + screenshot yolları + `excluded_from_store`). Profilin `evidence_to_store`'a koymadığı kanıdın **içeriği boş**, metadata durur |
| `prompts/` | **Giden** taraf: `prompt` + gönderilen tam `request` |
| `llm_responses/` | **Gelen** taraf: `raw_response` (tam zarf) + `content` + model/token/süre |
| `analysis_results/` | Nihai teşhis (`verdict`, `root_cause`... + sistem meta + `status`) |
| `attachments/` | (gerçek VisiumGo) inen ham dosyalar |

Aynı senaryonun izi **aynı `result_id`** ile `evidence`/`prompts`/`llm_responses`/`analysis_results`
arasında bağlıdır. `analyzer_run_id` ise hepsini bir job koşusuna bağlar.

---

## 9. Uçtan uca akış (özet)

```
POST {parameter1?, parameter2?, job_id|run_id}
  → create_run  → runs/ (pending)  → HEMEN analyzer_run_id döner
  → (arka plan) run_analysis → _run_job
        → source.fetch_job → JobData (başarısız senaryolar)
        → her senaryo (paralel): _analyze_scenario
              extract → precheck → build → llm.complete
              → evidence/ , prompts/ , llm_responses/ , analysis_results/
        → runs/ (done)
GET /{analyzer_run_id}  → get_run → diskten oku → durum + teşhisler
```

---

## 10. "Şunu nasıl değiştiririm?" (hızlı reçete)

| İstek | Nereyi değiştir |
|---|---|
| Mock → gerçek VisiumGo | `.env`: `SOURCE_PROVIDER=visiumgo` + `VISIUMGO_BASE_URL`/`VISIUMGO_TOKEN` |
| Mock → gerçek LLM | `.env`: `LLM_PROVIDER=openai_compatible` + `LLM_BASE_URL` |
| SSL kapat | `.env`: `VISIUMGO_VERIFY_SSL=false` / `LLM_VERIFY_SSL=false` |
| Cache aç/kapa | `.env`: `CACHE_ENABLED=true/false` |
| Hangi kanıt LLM'e gitsin | `config/profiles.json`: job'a profil satırı ekle (`job_ids` + `evidence_to_llm`) |
| Kanıtın içini kes/seç | Aynı profilde `rules` (ör. `strip_tags`, `select_nth`, `keep_scenario_section`) |
| Prompt'a job'a özel not | Profilde `extra_context` |
| Prompt metni | `config/prompt_template.txt` (kod değil) |
| Paralellik | `.env`: `MAX_CONCURRENCY=n` |
| Yeni kaynak/LLM/precheck | İlgili `*_REGISTRY`'ye 1 satır + yeni sınıf |

---

**Kısaca:** `AnalyzerService` akışı bilir, `Settings`+`build_service` neyin takılacağını seçer, 6 arayüz
takılıp çıkabilen organlardır, `database/` her adımı diske işler. Değiştirmek istediğin çoğu şey
**tek bir `.env` satırı** ya da **registry'ye tek satır**.
