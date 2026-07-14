"""Agentin alətləri — StructuredTool + Pydantic args_schema.

Hər alət bir iclasa bağlanır (meeting_id closure ilə ötürülür).
Alətlər tək sahəli sxemlərlə qurulub ki, klassik ReAct formatının
sətir tipli "Action Input"-u ilə problemsiz işləsin.
"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class SearchContextArgs(BaseModel):
    """search_context alətinin arqumentləri."""
    query: str = Field(..., description="Bilik bazasında axtarılacaq sorğu")


class RecentTranscriptArgs(BaseModel):
    """get_recent_transcript alətinin arqumentləri."""
    note: str = Field(default="", description="İstəyə bağlı qeyd (istifadə olunmur)")


class DetectQuestionArgs(BaseModel):
    """detect_question alətinin arqumentləri."""
    text: str = Field(..., description="Sual axtarılacaq mətn")


def build_tools(meeting_id: str) -> list[StructuredTool]:
    """Verilən iclas üçün alət dəstini qurur."""
    # Dövri importdan qaçmaq üçün funksiya daxilində import edirik
    from app.ingestion.service import search_context as ctx_search
    from app.runtime import get_llm
    from app.services.meeting_service import get_memory

    def search_context(query: str) -> str:
        """Bilik bazasında (yüklənmiş sənədlərdə) semantik axtarış aparır."""
        hits = ctx_search(query)
        if not hits:
            return "Bilik bazasında uyğun məlumat tapılmadı."
        # Nəticələri agentin oxuya biləcəyi yığcam formata salırıq
        return "\n".join(
            f"[{h['title']}] {h['text'][:250]}" for h in hits
        )

    def get_recent_transcript(note: str = "") -> str:
        """İclasın son transkript pəncərəsini qaytarır."""
        mem = get_memory(meeting_id)
        window = mem.recent_window() if mem else ""
        return window or "Hələ transkript yoxdur."

    def detect_question(text: str) -> str:
        """Verilmiş mətndə sualları aşkarlayır (LLM structured output ilə)."""
        from app.models.structured import DetectedQuestions
        from app.prompts import DETECT_QUESTIONS

        result = get_llm().generate_structured(
            DETECT_QUESTIONS.format(user_name="Samir", text=text),
            DetectedQuestions,
        )
        if not result.questions:
            return "Sual tapılmadı."
        return "\n".join(f"- {q.question}" for q in result.questions)

    return [
        StructuredTool.from_function(
            func=search_context,
            name="search_context",
            description=(
                "İclasdan əvvəl yüklənmiş sənədlərdə (bilik bazasında) axtarış aparır. "
                "Suala əsaslandırılmış cavab vermək üçün HƏMİŞƏ əvvəlcə bunu çağır."
            ),
            args_schema=SearchContextArgs,
        ),
        StructuredTool.from_function(
            func=get_recent_transcript,
            name="get_recent_transcript",
            description="İclasın son dəqiqələrinin transkriptini qaytarır.",
            args_schema=RecentTranscriptArgs,
        ),
        StructuredTool.from_function(
            func=detect_question,
            name="detect_question",
            description="Mətn parçasında verilmiş sualları aşkarlayır.",
            args_schema=DetectQuestionArgs,
        ),
    ]
