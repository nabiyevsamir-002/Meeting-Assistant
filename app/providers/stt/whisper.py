"""OpenAI Whisper STT provayderi — ElevenLabs-ın əvəzləyicisi.

STT_PROVIDER=whisper etməklə bütün transkripsiya OpenAI-a keçir.
"""
import io
from typing import Optional

from app.models.core import TranscriptionResult
from app.providers.stt.base import BaseSTTProvider


class WhisperSTTProvider(BaseSTTProvider):
    """OpenAI audio.transcriptions endpointi ilə transkripsiya."""

    name = "whisper"

    def __init__(self, api_key: str, model: str = "whisper-1") -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "chunk.wav",
        language: Optional[str] = None,
        user_name: Optional[str] = None,  # yalnız mock işlədir
    ) -> TranscriptionResult:
        # OpenAI SDK fayl obyekti gözləyir — adı ilə birlikdə veririk
        buf = io.BytesIO(audio)
        buf.name = filename
        kwargs: dict = {"model": self._model, "file": buf}
        if language:
            kwargs["language"] = language
        resp = self._client.audio.transcriptions.create(**kwargs)
        return TranscriptionResult(
            text=resp.text, language=language, duration=0.0, provider=self.name
        )
