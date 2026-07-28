"""Vektor bazası abstraksiyası: Qdrant (real) | in-memory (mock).

VECTOR_BACKEND=auto rejimində əvvəlcə Qdrant-a qoşulmağa cəhd edilir,
əlçatan deyilsə in-memory saxlama işlədilir — beləliklə Docker/Qdrant
olmadan da tətbiq tam işləyir.
"""
import logging
import math
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class VectorPoint:
    """Bazaya yazılan bir nöqtə: vektor + istənilən payload."""
    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchHit:
    """Axtarış nəticəsi: oxşarlıq balı + payload."""
    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


class BaseVectorStore(ABC):
    """Vektor bazalarının ortaq interfeysi."""

    name: str = "base"

    @abstractmethod
    def ensure_collection(self, collection: str, dim: int) -> None:
        """Kolleksiya yoxdursa yaradır."""

    @abstractmethod
    def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        """Nöqtələri yazır/yeniləyir."""

    @abstractmethod
    def search(self, collection: str, vector: list[float], top_k: int = 4) -> list[SearchHit]:
        """Ən oxşar nöqtələri qaytarır."""

    @abstractmethod
    def count(self, collection: str) -> int:
        """Kolleksiyadakı nöqtə sayı."""

    @abstractmethod
    def clear_collection(self, collection: str) -> None:
        """Kolleksiyanı tam boşaldır (bütün nöqtələri silir).
        Yeni sənəd köhnəsi ilə qarışmasın deyə bilik bazası sıfırlanarkən çağırılır."""


class InMemoryVectorStore(BaseVectorStore):
    """Sadə in-memory saxlama — mock rejim və testlər üçün."""

    name = "memory"

    def __init__(self) -> None:
        # {kolleksiya: {id: VectorPoint}}
        self._data: dict[str, dict[str, VectorPoint]] = {}

    def ensure_collection(self, collection: str, dim: int) -> None:
        self._data.setdefault(collection, {})

    def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        store = self._data.setdefault(collection, {})
        for p in points:
            store[p.id] = p

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        """İki vektor arasında kosinus oxşarlığı."""
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (na * nb)

    def search(self, collection: str, vector: list[float], top_k: int = 4) -> list[SearchHit]:
        points = self._data.get(collection, {}).values()
        scored = [
            SearchHit(id=p.id, score=self._cosine(vector, p.vector), payload=p.payload)
            for p in points
        ]
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]

    def count(self, collection: str) -> int:
        return len(self._data.get(collection, {}))

    def clear_collection(self, collection: str) -> None:
        self._data.pop(collection, None)


class QdrantVectorStore(BaseVectorStore):
    """Qdrant (lokal Docker və ya bulud) üzərində real vektor bazası."""

    name = "qdrant"

    def __init__(self, url: str, api_key: Optional[str] = None) -> None:
        from qdrant_client import QdrantClient

        self._client = QdrantClient(url=url, api_key=api_key or None, timeout=5)

    def ping(self) -> bool:
        """Qdrant-ın əlçatan olub-olmadığını yoxlayır (auto rejim üçün)."""
        try:
            self._client.get_collections()
            return True
        except Exception:  # noqa: BLE001
            return False

    def ensure_collection(self, collection: str, dim: int) -> None:
        from qdrant_client.http.models import Distance, VectorParams

        if not self._client.collection_exists(collection):
            self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        from qdrant_client.http.models import PointStruct

        self._client.upsert(
            collection_name=collection,
            points=[
                PointStruct(
                    # Qdrant UUID formatlı ID gözləyir — hex-i UUID-ə çeviririk
                    id=str(uuid.UUID(p.id)) if len(p.id) == 32 else p.id,
                    vector=p.vector,
                    payload=p.payload,
                )
                for p in points
            ],
        )

    def search(self, collection: str, vector: list[float], top_k: int = 4) -> list[SearchHit]:
        res = self._client.query_points(
            collection_name=collection, query=vector, limit=top_k, with_payload=True
        )
        return [
            SearchHit(id=str(p.id), score=float(p.score), payload=dict(p.payload or {}))
            for p in res.points
        ]

    def count(self, collection: str) -> int:
        return int(self._client.count(collection_name=collection).count)

    def clear_collection(self, collection: str) -> None:
        # Kolleksiyanı tamamilə silirik; növbəti ingest ensure_collection ilə
        # onu yenidən (düzgün ölçü/məsafə ilə) yaradır.
        if self._client.collection_exists(collection):
            self._client.delete_collection(collection_name=collection)


def create_vector_store(settings: Settings) -> BaseVectorStore:
    """VECTOR_BACKEND-ə görə saxlama qurur; auto rejimdə Qdrant-ı yoxlayır."""
    backend = settings.vector_backend.lower()

    if backend in ("qdrant", "auto"):
        try:
            store = QdrantVectorStore(settings.qdrant_url, settings.qdrant_api_key)
            if store.ping():
                logger.info("Qdrant qoşuldu: %s", settings.qdrant_url)
                return store
            if backend == "qdrant":
                logger.error("Qdrant əlçatan deyil: %s — in-memory istifadə olunur",
                             settings.qdrant_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Qdrant müştərisi qurulmadı (%s) — in-memory", exc)
        if backend == "auto":
            logger.info("Qdrant tapılmadı — in-memory vektor bazası işlədilir")

    return InMemoryVectorStore()
