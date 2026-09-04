# Nasıl Çalışır? (yeni başlayanlar için)

> Projeyi ilk kez okuyan biri için, bir POST isteği atıldığında adım adım ne olduğunu,
> hangi method'un nereden çağrıldığını ve GET'in ne yaptığını sade dille anlatır.
> Görsel şema: [akis-semasi.md](akis-semasi.md).

## Büyük resim (restoran benzetmesi)

Projeyi bir **restoran** gibi düşün:

- **POST** = sipariş verirsin, garson "aldım, numaran bu" der ve gider (beklemez).
- **Arka plan** = mutfak yemeği hazırlar (asıl iş burada olur).
- **GET** = ara ara "hazır mı?" diye sorarsın.

Zincir **6 halka + 1 kanca**dan oluşur, her biri ayrı dosyada ve birbirinden bağımsızdır:

```
Source → Extraction → [PreCheck] → Prompt → LLM → Parse → Persist
(veri çek) (kanıt düzenle) (kısa devre?) (soru yaz) (AI'ya sor) (ayrıştır) (diske yaz)
```

**PreCheck** araya girer: bilinen bir hata kalıbı eşleşirse hazır cevap döner ve
**Prompt + LLM tamamen atlanır**. Varsayılan `NoOpPreCheck` hiç eşleşmez, yani normalde
her senaryo LLM'e gider.

Her halka bir **arayüz** (interface) arkasındadır. Hangi gerçeklemenin (mock mu, gerçek mi)
kullanılacağı `.env`'den seçilir ve hepsi başta `app/main.py` → `build_service()` içinde birbirine
takılır. Buna **dependency injection** (bağımlılık enjeksiyonu) denir: parçaları dışarıdan takarız,
böylece mock↔gerçek geçişi kod değişmeden olur.

---

## 1) POST /analyze/visiumgo — sipariş

**Dosya:** `app/main.py` → `start_analysis()`

1. **FastAPI gövdeyi doğrular.** `AnalyzeRequest` modeli `{parameter1?, parameter2?, job_id | run_id}`
   bekler; parametreler verilmezse `"default"` olur. job_id ve run_id'nin ikisi de yoksa → `422` hata.
2. **`service.create_run(parameter1, job_id, parameter2, run_id)`** çağrılır (`app/service.py`):
   - Rastgele bir kimlik üretir: `analyzer_run_id`.
   - `database/runs/{analyzer_run_id}.json` dosyasını `status="pending"` ile **diske yazar**.
   - Bu id'yi döndürür.
3. **`background_tasks.add_task(service.run_analysis, analyzer_run_id)`** — asıl ağır işi **arka plana**
   kuyruğa atar (cevap gönderildikten sonra çalışır).
4. **Hemen döner:** `{analyzer_run_id, status: "pending"}`.

> POST **beklemez**; "siparişi aldım, numaran bu" der ve kapatır. Yemek arka planda pişer.

---

## 2) Arka plan — mutfak çalışıyor

**`run_analysis(analyzer_run_id)`** (service.py) — tek giriş noktası. (İleride Redis'e geçilirse
yalnızca burası değişir; kod bu yüzden böyle kurgulandı.)

1. `runs` dosyasını diskten okur.
2. **`_run_job(run)`** çağrılır:
   - Durumu `running` yapar.
   - **`self._source.resolve_run_id(...)`** — hangi koşum olduğunu **önce** belirler (ucuz).
   - **Önbellek kontrolü** (`CACHE_ENABLED` açıksa): aynı `run_id` + parametreler daha önce
     analiz edildiyse hiçbir indirme yapılmadan eski sonuçlar gösterilir. Varsayılan **kapalı**.
   - **`self._source.fetch_job(job_id, run_id)`** — **Source** halkası
     (`MockSource` veya `VisiumGoSource`):
     - `VisiumGoSource`: run_id'yi çözer → `/results`'tan **FAILED** senaryoları alır → her senaryonun
       detayını (`errorText`, `stepResults`, `attachments`) çeker → attachment'ları indirir →
       **build log**'u `/logs` ucundan **ZIP** olarak indirip içinden `build.log`'u çıkarır.
       Sonuç: `JobData` (içinde başarısız senaryoların listesi = `RawScenario`'lar).
   - `runs` dosyasını günceller (run_id, job adı, senaryo sayıları, ham cevap).
   - **Hata yoksa** → `status="done"`, not: "analiz edilecek hata yok". Biter.
   - **Hata varsa** → her senaryo için **`_analyze_scenario(...)`** paralel çalışır
     (`asyncio.gather` + `Semaphore`; aynı anda kaç tane olduğu config'ten).
   - Sonunda `status="done"`.

**`_analyze_scenario(scenario)`** — asıl zincir, her başarısız senaryo için:

1. `result_id` üretir (bu senaryonun izini 4 tabloda birbirine bağlayan anahtar).
2. **`self._extractor.extract(scenario, ...)`** — **Extraction** halkası (`EvidenceExtractor`):
   - `job_id`/`parameter1` ile **analiz profilini** seçer (`config/profiles.json`).
   - `EvidenceRegistry` ile attachment'ları (`mimeType` + `deviceId`'ye göre) Evidence sınıflarına eşler.
   - Profilin **içerik kurallarını** uygular (kes/seç/temizle).
   - `Findings` üretir: LLM'e gidecek etiketli bloklar + hata mesajı + adımlar.
     Profilin istediği bir kanıt gelmediyse bloğu **düşmez**, içine
     `(bu kanıt alınamadı / bulunmuyor)` yazar.
3. **`self._precheck.check(findings)`** — **PreCheck**:
   - `NoOpPreCheck` (varsayılan) → `None` → LLM'e devam.
   - `RuleBasedPreCheck` → bir kural eşleşirse **hazır teşhis** döner ve **4-5. adımlar atlanır**
     (prompt kurulmaz, LLM çağrılmaz).
4. **`prompt = self._builder.build(findings)`** — **Prompt** halkası (`PromptBuilder`):
   şablonu (`config/prompt_template.txt`) doldurur.
5. **`response = await self._llm.complete(prompt)`** — **LLM** halkası
   (`MockLLMProvider` veya `OpenAICompatibleLLMProvider`):
   - Gerçek olan: LLM servisine POST atar, **ham cevabı olduğu gibi yakalar**, içinden `content`'i çıkarır.
6. **`_try_json(response.content)`** — **Parse** halkası: LLM cevabındaki JSON'u yapıya çevirir.
   - Geçerliyse → teşhis alanları dolu (`verdict`, `root_cause`, ...), `status="ok"`.
   - Geçersiz/boşsa → `status="analysis_failed"` (alanlar boş, **ham cevap yine saklı**).
7. **Şimdi diske yazar** (4 tablo, hepsi aynı `result_id` ile):
   - `evidence/` → ham senaryo. **Extraction'dan sonra** yazılır, çünkü profilin
     `evidence_to_store` kararının uygulanması gerekir.
   - `prompts/` → **GİDEN** taraf: gönderilen prompt + tam istek. *(Ham cevap burada **yoktur**.)*
   - `llm_responses/` → **GELEN** taraf: LLM'in tam ham zarfı + içerik + çağrı meta'sı.
   - `analysis_results/` → teşhis satırı.
8. Run dosyasındaki `completed_count`'u +1 yapar.

> LLM çağrısı patlarsa (ör. bağlantı hatası) o senaryo `analysis_failed` işaretlenir ama **job devam
> eder** — bir senaryo tüm koşuyu düşürmez.

---

## 3) GET /analyze/visiumgo/{id} — "hazır mı?"

**Dosya:** `app/main.py` → `get_analysis()` → **`service.get_run(id)`**

1. `database/runs/{id}.json`'u **diskten** okur (bellekten değil — bu bilinçli bir tasarım).
2. Bu run'a ait tüm `analysis_results` satırlarını okuyup `results` olarak ekler.
3. **`build_run_view()` ile sadeleştirir** — API'ye yalnız şunlar çıkar: durum bilgileri +
   her senaryo için **LLM'in teşhisi** + `status` + `meta` + `result_id`.
   Ham veriler (`build_log`, `raw_run_response`, `raw_llm_response`, `screenshot_paths` …)
   **API'ye girmez**; hepsi `database/` altında tam durur ve `result_id` ile bulunur.
4. Id yoksa → `404`.

> GET hiçbir şey hesaplamaz, sadece **diskte ne varsa onu okur.** Bu yüzden istediğin kadar sorabilirsin;
> sunucu yeniden başlasa bile durum kaybolmaz.

---

## database/ = sahte veritabanı

- **Klasör = tablo**, **JSON dosyası = satır.**
- Bir senaryonun tam izi (hepsi aynı `result_id` ile bağlı):
  `evidence/` (ham kanıt) → `prompts/` (giden soru) → `llm_responses/` (AI'nın ham cevabı) →
  `analysis_results/` (teşhis). `runs/` = job'ın genel durumu.
- Her şey insan-okunur JSON; açıp inceleyebilirsin.

## Neden böyle kurgulandı?

- **POST hızlı dönsün** → kullanıcı beklemesin (asıl iş arka planda).
- **Paralel işlem** → senaryolar aynı anda analiz edilsin (`Semaphore` ile sınırlı).
- **Durum diskten okunsun** → sunucu yeniden başlasa bile kaybolmasın; ileride kuyruk/Redis'e geçiş kolay.
- **Mock↔gerçek geçişi sadece `.env`** → kod değişmeden; test/geliştirme mock'la, üretim gerçekle.
- **Davranış dallanması yok** (`if mock` / `if type` yok) → her varyant ayrı sınıf + registry + DI.
- **Job bazlı özelleştirme**: `job_id` (ya da `parameter1`) → `config/profiles.json`'dan analiz
  profili seçilir: hangi kanıt prompt'a girer **ve** o kanıtın içine hangi kurallar uygulanır
  (kes/seç/ekle). Yeni job = config satırı, kod değişmez.
