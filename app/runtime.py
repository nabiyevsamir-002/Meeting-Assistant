"""Mərkəzi runtime — bütün provayderlərin keşlənmiş singleton-ları.

Provayderlər bir dəfə qurulur və bütün tətbiq boyu paylaşılır.
Testlərdə reset_runtime() ilə sıfırlanır (fərqli env üçün).
"""
from functools import lru_cache

from app.config import get_settings
from app.providers.calendar import create_calendar_provider
from app.providers.calendar.base import BaseCalendarProvider
from app.providers.card import BaseCardProvider, create_card_provider
from app.providers.delivery import BaseDeliveryProvider, create_delivery_provider
from app.providers.embeddings import BaseEmbeddingProvider, create_embedding_provider
from app.providers.llm import BaseLLMProvider, create_llm_provider
from app.providers.stt import BaseSTTProvider, create_stt_provider
from app.providers.tts import BaseTTSProvider, create_tts_provider
from app.providers.vector import BaseVectorStore, create_vector_store


@lru_cache
def get_llm() -> BaseLLMProvider:
    """LLM provayderi (mock/claude/openai)."""
    return create_llm_provider(get_settings())


@lru_cache
def get_stt() -> BaseSTTProvider:
    """STT provayderi (mock/elevenlabs/whisper)."""
    return create_stt_provider(get_settings())


@lru_cache
def get_tts() -> BaseTTSProvider:
    """TTS provayderi (mock/elevenlabs/openai)."""
    return create_tts_provider(get_settings())


@lru_cache
def get_embedder() -> BaseEmbeddingProvider:
    """Embedding provayderi (mock/openai)."""
    return create_embedding_provider(get_settings())


@lru_cache
def get_vectors() -> BaseVectorStore:
    """Vektor bazası (qdrant/memory)."""
    return create_vector_store(get_settings())


@lru_cache
def get_calendar() -> BaseCalendarProvider:
    """Təqvim provayderi (mock/google)."""
    return create_calendar_provider(get_settings())


@lru_cache
def get_card() -> BaseCardProvider:
    """Kart provayderi (mock/hcti)."""
    return create_card_provider(get_settings())


@lru_cache
def get_delivery() -> BaseDeliveryProvider:
    """Çatdırılma provayderi (mock/n8n)."""
    return create_delivery_provider(get_settings())


def reset_runtime() -> None:
    """Bütün keşləri sıfırlayır — testlərdə env dəyişəndə çağırılır."""
    get_settings.cache_clear()
    for fn in (get_llm, get_stt, get_tts, get_embedder, get_vectors,
               get_calendar, get_card, get_delivery):
        fn.cache_clear()
    # İclas runtime reyestri də sıfırlanmalıdır (dövri importdan qaçmaq üçün burada)
    from app.services import meeting_service

    meeting_service.reset_registry()
