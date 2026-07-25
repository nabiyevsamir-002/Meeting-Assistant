"""Əsas domen modelləri — iclas, seqment, feed hadisəsi, sənəd, hesabat.

Bu modellər API-nin giriş/çıxış sxemləri kimi də istifadə olunur.
"""
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id() -> str:
    """Unikal identifikator yaradır."""
    return uuid4().hex


def utcnow_iso() -> str:
    """UTC vaxtını ISO formatında qaytarır (SQLite üçün mətn kimi saxlanır)."""
    return datetime.now(timezone.utc).isoformat()


# --- İclas ---

MeetingStatus = Literal["scheduled", "created", "live", "ended"]


class MeetingCreate(BaseModel):
    """Yeni iclas yaratmaq üçün API sorğusu."""
    topic: str = Field(..., description="İclasın mövzusu")
    language: str = Field(default="az", description="İclasın dili")
    scheduled_at: Optional[str] = Field(default=None, description="Planlaşdırılmış vaxt (ISO)")
    user_name: Optional[str] = Field(
        default=None,
        description="Bu iclasda köməkçinin təmsil etdiyi şəxs — ona ünvanlanan suallar süzülür",
    )


class Meeting(BaseModel):
    """İclasın tam təsviri."""
    id: str = Field(default_factory=new_id)
    topic: str
    status: MeetingStatus = "created"
    language: str = "az"
    source: str = "manual"                      # manual
    user_name: Optional[str] = None             # boşdursa, settings.user_name işlədilir
    scheduled_at: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    created_at: str = Field(default_factory=utcnow_iso)


# --- Transkript seqmenti ---

class SegmentIn(BaseModel):
    """Mətn seqmentinin API ilə göndərilməsi (audio olmadan test üçün)."""
    text: str
    speaker: Optional[str] = None


class TranscriptSegment(BaseModel):
    """Transkriptin bir parçası (15-30 saniyəlik audio hissəsinə uyğun)."""
    id: str = Field(default_factory=new_id)
    meeting_id: str
    seq: int
    text: str
    speaker: Optional[str] = None
    duration: float = 0.0
    created_at: str = Field(default_factory=utcnow_iso)


# --- Canlı feed hadisəsi ---

FeedEventType = Literal["segment", "question", "answer_options", "answer", "quick_summary", "info"]


class FeedEvent(BaseModel):
    """İclas zamanı UI-a göndərilən canlı hadisə."""
    id: int = 0                                  # SQLite AUTOINCREMENT verir
    meeting_id: str
    type: FeedEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utcnow_iso)


# --- Bilik bazası sənədi ---

class IngestRequest(BaseModel):
    """n8n və ya istifadəçi tərəfindən göndərilən sənəd (scraping/OCR/PDF nəticəsi)."""
    title: str
    content: str = Field(..., description="Sənədin tam mətni")
    source_type: str = Field(default="text", description="web | pdf | ocr | text")
    url: Optional[str] = None
    meeting_topic: Optional[str] = Field(default=None, description="Hansı iclasa aiddir")


class IngestResult(BaseModel):
    """Ingest əməliyyatının nəticəsi."""
    doc_id: str
    title: str
    chunk_count: int
    backend: str                                # qdrant | memory


# --- STT nəticəsi ---

class TranscriptionResult(BaseModel):
    """STT provayderinin qaytardığı nəticə."""
    text: str
    language: Optional[str] = None
    duration: float = 0.0
    provider: str = "mock"


# --- Yekun hesabat ---

class MeetingReport(BaseModel):
    """İclasdan sonra yaradılan tam hesabat."""
    meeting_id: str
    topic: str
    transcript: str
    summary: dict[str, Any]
    action_items: list[dict[str, Any]]
    entities: list[dict[str, Any]] = Field(default_factory=list)
    card_url: Optional[str] = None
    delivered: bool = False
    delivery_info: Optional[str] = None
    created_at: str = Field(default_factory=utcnow_iso)
