"""TTS (mətn -> səs) provayderləri: mock | elevenlabs | openai.

İstəyə bağlı funksiya — iclas xülasəsini səsləndirmək üçün.
Kiçik modul olduğu üçün baza sinif, implementasiyalar və factory bir fayldadır.
"""
import io
import logging
import struct
import wave
from abc import ABC, abstractmethod

from app.config import Settings

logger = logging.getLogger(__name__)


class BaseTTSProvider(ABC):
    """Mətn -> audio bayt çevirən provayderlərin interfeysi."""

    name: str = "base"
    # Qaytarılan formata görə fayl uzantısı (mock wav, real provayderlər mp3 verir)
    extension: str = "mp3"

    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """Mətni səsə çevirir."""


class MockTTSProvider(BaseTTSProvider):
    """1 saniyəlik səssiz WAV qaytarır — pipeline-ı açarsız test etmək üçün."""

    name = "mock"
    extension = "wav"

    def synthesize(self, text: str) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            # 1 saniyə tam sükut — hər nümunə 0
            w.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))
        return buf.getvalue()


class ElevenLabsTTSProvider(BaseTTSProvider):
    """ElevenLabs TTS (free tier) — multilingual model Azərbaycan dilini dəstəkləyir."""

    name = "elevenlabs"
    extension = "mp3"

    def __init__(self, api_key: str, voice_id: str, model_id: str) -> None:
        self._api_key = api_key
        self._voice_id = voice_id
        self._model_id = model_id

    def synthesize(self, text: str) -> bytes:
        import httpx

        resp = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self._voice_id}",
            headers={"xi-api-key": self._api_key},
            json={"text": text, "model_id": self._model_id},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.content


class OpenAITTSProvider(BaseTTSProvider):
    """OpenAI TTS — ElevenLabs-ın əvəzləyicisi."""

    name = "openai"
    extension = "mp3"

    def __init__(self, api_key: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)

    def synthesize(self, text: str) -> bytes:
        resp = self._client.audio.speech.create(model="tts-1", voice="alloy", input=text)
        return resp.content


def create_tts_provider(settings: Settings) -> BaseTTSProvider:
    """TTS_PROVIDER dəyişəninə görə provayder qurur, açar yoxdursa mock."""
    choice = settings.tts_provider.lower()
    if choice == "elevenlabs" and settings.elevenlabs_api_key:
        return ElevenLabsTTSProvider(
            settings.elevenlabs_api_key,
            settings.elevenlabs_voice_id,
            settings.elevenlabs_tts_model,
        )
    if choice == "openai" and settings.openai_api_key:
        return OpenAITTSProvider(settings.openai_api_key)
    if choice != "mock":
        logger.warning("TTS üçün açar yoxdur — mock istifadə olunur")
    return MockTTSProvider()
