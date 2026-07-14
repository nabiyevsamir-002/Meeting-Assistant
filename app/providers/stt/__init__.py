"""STT provayder factory-si — açar yoxdursa mock-a düşür."""
import logging

from app.config import Settings
from app.providers.stt.base import BaseSTTProvider
from app.providers.stt.mock import MockSTTProvider

logger = logging.getLogger(__name__)


def create_stt_provider(settings: Settings) -> BaseSTTProvider:
    """STT_PROVIDER dəyişəninə görə provayder qurur."""
    choice = settings.stt_provider.lower()

    if choice == "elevenlabs":
        if settings.elevenlabs_api_key:
            from app.providers.stt.elevenlabs import ElevenLabsSTTProvider

            return ElevenLabsSTTProvider(
                settings.elevenlabs_api_key, settings.elevenlabs_stt_model
            )
        logger.warning("ELEVENLABS_API_KEY boşdur — STT mock rejimə keçdi")

    elif choice == "whisper":
        if settings.openai_api_key:
            from app.providers.stt.whisper import WhisperSTTProvider

            return WhisperSTTProvider(settings.openai_api_key, settings.whisper_model)
        logger.warning("OPENAI_API_KEY boşdur — STT mock rejimə keçdi")

    elif choice != "mock":
        logger.warning("Naməlum STT_PROVIDER=%s — mock istifadə olunur", choice)

    return MockSTTProvider()
