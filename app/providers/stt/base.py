"""STT (speech-to-text) provayderlərinin baza interfeysi."""
from abc import ABC, abstractmethod
from typing import Optional

from app.models.core import TranscriptionResult


class BaseSTTProvider(ABC):
    """Audio baytlarını mətnə çevirən provayderlərin ortaq interfeysi."""

    name: str = "base"

    @abstractmethod
    def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "chunk.wav",
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """Audio parçasını (15-30 saniyə) transkripsiya edir."""
