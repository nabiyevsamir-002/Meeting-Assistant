"""Mətn üzərində sürət/dəqiqlik köməkçiləri.

  E — correct_transcript(): STT-nin (ElevenLabs/Azure) az-AZ-də ingilis texniki
      terminlərdə etdiyi tez-tez rast gəlinən səhvləri düzəldir. Aşkarlamadan
      əvvəl tətbiq olunur → həm sualın tanınması, həm cavab dəqiqliyi artır.

  A — has_question_signal(): LLM sual aşkarlamadan ƏVVƏL ucuz lokal yoxlama.
      Seqmentdə sual əlaməti yoxdursa LLM çağırışı atlanır (sürət + xərc).
      Prinsip: "yanlış müsbət" təhlükəsizdir (sadəcə LLM işə düşür), amma
      əsl sualı ötürmək OLMAZ — ona görə filtr qəsdən "geniş" tutulub.
"""
import re

# --- E: STT texniki-termin lüğəti (çoxsözlülər əvvəl gəlməlidir) ---
_GLOSSARY: list[tuple[str, str]] = [
    (r"\bepi[ -]?yaydan\b", "API-dən"),      # "API-dən" → "epi yaydan"
    (r"\bey[ -]?pi[ -]?ay\b", "API"),
    (r"\bepi\b", "API"),
    (r"\bes[ -]?kyu[ -]?el\b", "SQL"),
    (r"\bca[vw]a[ -]?skript\b", "JavaScript"),
    (r"\bbek[ -]?end\b", "backend"),
    (r"\bbeken[dt]\b", "backend"),
    (r"\bfront[ -]?end\b", "frontend"),
    (r"\bendp[oa]int\b", "endpoint"),
    (r"\bkl[ao]ud\b", "cloud"),
    (r"\bdedlay?n\b", "deadline"),
    (r"\bdeyta[ -]?beyz\b", "database"),
    (r"\bdeyta[ -]?beys\b", "database"),
    (r"\bfreym[ -]?vork\b", "framework"),
    (r"\bstart[ -]?ap\b", "startup"),
    (r"\bdok[k]er\b", "Docker"),
    (r"\bgit[ -]?hab\b", "GitHub"),
    (r"\bveb[ -]?huk\b", "webhook"),
    (r"\bto[uy]ken\b", "token"),
    (r"\bser[vw]er\b", "server"),
]
_GLOSSARY_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in _GLOSSARY]


def correct_transcript(text: str) -> str:
    """STT mətnindəki məlum texniki-termin səhvlərini düzəldir."""
    if not text:
        return text
    for rx, repl in _GLOSSARY_COMPILED:
        text = rx.sub(repl, text)
    return text


# --- A: lokal sual ön-filtri ---
# Dəqiq söz uyğunluğu ilə yoxlanan sual sözləri (inflected "nə*" formaları
# qəsdən tam sözlə verilir ki, "nəzər", "nəticə" kimi sözlər YANLIŞ müsbət
# verməsin — əks halda filtr heç vaxt işə yaramazdı).
_QWORDS = {
    "nə", "nədir", "nədən", "nəyə", "nələr", "nəçün",
    "niyə", "niə", "necə", "neçə", "neçəyə",
    "hansı", "hansını", "harada", "hara", "haraya", "haçan",
    "kim", "kimdir", "kimə", "kimlər",
    "sizcə", "olarmı", "varmı", "yoxdurmu", "doğrudurmu",
}
_QPHRASES = ("nə vaxt", "nə üçün", "nə qədər", "nə cür")
# Arxa-saitli sual enklitiki (mı/mu/mü) — demək olar həmişə sualdır
# ("varmı", "oldumu", "doğrudurmu"). Ön-saitli "mi" qəsdən buraxılıb, çünki
# "kimi", "sistemi", "problemi" kimi adi sözlər də onunla bitir.
_ENCLITIC = re.compile(r"\b\w+(mı|mu|mü)\b", re.IGNORECASE)


def has_question_signal(text: str, user_name: str = "") -> bool:
    """Seqmentdə sual əlaməti varmı? (LLM aşkarlamanı işə salmağa dəyərmi?)"""
    if not text:
        return False
    if "?" in text:
        return True
    low = text.lower()
    name = (user_name or "").strip().lower()
    if len(name) > 1 and name in low:
        return True
    words = set(re.findall(r"\w+", low))
    if words & _QWORDS:
        return True
    if any(p in low for p in _QPHRASES):
        return True
    if _ENCLITIC.search(low):
        return True
    return False
