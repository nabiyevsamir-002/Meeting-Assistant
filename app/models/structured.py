"""LLM-dən structured output almaq üçün Pydantic sxemləri.

Bu sxemlər üç yolla doldurulur:
  - Claude:  Instructor (instructor.from_anthropic) və ya tool-use fallback
  - OpenAI:  Instructor (instructor.from_openai)
  - Mock:    prompt-dakı işarələnmiş bölmələrdən qaydalarla çıxarılır
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


# --- Sual aşkarlama (iclas zamanı) ---

class DetectedQuestion(BaseModel):
    """Transkript parçasında aşkarlanmış bir sual."""
    question: str = Field(..., description="Aşkarlanmış sualın mətni")
    directed_to_user: bool = Field(
        default=False, description="Sual birbaşa istifadəçiyə ünvanlanıb?"
    )
    urgency: Literal["aşağı", "normal", "yüksək"] = "normal"
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class DetectedQuestions(BaseModel):
    """Bir seqmentdəki bütün aşkarlanmış suallar."""
    questions: list[DetectedQuestion] = Field(default_factory=list)


# --- Cavab variantları ---

class AnswerOption(BaseModel):
    """İstifadəçiyə təklif olunan bir cavab variantı."""
    text: str = Field(..., description="Cavabın mətni")
    tone: Literal["qısa", "ətraflı", "diplomatik"] = "qısa"
    based_on_context: bool = Field(
        default=False, description="Bilik bazasındakı kontekstə əsaslanır?"
    )


class AnswerOptions(BaseModel):
    """Bir sual üçün 2-3 cavab variantı."""
    question: str
    options: list[AnswerOption] = Field(default_factory=list)


# --- İclas xülasəsi ---

class MeetingSummaryModel(BaseModel):
    """İclasın strukturlaşdırılmış yekun xülasəsi."""
    headline: str = Field(..., description="Bir cümləlik başlıq")
    overview: str = Field(..., description="2-4 cümləlik ümumi icmal")
    key_points: list[str] = Field(default_factory=list, description="Əsas məqamlar")
    decisions: list[str] = Field(default_factory=list, description="Qəbul edilmiş qərarlar")
    open_questions: list[str] = Field(default_factory=list, description="Açıq qalan suallar")


# --- Action item-lər ---

class ActionItem(BaseModel):
    """Bir konkret növbəti addım."""
    task: str = Field(..., description="Görüləcək iş")
    owner: Optional[str] = Field(default=None, description="Məsul şəxs")
    due: Optional[str] = Field(default=None, description="Son tarix (mətn şəklində)")
    priority: Literal["aşağı", "orta", "yüksək"] = "orta"


class ActionItems(BaseModel):
    """İclasın bütün action item-ləri."""
    items: list[ActionItem] = Field(default_factory=list)


# --- Entity yaddaşı ---

class Entity(BaseModel):
    """İclasda xatırlanan varlıq (şəxs, layihə, tarix və s.)."""
    name: str
    type: Literal["şəxs", "layihə", "tarix", "təşkilat", "digər"] = "digər"
    note: str = Field(default="", description="Bu varlıq haqqında qısa qeyd")


class EntityList(BaseModel):
    """Bir seqmentdən çıxarılmış varlıqlar."""
    entities: list[Entity] = Field(default_factory=list)


# --- Sürətli xülasə (iclas zamanı) ---

class QuickSummary(BaseModel):
    """Son bir neçə seqmentin qısa icmalı — söhbəti izləməyə kömək edir."""
    summary: str = Field(..., description="2-3 cümləlik cari vəziyyət icmalı")
    current_topic: str = Field(default="", description="Hazırda müzakirə olunan mövzu")
