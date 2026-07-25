"""Mock STT — açarsız test üçün ssenariləşdirilmiş iclas transkripti.

Hər çağırışda növbəti "iclas cümləsini" qaytarır. Ssenaridə həm adi
fikirlər, həm istifadəçiyə ünvanlanan suallar, həm də action item-lər var —
beləliklə bütün pipeline (sual aşkarlama, cavablar, xülasə, action-lar)
real açar olmadan nümayiş etdirilə bilər.
"""
import itertools
from typing import Optional

from app.models.core import TranscriptionResult
from app.providers.stt.base import BaseSTTProvider

# Ssenariləşdirilmiş iclas — dövri şəkildə təkrarlanır.
# {name} yeri konfiqurasiyadakı istifadəçi adı ilə doldurulur — beləliklə
# istənilən adla daxil olan istifadəçi "ona ünvanlanan sual" nümayişini görür.
_SCRIPT = [
    "Salam, hamıya xoş gəlmisiniz. Bu gün AI Meeting Assistant layihəsinin planını müzakirə edəcəyik.",
    "Birinci mərhələdə sənədlərin toplanması və bilik bazasının qurulması dayanır.",
    "{name}, sizcə inteqrasiya üçün hansı API-dən istifadə etməliyik?",
    "Layihənin deadline-ı nə vaxtdır və büdcə artıq təsdiqlənibmi?",
    "Yaxşı, onda növbəti addımları dəqiqləşdirək və məsuliyyətləri bölüşdürək.",
    "{name} texniki sənədləri cümə gününə qədər hazırlayacaq, Aynur isə test planını yazacaq.",
]


class MockSTTProvider(BaseSTTProvider):
    """Audio məzmunundan asılı olmayaraq ssenari üzrə mətn qaytarır."""

    name = "mock"

    def __init__(self, user_name: str = "Samir") -> None:
        self._default_name = user_name
        # itertools.cycle — ssenari bitəndə əvvəldən başlayır.
        # Xam saxlanır; ad transcribe zamanı qoyulur (iclasa bağlı ad dəyişə bilir).
        self._lines = itertools.cycle(_SCRIPT)

    def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "chunk.wav",
        language: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> TranscriptionResult:
        return TranscriptionResult(
            text=next(self._lines).format(name=user_name or self._default_name),
            language=language or "az",
            duration=20.0,  # təxmini chunk uzunluğu
            provider=self.name,
        )
