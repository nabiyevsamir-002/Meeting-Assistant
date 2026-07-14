"""Uzunmüddətli yaddaş: mem0 (real) | SQLite (mock).

İclas bitəndə əsas faktlar (xülasə, qərarlar, action-lar) uzunmüddətli
yaddaşa yazılır — gələcək iclaslarda "keçən dəfə nə danışmışdıq?"
sualına cavab vermək üçün.

mem0 real rejimdə OPENAI_API_KEY tələb edir (faktları LLM ilə çıxarır)
və vektorları Qdrant-da saxlayır.
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from app.config import Settings
from app.models.core import new_id

logger = logging.getLogger(__name__)


class BaseLongTermMemory(ABC):
    """Uzunmüddətli yaddaş provayderlərinin interfeysi."""

    name: str = "base"

    @abstractmethod
    def add(self, text: str, *, meeting_id: Optional[str] = None,
            meta: Optional[dict[str, Any]] = None) -> None:
        """Faktı yaddaşa yazır."""

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Yaddaşda axtarış aparır."""


class MockLongTermMemory(BaseLongTermMemory):
    """SQLite üzərində sadə saxlama + LIKE axtarışı."""

    name = "mock"

    def add(self, text: str, *, meeting_id: Optional[str] = None,
            meta: Optional[dict[str, Any]] = None) -> None:
        from app.storage import repo

        repo.save_long_term(new_id(), meeting_id, "episode", text, meta or {})

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        from app.storage import repo

        return [
            {"text": r["text"], "meta": r["meta"], "created_at": r["created_at"]}
            for r in repo.search_long_term(query, limit)
        ]


class Mem0LongTermMemory(BaseLongTermMemory):
    """mem0 kitabxanası üzərində real uzunmüddətli yaddaş."""

    name = "mem0"

    def __init__(self, settings: Settings) -> None:
        from mem0 import Memory

        # mem0 konfiqurasiyası: LLM=OpenAI, vektor bazası=Qdrant
        config = {
            "llm": {
                "provider": "openai",
                "config": {"model": settings.openai_model,
                           "api_key": settings.openai_api_key},
            },
            "embedder": {
                "provider": "openai",
                "config": {"model": settings.openai_embedding_model,
                           "api_key": settings.openai_api_key},
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {"url": settings.qdrant_url,
                           "collection_name": "mem0_memories"},
            },
        }
        self._memory = Memory.from_config(config)

    def add(self, text: str, *, meeting_id: Optional[str] = None,
            meta: Optional[dict[str, Any]] = None) -> None:
        self._memory.add(
            text, user_id="samir",
            metadata={**(meta or {}), "meeting_id": meeting_id},
        )

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        # mem0-un yeni versiyaları user_id-ni filters içində istəyir,
        # köhnələri isə birbaşa parametr kimi — hər ikisini dəstəkləyirik
        try:
            res = self._memory.search(query, filters={"user_id": "samir"}, limit=limit)
        except (TypeError, ValueError):
            res = self._memory.search(query, user_id="samir", limit=limit)
        results = res.get("results", res) if isinstance(res, dict) else res
        return [
            {"text": r.get("memory", ""), "meta": r.get("metadata", {}),
             "score": r.get("score")}
            for r in results
        ]


def create_long_term_memory(settings: Settings) -> BaseLongTermMemory:
    """LONGTERM_PROVIDER dəyişəninə görə yaddaş qurur."""
    if settings.longterm_provider.lower() == "mem0":
        if settings.openai_api_key:
            try:
                return Mem0LongTermMemory(settings)
            except Exception as exc:  # noqa: BLE001
                logger.warning("mem0 qurulmadı (%s) — mock istifadə olunur", exc)
        else:
            logger.warning("mem0 üçün OPENAI_API_KEY lazımdır — mock istifadə olunur")
    return MockLongTermMemory()
