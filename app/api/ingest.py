"""Bilik bazası endpointləri (Phase 1).

/api/ingest       — n8n scraping workflow-u buraya POST edir
/api/ingest/file  — PDF/mətn faylının birbaşa yüklənməsi
/api/ingest/search — bilik bazasında axtarış (debug/nümayiş)
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile

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
    if name.lower().endswith(".pdf"):
        content = extract_pdf_text(data)
        source_type = "pdf"
    else:
        content = data.decode("utf-8", errors="replace")
        source_type = "text"
    return ingest_document(
        IngestRequest(title=name, content=content, source_type=source_type)
    )


@router.get("/search")
def search(q: str, top_k: int = 4) -> list[dict]:
    """Bilik bazasında semantik axtarış — agentin istifadə etdiyi eyni funksiya."""
    return search_context(q, top_k)


@router.get("/documents")
def documents() -> list[dict]:
    """Yüklənmiş sənədlərin siyahısı."""
    return repo.list_documents()
