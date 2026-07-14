"""ElevenLabs Scribe STT provayderi (FREE tier).

REST API birbaşa httpx ilə çağırılır — SDK asılılığı yoxdur.
Pulsuz planda aylıq limit var, ona görə audio 15-30 saniyəlik
parçalarla göndərilir və yalnız lazım olanda istifadə olunur.
"""
from typing import Optional

import httpx

from app.models.core import TranscriptionResult
from app.providers.stt.base import BaseSTTProvider

_API_URL = "https://api.elevenlabs.io/v1/speech-to-text"


class ElevenLabsSTTProvider(BaseSTTProvider):
    """ElevenLabs Scribe (scribe_v1) modeli ilə transkripsiya."""

    name = "elevenlabs"

    def __init__(self, api_key: str, model_id: str = "scribe_v1") -> None:
        self._api_key = api_key
        self._model_id = model_id

    def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "chunk.wav",
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        data: dict = {"model_id": self._model_id}
        if language:
            # ISO kod veriləndə dil aşkarlamaya vaxt sərf olunmur
            data["language_code"] = language
        resp = httpx.post(
            _API_URL,
            headers={"xi-api-key": self._api_key},
            data=data,
            files={"file": (filename, audio)},
            timeout=120,
        )
        resp.raise_for_status()
        payload = resp.json()
        return TranscriptionResult(
            text=payload.get("text", ""),
            language=payload.get("language_code", language),
            duration=0.0,
            provider=self.name,
        )
