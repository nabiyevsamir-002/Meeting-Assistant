"""Bilik bazası endpointləri (Phase 1).

/api/ingest       — n8n scraping workflow-u buraya POST edir
/api/ingest/file  — PDF/mətn faylının birbaşa yüklənməsi
/api/ingest/search — bilik bazasında axtarış (debug/nümayiş)
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.deps import require_user
from app.ingestion.service import extract_pdf_text, ingest_document, search_context
from app.models.core import IngestRequest, IngestResult
from app.storage import repo

router = APIRouter(dependencies=[Depends(require_user)])


@router.post("", response_model=IngestResult)
def ingest(req: IngestRequest) -> IngestResult:
    """Sənədi qəbul edir, parçalayır, embedding-ləyib vektor bazasına yazır."""
    try:
        return ingest_document(req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/file", response_model=IngestResult)
async def ingest_file(file: UploadFile) -> IngestResult:
    """PDF və ya mətn faylını yükləyib bilik bazasına salır."""
    data = await file.read()
    name = file.filename or "document"

    def _process() -> IngestResult:
        # PDF çıxarışı (CPU) + embedding (şəbəkə) sinxrondur — event loop-u
        # kilidləməmək üçün thread hovuzunda icra olunur
        if name.lower().endswith(".pdf"):
            content = extract_pdf_text(data)
            # Skan/şəkil PDF-lərdə mətn qatı olmur → aydın izah veririk
            if len((content or "").strip()) < 40:
                raise HTTPException(
                    status_code=422,
                    detail=("PDF-də oxunacaq mətn tapılmadı — çox güman skan/şəkil "
                            "əsaslı PDF-dir. Mətni seçilə (kopyalana) bilən PDF yükləyin."),
                )
            source_type = "pdf"
        else:
            content = data.decode("utf-8", errors="replace")
            source_type = "text"
        return ingest_document(
            IngestRequest(title=name, content=content, source_type=source_type)
        )

    return await run_in_threadpool(_process)


@router.get("/search")
def search(q: str, top_k: int = 4) -> list[dict]:
    """Bilik bazasında semantik axtarış — agentin istifadə etdiyi eyni funksiya."""
    return search_context(q, top_k)


@router.get("/status/{doc_id}")
def ingest_status_ep(doc_id: str) -> dict:
    """Yükləmə mərhələsi — frontend PDF emalını canlı göstərmək üçün poll edir."""
    from app.services import ingest_status

    return ingest_status.get(doc_id) or {
        "doc_id": doc_id, "stage": "unknown", "done": True, "qa": 0,
    }


@router.get("/documents")
def documents() -> list[dict]:
    """Yüklənmiş sənədlərin siyahısı."""
    return repo.list_documents()
