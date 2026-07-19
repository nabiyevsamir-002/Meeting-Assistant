"""Yaddaş endpointləri — keçmiş iclaslarda axtarış (Phase 3)."""
from fastapi import APIRouter, Depends

from app.api.deps import require_user
from app.config import get_settings

router = APIRouter(dependencies=[Depends(require_user)])


@router.get("/stats")
def stats() -> dict:
    """UI dashboard-u üçün ümumi göstəricilər."""
    from app.storage import repo

    return repo.get_stats()


@router.get("/search")
def search_memory(q: str) -> dict:
    """Epizodik (Qdrant) və uzunmüddətli (mem0/mock) yaddaşda birgə axtarış."""
    from app.memory.episodic import search_episodes
    from app.memory.long_term import create_long_term_memory

    ltm = create_long_term_memory(get_settings())
    return {
        "query": q,
        "episodes": search_episodes(q),      # vektor axtarışı (Qdrant/in-memory)
        "long_term": ltm.search(q),          # mem0 və ya SQLite mock
    }
