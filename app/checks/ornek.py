"""Örnek check'ler — `ornek` profilinde çalışır, mekanizmayı göstermek içindir.

Üretim profillerinde kullanılmaz. Kendi check'ini yazarken bu dosyaya bakman
yeter: kayıt, boş dönüş, ham kanıt okuma, kendi başlığını yazma.
"""

from app.evidence.checks import CheckFacts, check


@check("ornek_senaryo_ozeti")
def ornek_senaryo_ozeti(facts: CheckFacts) -> str:
    """Koşumun bildirdiği iki gerçeği prompt'un başına koyar.

    Patlayan adım ve hata metni VisiumGo'dan geliyor; model bunları bugün koca
    logun içinde arıyor. Hazırsa vermek, aratmaktan ucuz.
    """
    satirlar = [
        f"{etiket}: {deger}"
        for etiket, deger in (
            ("Patlayan adım", facts.failed_step),
            ("Hata metni", facts.error_text),
        )
        if deger
    ]
    if not satirlar:
        return ""
    return "=== koşumun bildirdikleri ===\n" + "\n".join(satirlar)


@check("ornek_kanit_ozeti")
def ornek_kanit_ozeti(facts: CheckFacts) -> str:
    """Prompt'a KONMAYAN bir kanıttan ölçü alınabildiğini gösterir.

    `ornek` profilinde DOM `"prompt": false` ile iniyor: modele gitmiyor, ama
    burada okunabiliyor.
    """
    ham = facts.raw("HtmlEvidence")
    if not ham:
        return ""
    return f"Hata anındaki sayfanın DOM'u {len(ham)} karakterdi (prompt'a konmadı)."
