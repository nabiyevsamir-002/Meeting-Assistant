"""Epizodik yaddaş — hər iclas Qdrant-da bir "epizod" kimi saxlanılır.

Semantik yaddaşdan (bilik bazası) fərqi: burada konkret hadisələr
("15 iyul iclasında X qərara alındı") saxlanılır və vaxt konteksti var.
"""
import logging

from app.config import get_settings
from app.models.core import new_id
from app.runtime import get_embedder, get_vectors
from app.providers.vector import VectorPoint

logger = logging.getLogger(__name__)


def store_episode(meeting_id: str, topic: str, summary_text: str,
                  actions_text: str, date: str) -> None:
    """İclas epizodunu vektorlaşdırıb episodes kolleksiyasına yazır."""
    settings = get_settings()
    embedder = get_embedder()
    vectors = get_vectors()
    collection = settings.qdrant_collection_episodes
    vectors.ensure_collection(collection, embedder.dim)

    text = f"İclas: {topic}. Xülasə: {summary_text}. Addımlar: {actions_text}"
    vectors.upsert(collection, [
        VectorPoint(
            id=new_id(),
            vector=embedder.embed_one(text),
            payload={
                "meeting_id": meeting_id,
                "topic": topic,
                "date": date,
                "text": text,
            },
        )
    ])
    logger.info("Epizod yazıldı: %s (%s)", topic, meeting_id)


def search_episodes(query: str, top_k: int = 3) -> list[dict]:
    """Keçmiş iclaslarda semantik axtarış."""
    settings = get_settings()
    embedder = get_embedder()
    vectors = get_vectors()
    collection = settings.qdrant_collection_episodes
    vectors.ensure_collection(collection, embedder.dim)

    hits = vectors.search(collection, embedder.embed_one(query), top_k)
    return [
        {
            "score": round(h.score, 4),
            "meeting_id": h.payload.get("meeting_id"),
            "topic": h.payload.get("topic"),
            "date": h.payload.get("date"),
            "text": h.payload.get("text"),
        }
        for h in hits
    ]
