"""Ingest xidməti: sənəd -> parçalar -> embedding -> vektor bazası.

Sənədlər iki yolla gəlir:
  1. n8n scraping workflow-u /api/ingest endpointinə POST edir
     (veb səhifə, PDF, OCR nəticəsi)
  2. İstifadəçi PDF/mətn faylını birbaşa /api/ingest/file ilə yükləyir
"""
import logging

from app.config import get_settings
from app.ingestion.chunker import chunk_text
from app.models.core import IngestRequest, IngestResult, new_id
from app.providers.vector import VectorPoint
from app.runtime import get_embedder, get_vectors
from app.storage import repo

logger = logging.getLogger(__name__)


def ingest_document(req: IngestRequest) -> IngestResult:
    """Sənədi parçalayıb embedding-ləri vektor bazasına yazır."""
    settings = get_settings()
    embedder = get_embedder()
    vectors = get_vectors()

    chunks = chunk_text(req.content, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        raise ValueError("Sənədin məzmunu boşdur")

    doc_id = new_id()
    collection = settings.qdrant_collection_context
    vectors.ensure_collection(collection, embedder.dim)

    # Bütün parçalar bir sorğu ilə embedding-lənir (daha sürətli/ucuz)
    embeddings = embedder.embed(chunks)
    points = [
        VectorPoint(
            id=new_id(),
            vector=emb,
            payload={
                "doc_id": doc_id,
                "title": req.title,
                "source_type": req.source_type,
                "url": req.url,
                "meeting_topic": req.meeting_topic,
                "chunk_index": i,
                "text": chunk,
            },
        )
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]
    vectors.upsert(collection, points)

    repo.save_document(doc_id, req.title, req.source_type, req.url,
                       req.meeting_topic, len(chunks))
    logger.info("Sənəd yükləndi: «%s» (%d parça, backend=%s)",
                req.title, len(chunks), vectors.name)

    # Frontend mərhələ göstəricisi üçün: parçalar yazıldı
    from app.services import ingest_status

    ingest_status.set(doc_id, title=req.title, stage="saved",
                      chunks=len(chunks), qa=0, done=False)

    # J: öncədən Q&A hazırlığı — arxa planda (yükləmə cavabını gözlətmir),
    # beləliklə canlı iclasda uyğun sual gələndə cavab hazır olur.
    if settings.prepared_qa_enabled:
        import threading

        from app.services import prepared_qa

        threading.Thread(
            target=prepared_qa.build_from_text, args=(req.content, doc_id), daemon=True
        ).start()
    else:
        # J söndürülübsə mərhələ dərhal tamamlanmış sayılır
        ingest_status.set(doc_id, stage="done", done=True, qa=0)

    return IngestResult(doc_id=doc_id, title=req.title,
                        chunk_count=len(chunks), backend=vectors.name)


def search_context(query: str, top_k: int | None = None) -> list[dict]:
    """Bilik bazasında semantik axtarış — agentin əsas aləti."""
    settings = get_settings()
    embedder = get_embedder()
    vectors = get_vectors()
    collection = settings.qdrant_collection_context
    vectors.ensure_collection(collection, embedder.dim)

    hits = vectors.search(collection, embedder.embed_one(query),
                          top_k or settings.search_top_k)
    return [
        {
            "score": round(h.score, 4),
            "title": h.payload.get("title"),
            "text": h.payload.get("text"),
            "source_type": h.payload.get("source_type"),
            "url": h.payload.get("url"),
        }
        for h in hits
    ]


def extract_pdf_text(data: bytes) -> str:
    """Yüklənmiş PDF-dən mətn çıxarır.

    Əvvəlcə pdfplumber (tərtibat/cədvəlləri daha yaxşı saxlayır, sütunları
    qarışdırmır), az mətn versə pypdf-ə keçir. Skan/şəkil PDF-lərdə mətn qatı
    olmadığı üçün nəticə boş qala bilər — çağıran yer bunu yoxlayır.
    """
    import io

    text = ""
    # 1) pdfplumber — mürəkkəb tərtibatlar üçün daha keyfiyyətli
    try:
        import pdfplumber

        parts = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
                # Cədvəlləri sətir kimi əlavə et (semantik axtarış üçün faydalı)
                for tbl in (page.extract_tables() or []):
                    for row in tbl:
                        cells = [c for c in (row or []) if c]
                        if cells:
                            parts.append(" | ".join(cells))
        text = "\n".join(p for p in parts if p).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("pdfplumber çıxarışı alınmadı, pypdf-ə keçilir: %s", exc)

    # 2) Ehtiyat: pdfplumber az mətn veribsə pypdf sınanır
    if len(text) < 40:
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            alt = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
            if len(alt) > len(text):
                text = alt
        except Exception as exc:  # noqa: BLE001
            logger.warning("pypdf çıxarışı da alınmadı: %s", exc)

    return text
