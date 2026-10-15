# VisiumGo Test Analyzer

Başarısız bir test koşumunun kanıtlarını VisiumGo'dan çeker, kurum içi modele sorar ve
her senaryo için yapılandırılmış bir ön teşhis döndürür.

Soru her zaman aynı: **hata testin kendisinden mi, uygulamadan mı, ortamdan mı
kaynaklanıyor, yoksa geçici mi?**

---

## Kurulum

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

`.env` içinde doldurulması **zorunlu** iki alan var:

```
VISIUMGO_BASE_URL=
VISIUMGO_TOKEN=
```

Geri kalan her ayarın çalışır bir varsayılanı vardır.

## Çalıştırma

```bat
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Tek süreç çalıştırın. `--workers 2` ile iki süreç de açılışta aynı yarım koşumu devam
ettirir ve model iki kez çağrılır.

---

## Kullanım

### Analiz başlat

```
POST /analyze/visiumgo
{ "profil": "web", "job_id": "868" }
```

`job_id` yerine `run_id` da verilebilir; ikisinden en az biri zorunludur. `job_id`
verilirse o job'un **en yeni bitmiş** koşumu seçilir (süren koşumlar atlanır).

Cevap hemen döner, iş arka planda başlar:

```json
{ "analyzer_run_id": "8e2a1c55-...", "status": "pending" }
```

### Sonucu al

```
GET /analyze/visiumgo/{analyzer_run_id}
```

```json
{
  "status": "done",
  "profil": "web",
  "profile_name": "web",
  "job_name": "yeni-ty-internet-bank-kritik",
  "resume_count": 0,
  "scenario_count": 13,
  "completed_count": 13,
  "note": "13 senaryo 4 gruba indi (aynı adım + aynı hata mesajı); her grup için tek cevap üretildi",
  "results": [
    {
      "scenario_name": "Bireysel Vadesiz Hesap Açılışı TL Birimi- YENİ",
      "scenario_id": "1:Bireysel/Hesap Islemleri/HesapAcilislari.feature:60_1341818141:1",
      "verdict": "test_maintenance",
      "confidence": 0.75,
      "root_cause": "...", "explanation": "...", "suggestion": "...",
      "error_text": "Failed to interact with Sms Onay Sifresi",
      "failed_step": "Sms Onay Sifresi öğesini görürüm",
      "grouped_with": "",
      "status": "ok",
      "meta": {
        "answered_by": "llm",
        "llm_model": "qwen3-coder-next",
        "prompt_template": "web",
        "prompt_version": "90c2677f74",
        "input_tokens": 11843, "output_tokens": 312, "duration_ms": 48219,
        "analyzed_at": "2026-10-14T12:00:00+00:00"
      }
    }
  ]
}
```

`meta.answered_by`: `llm` · `group` (grup temsilcisinin cevabı) · `known_errors` (katalogdan).
`status`: `pending` → `running` → `done` (ya da `failed`).
Satır bazında `status`: `ok` · `no_evidence` · `analysis_failed`; neden olduğu
`failure_reason` alanında yazar.

---

## Profiller

Profili **isteği atan seçer**. İçerikleri `config/profiles.json` dosyasındadır.

| profil | kanıt | kırpma |
|---|---|---|
| `web` | `test.log` · `browser.default.log` · `browser.default.html` | HTML tam kırpılır; test.log'da base64 |
| `mobil` | `test.log` · `mobile.<os>.<cihaz>.xml` | base64 |
| `finart` | `build.log` (yalnız o senaryonun bölümü) | senaryo bölümü kesilir |
| `error` | `build.log` (koşumun tamamı) | yok |
| `ornek` | `test.log` · `browser.default.html` (**prompt'a girmez**) | base64 |

- **`error` koşum seviyesidir:** senaryo satırları hiç okunmaz, koşumun kendisi için
  **tek** teşhis üretilir. Jenkins'te başlatılamayan koşum için budur.
- Koşumun kendisi çöktüğünde (`runResult.state=FAILED`) sistem, hangi profil istenirse
  istensin `error`'u uygular ve bunu koşum notuna yazar.
- Listede olmayan kanıt **hiç indirilmez**. Ekran görüntüleri hiçbir profilde gitmez.
- **`ornek`** üretim profili değildir: `checks` mekanizmasını çalışır hâlde göstermek için
  duruyor (`app/checks/ornek.py`). İstemiyorsan profili, şablonunu ve o dosyayı silebilirsin.

## Hesaplanan bilgiler (checks)

Modelin kendi başına güvenilir çıkaramayacağı, ama koddan **kesin** hesaplanabilen bir
bilgiyi prompt'a koymak için. Kanıtın yerine geçmez, yanına girer.

Üç parça birbirini kilitler:

**1 · Method** — `app/checks/` altında, adıyla kaydedilir:
```python
@check("dom_kontrolu")
def dom_kontrolu(facts) -> str:
    if not facts.has("HtmlEvidence"):
        return ""  # boş dönerse prompt'a hiçbir şey girmez
    return f"Aranan element sayfada {facts.raw('HtmlEvidence').count('Hesap Aç')} kez geçiyor."
```

**2 · Profil** — hangi profilde çalışacağı (`config/profiles.json`):
```json
"web": { "prompt": "web", "evidence": [ ... ], "checks": ["dom_kontrolu"] }
```

**3 · Şablon** — çıktısının **nereye** gireceği (`config/prompts/web.txt`):
```
$dom_kontrolu
```

Bir profil birden çok check çalıştırabilir ve her birinin metni şablonda ayrı bir yere
konabilir — başa, ortaya, sona.

`facts` içinde: `scenario_name` · `scenario_id` · `failed_step` · `error_text` ·
`profile_name` · `job_log` · `raw(ad)` · `shaped(ad)` · `has(ad)`.
`raw()` ile `shaped()` **farklı metinlerdir** ve fark önemli:

| | ne döndürür | ne zaman "" | kural kesemezse |
|---|---|---|---|
| `raw(ad)` | dosya nasıl geldiyse | kanıt hiç gelmediyse | etkilenmez |
| `shaped(ad)` | **modelin gördüğü** hâli | kanıt hiç gelmediyse | `RuleError` fırlatır |

**Arama `raw()` üzerinde yapılmalı** — `shaped()` kırpmadan geçmiştir, orada bulunamayan
şey bizim sildiğimiz için bulunamıyor olabilir.

**Ama dikkat:** `raw()` ile hesaplayıp prompt'a yazdığın bir olguyu model `shaped()`
üzerinden doğrulayamayabilir. Kırpma o bilgiyi silmişse model "ben göremiyorum" der ve
senin olgunla çelişir. Böyle bir durumda ya metninde bunu söyle ("kırpılmamış sayfada
hesaplandı"), ya o kanıdın kırpma kurallarını kaldır.

`shaped()` kural hatasını yutmaz: "kanıt yok" ile "kural kesemedi" farklı şeylerdir ve
ikisini ayıramayan bir check, sayfayla ilgisi olmayan bir hata için "burada bir şey yok"
der. Fırlayan hata, her check hatasının yakalandığı yerde yakalanır ve koşum notuna yazılır.

Üç kural:
- Dönen metne dokunulmaz, olduğu gibi girer — başlık da senin metninin parçasıdır.
- Boş dönerse prompt, check hiç yokmuş gibi kalır.
- Patlarsa senaryo ölmez: metin basılmaz, sebebi koşumun `note` alanına yazılır.

Üçünden biri eksikse uygulama **açılmaz**: kayıtsız ad, şablonda yeri olmayan check, ya da
profilin çalıştırmadığı bir `$ad` — üçü de açılışta hata verir.

### Kanıtı modele göstermeden check'te kullanmak

`evidence` listesinde olmak "indirilir" demektir; prompt'a girmesi ayrı bir bayraktır:

```json
{ "name": "HtmlEvidence", "prompt": false }
```

Dosya iner, check `facts.raw("HtmlEvidence")` ile okur, ama prompt'ta blok olarak
görünmez. Varsayılan `prompt: true`.

## Nasıl çalışır

1. **Koşum seçilir** — `run_id` verildiyse o, yoksa job'un en yeni bitmiş koşumu.
2. **Başarısız senaryolar bulunur** — her biri için hata metni, patlayan adım ve ek
   dosya listesi okunur. Dosya içeriği bu adımda okunmaz.
3. **Gruplama** — aynı `(patlayan adım, hata mesajı)` çiftine düşen senaryolar bir
   grup olur. 300 senaryo 8 gruba inerse modele 8 kez sorulur, teşhis 300 satıra yazılır.
4. **Bilinen hatalar** — `config/known_errors.json` kataloğunda adım + hata birebir
   eşleşirse **hiçbir dosya okunmadan** cevap döner, model çağrılmaz.
5. **Kanıt okunur** — yalnız grup temsilcisinin, yalnız profilin istediği dosyalar.
6. **Kırpma** — profildeki kurallar sırayla uygulanır. Kesemeyen kural hata verir; o
   senaryo kapanır, koşum devam eder.
7. **Hesaplanan bilgiler** — profilin `checks` listesi çalışır, metinleri şablondaki
   kendi yerlerine girer.
8. **Prompt** — her kanıt kendi bloğunda, başında ne olduğu yazılı. Gelmeyen kanıttan
   prompt'ta hiç söz edilmez.
9. **Model** — tek atış. Cevap JSON şemasına uymazsa satır `analysis_failed` olur ve
   sebebi yazılır.
10. **Kayıt** — teşhisler `DATABASE_DIR` altına, modele giden/gelen metin `TRACE_DIR`
    altına yazılır.

Süreç analiz sırasında ölürse uygulama açılışta o koşumu bulur ve **kaldığı yerden**
devam eder: tamamlanmış teşhisler korunur, model onlar için yeniden çağrılmaz.

---

## Sık yapılan işler

### Yeni profil eklemek
1. `config/profiles.json`'a satır ekle: `prompt`, `evidence`, varsa `rules` ve `checks`.
2. `config/prompts/<prompt adı>.txt` dosyasını yaz.
3. Bitti — kod değişmez. Uygulama açılışta doğrular: olmayan kanıt adı, olmayan şablon,
   yeri olmayan check varsa **açılmaz** ve nedenini söyler.

### Kanıta kırpma kuralı eklemek
Profildeki o kanıdın `rules` listesine ekle; sırayla uygulanır.

| kural | ne yapar |
|---|---|
| `keep_scenario_section` | job log'undan yalnız o senaryonun bölümünü keser |
| `strip_tags` | verilen etiketleri içeriğiyle birlikte atar (`tags: [...]`) |
| `keep_attributes` | sayılanlar dışındaki öznitelikleri atar (`keep: [...]`, `*` ile önek) |
| `strip_base64` | uzun base64 dizisini `[base64 N karakter]` notuyla değiştirir (`min_chars`) |
| `collapse_whitespace` | boşluk ve boş satır yığınlarını daraltır |

Kesemeyen kural hata verir: o senaryo kapanır, **koşum devam eder**, sebep satırda yazar.

### Bilinen bir hataya hazır cevap koymak
`config/known_errors.json`'a satır ekle: `step` · `error` · `answer` · `verdict` ·
`confidence`. Eşleşme **birebir**; eşleşirse hiçbir dosya okunmadan cevap döner, model
çağrılmaz. Adımı ya da hata mesajı boş olan senaryo hiç eşleşmez.

### Bir şey ters gittiğinde nereye bakılır
| nereye | ne söyler |
|---|---|
| koşumun `note` alanı | profil zorlandı mı, kaç gruba indi, iz yazılamadı mı, check patladı mı |
| satırın `failure_reason` | o senaryo neden teşhis alamadı |
| satırın `meta.answered_by` | `llm` · `group` · `known_errors` |
| `TRACE_DIR` altındaki dosyalar | modele **tam olarak** ne gitti, **tam olarak** ne geldi |
| koşumun `build_log_error` | build log inemediyse sebebi |

## Bilinen sınırlar

- **Tek süreç.** `--workers 2` ile iki süreç de açılışta aynı yarım koşumu devam ettirir.
- **Kırpma eksik:** `test.log` ve `browser.default.log` ham gidiyor (base64 dışında),
  mobil arayüz ağacı da öyle. `error` profilinde build log'un tamamı gidiyor.
- **finart'ta son senaryo fazla alıyor:** bitiş işareti olmadığı için koşum kuyruğu
  (`Failed scenarios:` listesi, Gradle çıktısı) onun bölümüne giriyor.
- **Yalnız `FAILED` senaryolar analiz edilir**; `UNSTABLE` olanlar dışarıda.
- **`previousRetries` okunmuyor** — bir senaryonun önceki denemesi değerlendirilmiyor.
- **Mobil ağaca kırpma kuralı uygulanamaz:** `strip_tags` ve `keep_attributes` HTML
  ayrıştırıcısı kullanıyor ve etiket adlarını küçültüyor; XML büyük/küçük harfe duyarlı.

## Yapılandırma

Bütün ayarlar `.env` dosyasındadır, açıklamaları `.env.example` içindedir. En çok
dokunulanlar:

| ayar | ne yapar |
|---|---|
| `MAX_CONCURRENCY` | aynı anda kaç senaryo işlenir (süreç başına) |
| `TRACE_DIR` | modele giden prompt ve dönen cevap buraya yazılır; boş = kapalı |
| `DATABASE_DIR` | koşum ve teşhis kayıtları |
| `PRECHECK_PROVIDER` | `known_errors` (varsayılan) ya da `noop` |

Davranış değişikliklerinin çoğu config satırıdır: yeni profil, yeni kırpma kuralı ve
yeni bilinen hata için kod değişmez.

## Geliştirme

```bat
.venv\Scripts\python -m pip install -e ".[lint]"
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m mypy app
```
