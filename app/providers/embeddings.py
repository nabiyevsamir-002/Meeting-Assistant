"""Embedding provayderləri: mock | openai.

Qeyd: Claude API embedding vermir, ona görə real embedding üçün OpenAI
istifadə olunur. Mock isə mətnin hash-indən DETERMİNİSTİK vektor yaradır —
eyni mətn həmişə eyni vektoru alır, oxşar sözlü mətnlər isə (söz səviyyəli
hash cəmi sayəsində) bir-birinə yaxın düşür. Bu, açarsız da vektor
axtarışının mənalı işləməsinə imkan verir.
"""
import hashlib
import logging
import math
import random
import re
from abc import ABC, abstractmethod

from app.config import Settings

logger = logging.getLogger(__name__)


class BaseEmbeddingProvider(ABC):
    """Mətn -> vektor çevirən provayderlərin interfeysi."""

    name: str = "base"
    dim: int = 256

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Mətnlər siyahısını vektorlar siyahısına çevirir."""

    def embed_one(self, text: str) -> list[float]:
        """Tək mətn üçün rahatlıq metodu."""
        return self.embed([text])[0]


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Söz-səviyyəli deterministik hash vektorları."""

    name = "mock"

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _word_vector(self, word: str) -> list[float]:
        """Hər söz üçün hash-dən törədilmiş sabit vektor."""
        seed = int.from_bytes(hashlib.sha256(word.encode()).digest()[:8], "big")
        rnd = random.Random(seed)
        return [rnd.uniform(-1.0, 1.0) for _ in range(self.dim)]

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            words = re.findall(r"\w+", text.lower())
            vec = [0.0] * self.dim
            # Sözlərin vektorlarının cəmi — ortaq sözlü mətnlər yaxın olur
            for w in words or ["boş"]:
                wv = self._word_vector(w)
                for i in range(self.dim):
                    vec[i] += wv[i]
            # Normalizasiya — kosinus oxşarlığı üçün vacibdir
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            result.append([v / norm for v in vec])
        return result


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI text-embedding-3-small — dimensions parametri ilə ölçü sabitlənir."""

    name = "openai"

    def __init__(self, api_key: str, model: str, dim: int) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        # dimensions parametri mock ilə eyni ölçünü təmin edir —
        # provayder dəyişəndə Qdrant kolleksiyası uyğunsuz qalmır
        resp = self._client.embeddings.create(
            model=self._model, input=texts, dimensions=self.dim
        )
        return [d.embedding for d in resp.data]


def create_embedding_provider(settings: Settings) -> BaseEmbeddingProvider:
    """EMBEDDING_PROVIDER dəyişəninə görə provayder qurur."""
    if settings.embedding_provider.lower() == "openai":
        if settings.openai_api_key:
            return OpenAIEmbeddingProvider(
                settings.openai_api_key,
                settings.openai_embedding_model,
                settings.embedding_dim,
            )
        logger.warning("OPENAI_API_KEY boşdur — embedding mock rejimə keçdi")
    return MockEmbeddingProvider(settings.embedding_dim)
