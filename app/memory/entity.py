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
        # SÜRƏT: canlı iclasda hər seqmentə LLM çağırışı etməmək üçün mətnlər
        # yığılır və iclasın sonunda toplu şəkildə emal olunur (flush)
        self._deferred: list[str] = []

    def defer(self, text: str) -> None:
        """Mətni sonrakı toplu emal üçün növbəyə qoyur (canlı axını yavaşlatmır)."""
        self._deferred.append(text)

    def flush(self) -> None:
        """Yığılmış mətnlərdən varlıqları toplu çıxarır (iclas sonunda çağırılır)."""
        if not self._deferred:
            return
        # Çox uzun iclaslarda tək prompt şişməsin — ~4000 simvolluq qruplarla
        group: list[str] = []
        size = 0
        for t in self._deferred:
            if size + len(t) > 4000 and group:
                self.update("\n".join(group))
                group, size = [], 0
            group.append(t)
            size += len(t)
        if group:
            self.update("\n".join(group))
        self._deferred = []

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
