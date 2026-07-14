"""Canlı iclas pipeline-ı (Phase 2).

Hər gələn seqment (audio -> STT -> mətn, və ya birbaşa mətn) üçün:
  1. Seqment SQLite-a və qısamüddətli yaddaşa yazılır
  2. LLM structured output ilə suallar aşkarlanır
  3. Hər sual üçün ReAct agent bilik bazasında axtarıb cavab qaralaması qurur
  4. Qaralama 2-3 tonlu cavab variantına strukturlaşdırılır
  5. Hər N seqmentdən bir sürətli xülasə feed-ə düşür

Bütün nəticələr feed_events cədvəlinə yazılır — UI polling ilə oxuyur.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.config import get_settings
from app.memory.short_term import MeetingMemory
from app.models.core import (
    Meeting,
    SegmentIn,
    TranscriptSegment,
    utcnow_iso,
)
from app.models.structured import AnswerOptions, DetectedQuestions, QuickSummary
from app.prompts import DETECT_QUESTIONS, QUICK_SUMMARY, STRUCTURE_ANSWERS
from app.runtime import get_llm, get_stt
from app.storage import repo

logger = logging.getLogger(__name__)


@dataclass
class MeetingRuntime:
    """Canlı iclasın in-process vəziyyəti (yaddaş + agent)."""
    memory: MeetingMemory
    agent_executor: object = None  # tənbəl qurulur (lazy)
    segment_count: int = field(default=0)


# Canlı iclasların reyestri: meeting_id -> MeetingRuntime
_registry: dict[str, MeetingRuntime] = {}


def reset_registry() -> None:
    """Testlər üçün reyestri sıfırlayır."""
    _registry.clear()


def get_memory(meeting_id: str) -> Optional[MeetingMemory]:
    """Agentin alətləri iclasın yaddaşına buradan çıxış edir."""
    rt = _registry.get(meeting_id)
    return rt.memory if rt else None


def _get_runtime(meeting_id: str) -> MeetingRuntime:
    """İclasın runtime-ını qaytarır, yoxdursa yaradır."""
    if meeting_id not in _registry:
        _registry[meeting_id] = MeetingRuntime(memory=MeetingMemory(get_llm()))
    return _registry[meeting_id]


def start_meeting(meeting: Meeting) -> Meeting:
    """İclası canlı statusa keçirir və runtime hazırlayır."""
    meeting.status = "live"
    meeting.started_at = utcnow_iso()
    repo.save_meeting(meeting)
    _get_runtime(meeting.id)
    repo.add_feed_event(meeting.id, "info", {"message": "İclas başladı"})
    return meeting


def process_audio_chunk(meeting: Meeting, audio: bytes, filename: str) -> TranscriptSegment:
    """Audio parçasını STT ilə mətnə çevirib pipeline-a ötürür."""
    stt = get_stt()
    result = stt.transcribe(audio, filename=filename, language=meeting.language)
    logger.info("STT (%s): %s", result.provider, result.text[:80])
    return process_text_segment(meeting, SegmentIn(text=result.text))


def process_text_segment(meeting: Meeting, seg_in: SegmentIn) -> TranscriptSegment:
    """Bir transkript seqmentini tam pipeline-dan keçirir."""
    settings = get_settings()
    llm = get_llm()
    rt = _get_runtime(meeting.id)

    # 1) Seqmenti saxla və yaddaşa əlavə et
    seq = repo.next_segment_seq(meeting.id)
    segment = TranscriptSegment(
        meeting_id=meeting.id, seq=seq, text=seg_in.text, speaker=seg_in.speaker
    )
    repo.save_segment(segment)
    rt.memory.add_segment(seg_in.text, seg_in.speaker)
    rt.segment_count += 1
    repo.add_feed_event(meeting.id, "segment",
                        {"seq": seq, "text": seg_in.text, "speaker": seg_in.speaker})

    # 2) Sual aşkarlama (structured output)
    try:
        detected = llm.generate_structured(
            DETECT_QUESTIONS.format(user_name="Samir", text=seg_in.text),
            DetectedQuestions,
        )
    except Exception as exc:  # noqa: BLE001 — aşkarlama xətası axını dayandırmasın
        logger.warning("Sual aşkarlama alınmadı: %s", exc)
        detected = DetectedQuestions()

    for q in detected.questions:
        repo.add_feed_event(meeting.id, "question", q.model_dump())
        # 3-4) Hər sual üçün cavab variantları hazırla
        _answer_question(meeting, rt, q.question)

    # 5) Hər N seqmentdən bir sürətli xülasə
    if rt.segment_count % settings.quick_summary_every == 0:
        _quick_summary(meeting, rt)

    return segment


def _answer_question(meeting: Meeting, rt: MeetingRuntime, question: str) -> None:
    """ReAct agent ilə cavab qaralaması qurub variantlara strukturlaşdırır."""
    llm = get_llm()
    draft = ""
    steps_info: list[dict] = []
    context_used = ""

    # ReAct agent — LangChain mövcud deyilsə sadə fallback işləyir
    try:
        if rt.agent_executor is None:
            from app.agent.react_agent import build_agent_executor

            rt.agent_executor = build_agent_executor(meeting.id, llm)
        result = rt.agent_executor.invoke({"input": question})
        draft = result.get("output", "")
        # Ara addımları (alət çağırışlarını) feed üçün yığırıq
        for action, observation in result.get("intermediate_steps", []):
            steps_info.append({
                "tool": getattr(action, "tool", ""),
                "input": str(getattr(action, "tool_input", ""))[:120],
                "observation": str(observation)[:200],
            })
            context_used = str(observation)[:500]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Agent işləmədi (%s) — birbaşa LLM fallback", exc)
        from app.ingestion.service import search_context

        hits = search_context(question)
        context_used = "\n".join(h["text"][:200] for h in hits)
        draft = llm.complete(
            f"Sual: {question}\nKontekst: {context_used}\nQısa cavab qaralaması yaz."
        )

    # Qaralamanı 2-3 tonlu cavab variantına çevir (structured output)
    try:
        options = get_llm().generate_structured(
            STRUCTURE_ANSWERS.format(
                question=question, context=context_used or "kontekst tapılmadı", draft=draft
            ),
            AnswerOptions,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cavab strukturlaşdırma alınmadı: %s", exc)
        return

    payload = options.model_dump()
    payload["agent_steps"] = steps_info  # şəffaflıq: agent hansı alətləri çağırdı
    repo.add_feed_event(meeting.id, "answer_options", payload)


def _quick_summary(meeting: Meeting, rt: MeetingRuntime) -> None:
    """Sürətli xülasə — diqqəti itirən istifadəçini kontekstə qaytarır."""
    llm = get_llm()
    # Əvvəlcə LangChain Summary memory ilə ümumi xülasəni yenilə
    running = rt.memory.update_summary()
    try:
        qs = llm.generate_structured(
            QUICK_SUMMARY.format(window=rt.memory.recent_window(),
                                 running_summary=running),
            QuickSummary,
        )
        repo.add_feed_event(meeting.id, "quick_summary", qs.model_dump())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sürətli xülasə alınmadı: %s", exc)


def end_meeting(meeting: Meeting) -> Meeting:
    """İclası bitirir və iclas-sonrası pipeline-ı işə salır."""
    meeting.status = "ended"
    meeting.ended_at = utcnow_iso()
    repo.save_meeting(meeting)
    repo.add_feed_event(meeting.id, "info", {"message": "İclas bitdi, hesabat hazırlanır"})

    # Phase 3: transkript, xülasə, action-lar, kart, çatdırılma
    from app.services.post_meeting import run_post_meeting_pipeline

    run_post_meeting_pipeline(meeting)
    return meeting
