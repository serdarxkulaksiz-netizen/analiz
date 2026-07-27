# Nasıl Çalışır? (yeni başlayanlar için)

> Projeyi ilk kez okuyan biri için, bir POST isteği atıldığında adım adım ne olduğunu,
> hangi method'un nereden çağrıldığını ve GET'in ne yaptığını sade dille anlatır.
> Görsel şema: [akis-semasi.md](akis-semasi.md).

## Büyük resim (restoran benzetmesi)

Projeyi bir **restoran** gibi düşün:

- **POST** = sipariş verirsin, garson "aldım, numaran bu" der ve gider (beklemez).
- **Arka plan** = mutfak yemeği hazırlar (asıl iş burada olur).
- **GET** = ara ara "hazır mı?" diye sorarsın.

Zincir **6 halka**dan oluşur, her biri ayrı dosyada ve birbirinden bağımsızdır:

```
Source → Extraction → Prompt → LLM → Parse → Persist
(veri çek) (kanıt düzenle) (soru yaz) (AI'ya sor) (cevabı ayrıştır) (diske yaz)
```

Her halka bir **arayüz** (interface) arkasındadır. Hangi gerçeklemenin (mock mu, gerçek mi)
kullanılacağı `.env`'den seçilir ve hepsi başta `app/main.py` → `build_service()` içinde birbirine
takılır. Buna **dependency injection** (bağımlılık enjeksiyonu) denir: parçaları dışarıdan takarız,
böylece mock↔gerçek geçişi kod değişmeden olur.

---

## 1) POST /analyze/visiumgo — sipariş

**Dosya:** `app/main.py` → `start_analysis()`

1. **FastAPI gövdeyi doğrular.** `AnalyzeRequest` modeli `{bank, platform, job_id | run_id}` bekler.
   İkisi de (job_id ve run_id) yoksa → `422` hata.
2. **`service.create_run(bank, job_id, platform, run_id)`** çağrılır (`app/service.py`):
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
   - **`self._source.fetch_job(bank, job_id, platform, run_id)`** — **Source** halkası
     (`MockSource` veya `VisiumGoSource`):
     - `VisiumGoSource`: run_id'yi çözer → `/results`'tan **FAILED** senaryoları alır → her senaryonun
       detayını (`errorText`, `stepResults`, `attachments`) çeker → attachment'ları indirir.
       Sonuç: `JobData` (içinde başarısız senaryoların listesi = `RawScenario`'lar).
   - `runs` dosyasını günceller (run_id, job adı, senaryo sayıları, ham cevap).
   - **Hata yoksa** → `status="done"`, not: "analiz edilecek hata yok". Biter.
   - **Hata varsa** → her senaryo için **`_analyze_scenario(...)`** paralel çalışır
     (`asyncio.gather` + `Semaphore`; aynı anda kaç tane olduğu config'ten).
   - Sonunda `status="done"`.

**`_analyze_scenario(scenario)`** — asıl zincir, her başarısız senaryo için:

1. `result_id` üretir (bu senaryonun izini 4 tabloda birbirine bağlayan anahtar).
2. **Ham kanıtı yazar** → `database/evidence/{result_id}.json`.
3. **`self._extractor.extract(scenario, ...)`** — **Extraction** halkası (`EvidenceExtractor`):
   - `EvidenceRegistry` ile attachment'ları (`mimeType` + `deviceId`'ye göre) Evidence sınıflarına eşler.
   - `Findings` üretir: LLM'e gidecek etiketli bloklar + hata mesajı + adımlar + eksik kanıtlar.
4. **`self._precheck.check(findings)`** — bugün `NoOpPreCheck`, her zaman `None` döner → LLM'e devam.
5. **`prompt = self._builder.build(findings)`** — **Prompt** halkası (`PromptBuilder`):
   şablonu (`config/prompt_template.txt`) doldurur.
6. **`response = await self._llm.complete(prompt)`** — **LLM** halkası
   (`MockLLMProvider` veya `OpenAICompatibleLLMProvider`):
   - Gerçek olan: LLM servisine POST atar, **ham cevabı olduğu gibi yakalar**, içinden `content`'i çıkarır.
7. **Prompt izini yazar** → `database/prompts/{result_id}.json` (gönderilen prompt + tam istek + ham cevap).
8. **LLM ham cevabını yazar** → `database/llm_responses/{result_id}.json`.
9. **`_try_json(response.content)`** — **Parse** halkası: LLM cevabındaki JSON'u yapıya çevirir.
   - Geçerliyse → teşhis alanları dolu (`verdict`, `root_cause`, ...), `status="ok"`.
   - Geçersiz/boşsa → `status="analysis_failed"` (alanlar boş, **ham cevap yine saklı**).
10. **Teşhisi yazar** → `database/analysis_results/{result_id}.json`.
11. Run dosyasındaki `completed_count`'u +1 yapar.

> LLM çağrısı patlarsa (ör. bağlantı hatası) o senaryo `analysis_failed` işaretlenir ama **job devam
> eder** — bir senaryo tüm koşuyu düşürmez.

---

## 3) GET /analyze/visiumgo/{id} — "hazır mı?"

**Dosya:** `app/main.py` → `get_analysis()` → **`service.get_run(id)`**

1. `database/runs/{id}.json`'u **diskten** okur (bellekten değil — bu bilinçli bir tasarım).
2. Bu run'a ait tüm `analysis_results` satırlarını okuyup `results` olarak ekler.
3. Döner: durum (`pending`/`running`/`done`/`failed`), kaç senaryodan kaçı bitti ve **biten teşhisler**.
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
- **Davranış dallanması yok** (`if mock` / `if platform` yok) → her varyant ayrı sınıf + registry + DI.
