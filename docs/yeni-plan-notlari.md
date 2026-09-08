# Yeni Plan — Çalışma Notları (canlı belge)

> Bu dosya, yeni isterlerin konuşulduğu oturumun notudur. Konular tek tek karara bağlanıp
> buraya yazılır; bitince `plan.md` v4 olarak yeniden yazılacak (eski md'ler silinebilir).

## Konu listesi (sıra)

1. **Regresyon** — LLM cevapları neden kötüleşti?
2. **Profil/config** — hangi job'da hangi veri prompt'a girer, attachment'lar nasıl düzenlenir
3. **Job-level analiz** — job'ın kendisi patladıysa build log'dan "neden patladı"
4. **Ölçüm** — kaliteyi sayıya çevirme (eval seti, prompt sürümü)
5. **Dokümanlar** — eski md'leri silip yeniden yazma

## 1. Regresyon — konuşulanlar

Kullanıcı: "Daha önce LLM düzgün cevaplar veriyordu, proje değiştikten sonra vermemeye başladı."

Git diff'ten çıkan dört şüpheli (tahmin değil, `git diff f69c835 HEAD -- config/prompt_template.txt`):

1. **Anlamsal bağlam kaybı** — prompt'ta eskiden `Banka: X` + `Platform: web|mobile|hybrid` ve
   platformun hatayı nasıl değiştirdiğini anlatan bir paragraf vardı. Şimdi yerinde
   `Parametre1: default` / `Parametre2: default` var; çoğu koşumda kelimenin tam anlamıyla
   "default" yazıyor = modele sıfır bilgi.
2. **"Pes etme" baskısı** — yeni kural 3-4 modele "eksik kanıt gerekçe değildir, unknown son
   çaredir" diyor. Fazla itmiş olabiliriz: kendinden emin ama yanlış teşhis.
3. **build.log şişmesi** — `keep_scenario_section` senaryo adını `build.log` içindeki
   `> Scenario [...]` ile eşleştiremezse hiçbir şey kesmiyor; tüm job logu her senaryonun
   prompt'una giriyor olabilir. (plan.md A16 bu eşleşmenin doğrulanmadığını yazıyor.)
4. **Model/endpoint değişimi** — temperature=0 olduğu için aynı prompt + aynı model = aynı
   cevap. Değiştiyse ya prompt ya model değişmiştir. `meta.llm_model` her satırda kayıtlı.

Ölçüm imkânı: `prompts/` ve `llm_responses/` tabloları diskte duruyor → eski/yeni prompt A/B.

## 1. Regresyon — KÖK NEDEN ve KARARLAR

**Belirti:** model sürekli "kanıt yok" diyor.

**Kök neden (prompt sorunu değil, config/iş mantığı sorunu):** `config/profiles.json`'daki tek
profil (`default`) `evidence_to_llm` olarak yalnız `TestLogEvidence`, `HtmlEvidence`,
`BrowserLogEvidence` gönderiyor. DOM ve test.log üretmeyen joblarda üç blok da yer tutucu oluyor,
**build log ise hiç girmiyor** → model boş bir prompt alıyor ve haklı olarak "kanıt yok" diyor.

**Kararlar:**

1. **Build log profilden yönetilir.** Kullanıcının açıkça tanımladığı joblarda prompt'a girer.
2. **`default` profil değişmez** — build log default'ta gitmez. (Tuzak bilinerek kabul edildi:
   tanımsız job'ta senaryo kanıtı da yoksa prompt boş kalır → bkz. madde 3.)
3. **Boş prompt'a LLM çağrısı yapılmaz.** Bütün bloklar yer tutucuysa model çağrılmaz; sonuç
   "bu senaryo için kanıt üretilmemiş" olarak kaydedilir. (Bugün çağrılıyor ve aynı cevap parayla
   alınıyor.)
4. **Prompt'a tek dokunuş:** "elindeki tek kanıt build log ise teşhisi ondan üret". Mevcut
   "eksik kanıt normaldir" paragrafı modele *neyi kullanacağını* söylemiyor, sadece *şikayet etme*
   diyor — yanlış yönlendiren kural bu.
5. Prompt genel olarak **bozulmayacak**; küçük ve hedefli düzeltme yapılacak.

**Kapsanmayan (Konu 3'e devredildi):** job'ın kendisi faile düştüyse, senaryo hatasından
**farklı** bir durum olarak ayrı prompt + regex ile "bu job neden patlamış olabilir" sorulacak.

## 2. Profil / prompt sistemi — KARARLAR

Kullanıcının cümlesi: *"889-890 için build log al, senaryo senaryo kes; 223-234 için test.log'un
error satırını al; 1321-1323 için tüm test.log + DOM."* → Bu, bugünkü `profiles.json`'un tam
olarak yaptığı iş; eksik olan dosyanın **doldurulmamış** olması.

**Kararlar:**

1. **Job grubu = profil.** `job_ids` + `evidence_to_llm` + `rules` (+ yeni: `prompt`,
   `extra_context`). Yeni job = config satırı, kod değil.
2. **Job başına ayrı prompt şablonu.** Başlangıç seti **5 şablon**:
   `default` · `web` (DOM + browser.log + test.log) · `mobile` (test.log) · `hybrid`
   (web + mobil adım bir arada) · `buildlog` (yalnız build log).
   Şablonlar `config/prompts/` altında; profil `"prompt": "mobile"` diyerek seçer.
3. **Ortak sözleşme tek dosyada** (`_sozlesme.txt`): JSON şeması + 6 verdict + 5 confidence
   kovası her şablona **sistem tarafından** eklenir. Gerekçe: 5 şablonda 5 kez bakım edilen bir
   şema er geç dolar ve parse sessizce bozulur.
4. **`extra_context`** ile job grubuna cümle eklenir ("Bu joblar mobil bankacılık joblarıdır").
5. **Kural sözlüğü genişletmesi ertelendi** — gerçek joblar yazılırken tek tek karara bağlanacak.
   Bilinen eksik: "eşleşme civarı ±N satır" (hata civarını almak) bugün ifade edilemiyor.

## 3. Job-level analiz — ERTELENDİ (iskelet şimdi, içi sonra)

- Kullanıcı: *"çok ileri bir feature."* Önce başarılı koşan jobların hatalı senaryoları.
- Bilinen: başarılı joblarda `runResult.state == "PASSED"`. Hatalı hâllerin değerlerini
  kullanıcı sonra verecek.
- Ayrı prompt + regex ile "bu job neden patlamış olabilir" sorulacak; senaryo hatasından
  **farklı** bir akış.
- Açık: çıktı şeması aynı 6 verdict mi, job'a özel mi? (karara bağlanmadı)

## Ertelenenler

- Koşum sonu **aksiyon listesi** (verdict'e göre gruplu özet): "şimdilik gerek yok".

## 4. Ölçüm — KARAR

İskelet **şimdi** kurulacak: golden set klasörü + koşturucu (boş setle çalışır), gerçek örnekler
sonradan doldurulacak. Ayrıca prompt sürümü/hash'i `meta`'ya yazılacak (bugün hangi prompt
sürümünün hangi cevabı ürettiği kayıtlı değil).

## 5. Dokümanlar — KARAR

`plan.md` **v4** olarak baştan yazılacak · `CHANGELOG.md` **korunacak** (dış hafıza; hangi
kararın neden alındığı orada) · `README.md` + `docs/` (nasil-calisir, akis-semasi, proje-rehberi)
iş bitince tek seferde yenilenecek.

## Uygulama sırası (öneri)

1. **Profil + prompt sistemi** — `config/prompts/` (5 şablon + `_sozlesme.txt`), profilde
   `prompt` alanı, şablon+sözleşme birleştirme.
2. **Konu 1 iş mantığı** — boş prompt'ta LLM çağrısı yok; "tek kanıtın build log ise ondan
   teşhis üret" cümlesi; **kanıt eşleşme raporu** (hangi attachment hangi Evidence'a eşleşti,
   eşleşemeyen var mı, blok dolu mu/yer tutucu mu, prompt boyutu) → bir sonraki gerçek koşum
   kendi teşhisini versin.
3. **Ölçüm iskeleti** — golden set + koşturucu + prompt sürümü meta'da.
4. **Job-level iskelet** — tasarım plan.md'ye, kodda yalnız genişleme noktası.
5. **plan.md v4.**

## Uygulama durumu

- [x] **1/5 — Profil + prompt sistemi.** `config/prompts/` (default/web/mobile/hybrid/buildlog +
      `_contract.txt`), profilde `prompt` alanı, her kanıt kendi placeholder'ı, açılışta doğrulama.
      `.env`: `PROMPT_TEMPLATE_PATH` → `PROMPTS_DIR`.
- [x] **2/5 — Boş prompt'a çağrı yok + kanıt eşleşme raporu.** `no_evidence` durumu;
      `evidence_report` (attachments/blocks/unmatched) + `prompt_chars`.
- [x] **3/5 — Ölçüm iskeleti.** `meta.prompt_template` + `meta.prompt_version`; `evals/` paketi
      (`python -m evals.runner`, boş set + örnek biçim); `try_json` public.
- [x] **4/5 — Job-level: tasarım yazıldı, kod yazılmadı** (plan.md A18). Gerçek `state` değerleri
      gelince config + şablon + tek dağıtım noktasıyla kodlanacak.
- [x] **5/5 — plan.md v4** + README/docs hizalandı; CHANGELOG korundu.

## Kullanıcı sorusu (2026-09-08): "senaryo bazlı test.log, bazen sadece job bazlı build.log —
## proje bunu karşılıyor mu?"

**Evet, karşılıyor** — üç şartla:

1. O joblar için `profiles.json`'a satır: `"evidence_to_llm": ["BuildLogEvidence"]` +
   `"prompt": "buildlog"`. (Default profil build log göndermiyor — kullanıcı kararı.)
2. Dilimleme kuralı: `keep_scenario_section`, `start: "> Scenario [{scenario_name}] started"`,
   `end: "beforeScenario:"`. Gerçek formatla test edildi (2026-09-01 doğrulaması + yeni test).
3. **Risk:** `/results`'taki senaryo adı ile build.log'daki `[...]` içeriği birebir eşleşmezse
   kural hiçbir şey kesmez → tüm job logu her senaryonun prompt'una gider. 2/5 adımında bu
   **görünür** hâle getirildi (rapor: `trimmed=false` + ham boyut), ama eşleşmeyi garanti eden
   bir şey yok. İş-pc'de ilk gerçek koşum bunu söyleyecek.
