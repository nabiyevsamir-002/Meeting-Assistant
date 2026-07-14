"""Sağlamlıq yoxlaması — deployment monitorinqi üçün."""
from fastapi import APIRouter

from app.config import get_settings
from app.runtime import get_embedder, get_llm, get_stt, get_vectors

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Tətbiqin və aktiv provayderlərin vəziyyətini qaytarır."""
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "providers": {
            # Hansı provayderlərin aktiv olduğu burada görünür —
            # mock görürsünüzsə, uyğun API açarı .env-də yoxdur
            "llm": get_llm().name,
            "stt": get_stt().name,
            "embeddings": get_embedder().name,
            "vector_store": get_vectors().name,
        },
    }
