"""Varlıq (entity) yaddaşı — iclasda kimlərin/nələrin xatırlandığını izləyir.

LangChain-in ConversationEntityMemory-sinin sadələşdirilmiş analoqu:
hər seqmentdən LLM structured output ilə varlıqlar çıxarılır və
ad üzrə birləşdirilərək saxlanılır. İclas sonunda hesabata düşür.
"""
import logging

from app.models.structured import Entity, EntityList
from app.prompts import EXTRACT_ENTITIES
from app.providers.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class EntityMemory:
    """Ad -> Entity xəritəsi; təkrar xatırlananlar qeydlə zənginləşir."""

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider
        self._entities: dict[str, Entity] = {}

    def update(self, text: str) -> None:
        """Mətndən varlıqları çıxarıb yaddaşa birləşdirir."""
        try:
            result = self._llm.generate_structured(
                EXTRACT_ENTITIES.format(text=text), EntityList
            )
        except Exception as exc:  # noqa: BLE001 — yaddaş xətası pipeline-ı dayandırmasın
            logger.warning("Entity çıxarılması alınmadı: %s", exc)
            return
        for ent in result.entities:
            existing = self._entities.get(ent.name)
            if existing:
                # Eyni varlıq yenidən xatırlanıb — qeydi yeniləyirik
                existing.note = ent.note or existing.note
            else:
                self._entities[ent.name] = ent

    def all(self) -> list[Entity]:
        """Bütün toplanmış varlıqlar."""
        return list(self._entities.values())

    def as_dicts(self) -> list[dict]:
        """Hesabat üçün dict formatı."""
        return [e.model_dump() for e in self._entities.values()]
