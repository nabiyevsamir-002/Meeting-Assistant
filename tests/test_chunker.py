"""Mətn parçalama testləri."""
from app.ingestion.chunker import chunk_text


def test_short_text_single_chunk():
    """Qısa mətn tək parça olmalıdır."""
    assert chunk_text("Qısa mətn.", chunk_size=100) == ["Qısa mətn."]


def test_empty_text_no_chunks():
    """Boş mətn parça verməməlidir."""
    assert chunk_text("   ") == []


def test_long_text_chunks_with_overlap():
    """Uzun mətn üst-üstə düşən parçalara bölünməlidir."""
    text = " ".join(f"Cümlə nömrə {i} burada bitir." for i in range(100))
    chunks = chunk_text(text, chunk_size=300, overlap=50)
    assert len(chunks) > 1
    # Hər parça limiti aşmamalıdır (cümlə sərhədi səbəbindən kiçik fərq ola bilər)
    assert all(len(c) <= 320 for c in chunks)
    # Bütün mətn əhatə olunmalıdır — son cümlə sonuncu parçada olmalıdır
    assert "nömrə 99" in chunks[-1]
