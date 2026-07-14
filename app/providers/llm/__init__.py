"""LLM provayder factory-si.

Seçim qaydası:
  LLM_PROVIDER=claude  + ANTHROPIC_API_KEY varsa  -> Claude
  LLM_PROVIDER=openai  + OPENAI_API_KEY varsa     -> OpenAI
  əks halda                                        -> Mock (xəbərdarlıqla)
"""
import logging

from app.config import Settings
from app.providers.llm.base import BaseLLMProvider
from app.providers.llm.mock import MockLLMProvider

logger = logging.getLogger(__name__)


def create_llm_provider(settings: Settings) -> BaseLLMProvider:
    """Konfiqurasiyaya əsasən LLM provayderini qurur, açar yoxdursa mock-a düşür."""
    choice = settings.llm_provider.lower()

    if choice == "claude":
        if settings.anthropic_api_key:
            from app.providers.llm.claude import ClaudeLLMProvider

            return ClaudeLLMProvider(settings.anthropic_api_key, settings.anthropic_model)
        logger.warning("ANTHROPIC_API_KEY boşdur — LLM mock rejimə keçdi")

    elif choice == "openai":
        if settings.openai_api_key:
            from app.providers.llm.openai_llm import OpenAILLMProvider

            return OpenAILLMProvider(settings.openai_api_key, settings.openai_model)
        logger.warning("OPENAI_API_KEY boşdur — LLM mock rejimə keçdi")

    elif choice != "mock":
        logger.warning("Naməlum LLM_PROVIDER=%s — mock istifadə olunur", choice)

    return MockLLMProvider()
