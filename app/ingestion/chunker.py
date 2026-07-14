"""Mətn parçalama (chunking) — sənədləri embedding üçün hissələrə bölür.

Strategiya: təxminən CHUNK_SIZE simvolluq pəncərələr, cümlə sərhədində
kəsilməyə üstünlük verilir, parçalar arasında CHUNK_OVERLAP qədər
üst-üstə düşmə saxlanılır (kontekst itkisini azaltmaq üçün).
"""
import re


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """Mətni üst-üstə düşən parçalara bölür."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            # Pəncərənin son 200 simvolunda cümlə sonu axtarırıq
            window = text[max(start, end - 200):end]
            m = None
            for m in re.finditer(r"[.!?…]\s", window):
                pass  # sonuncu uyğunluğu tapırıq
            if m:
                end = max(start, end - 200) + m.end()
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        # Növbəti parça overlap qədər geriyə çəkilərək başlayır
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]
