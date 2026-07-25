"""İclasdan sonrakı pipeline (Phase 3) — LangGraph StateGraph ilə.

Axın:  transkript -> xülasə -> action item-lər -> epizodik/uzunmüddətli
       yaddaş -> vizual kart -> çatdırılma -> hesabat

LangGraph MemorySaver checkpointer ilə qurulub — hər addımın vəziyyəti
thread_id=meeting_id üzrə yadda saxlanılır. LangGraph mövcud olmasa
eyni addımlar sadə ardıcıllıqla icra olunur (fallback).
"""
import logging
from datetime import date
from typing import Any, Optional, TypedDict

from app.config import get_settings
from app.models.core import Meeting, MeetingReport
from app.models.structured import ActionItems, MeetingSummaryModel
from app.prompts import EXTRACT_ACTIONS, FINAL_SUMMARY
from app.providers.card import CARD_TEMPLATE
from app.runtime import get_card, get_delivery, get_llm, get_tts
from app.storage import repo

logger = logging.getLogger(__name__)


class PipelineState(TypedDict, total=False):
    """LangGraph qovşaqları arasında ötürülən vəziyyət."""
    meeting_id: str
    topic: str
    transcript: str
    summary: dict[str, Any]
    action_items: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    card_url: Optional[str]
    delivered: bool
    delivery_info: Optional[str]


# --- Pipeline qovşaqları (hər biri vəziyyəti alır, yenilənmiş hissəni qaytarır) ---

def node_assemble(state: PipelineState) -> PipelineState:
    """Bütün seqmentləri tam transkriptə yığır."""
    segments = repo.list_segments(state["meeting_id"])
    lines = [
        f"[{s.speaker}] {s.text}" if s.speaker else s.text
        for s in segments
    ]
    return {"transcript": "\n".join(lines) or "(transkript boşdur)"}


def node_summarize(state: PipelineState) -> PipelineState:
    """Tam transkriptdən strukturlaşdırılmış yekun xülasə çıxarır."""
    summary = get_llm().generate_structured(
        FINAL_SUMMARY.format(topic=state["topic"], transcript=state["transcript"]),
        MeetingSummaryModel,
    )
    return {"summary": summary.model_dump()}


def node_actions(state: PipelineState) -> PipelineState:
    """Action item-ləri structured output ilə çıxarır."""
    actions = get_llm().generate_structured(
        EXTRACT_ACTIONS.format(transcript=state["transcript"]),
        ActionItems,
    )
    return {"action_items": [a.model_dump() for a in actions.items]}


def node_memorize(state: PipelineState) -> PipelineState:
    """Epizodik (Qdrant) və uzunmüddətli (mem0/mock) yaddaşa yazır."""
    from app.memory.episodic import store_episode
    from app.memory.long_term import create_long_term_memory

    summary = state.get("summary", {})
    actions_text = "; ".join(a["task"] for a in state.get("action_items", []))
    today = date.today().isoformat()

    store_episode(
        state["meeting_id"], state["topic"],
        summary.get("overview", ""), actions_text, today,
    )
    ltm = create_long_term_memory(get_settings())
    ltm.add(
        f"{today} tarixli «{state['topic']}» iclası: {summary.get('overview', '')} "
        f"Növbəti addımlar: {actions_text}",
        meeting_id=state["meeting_id"],
        meta={"topic": state["topic"], "date": today},
    )
    return {}


def node_card(state: PipelineState) -> PipelineState:
    """HTML şablonundan vizual xülasə kartı yaradır."""
    summary = state.get("summary", {})
    html = CARD_TEMPLATE.format(
        headline=summary.get("headline", state["topic"]),
        topic=state["topic"],
        date=date.today().isoformat(),
        overview=summary.get("overview", ""),
        key_points="".join(f"<li>{p}</li>" for p in summary.get("key_points", [])),
        actions="".join(
            f"<li>{a['task']}" + (f" — <b>{a['owner']}</b>" if a.get("owner") else "") + "</li>"
            for a in state.get("action_items", [])
        ),
    )
    url = get_card().render(html, state["meeting_id"])
    return {"card_url": url}


def node_deliver(state: PipelineState) -> PipelineState:
    """Hesabatı n8n webhook-una (email/Telegram) və ya mock outbox-a göndərir."""
    payload = {
        "meeting_id": state["meeting_id"],
        "topic": state["topic"],
        "summary": state.get("summary", {}),
        "action_items": state.get("action_items", []),
        "card_url": state.get("card_url"),
    }
    try:
        info = get_delivery().deliver(payload)
        return {"delivered": True, "delivery_info": info}
    except Exception as exc:  # noqa: BLE001 — çatdırılma xətası hesabatı ləğv etməsin
        logger.warning("Çatdırılma alınmadı: %s", exc)
        return {"delivered": False, "delivery_info": str(exc)}


# --- Pipeline-ın qurulması və icrası ---

def _set_stage(meeting_id: Optional[str], stage: str, **fields) -> None:
    """Frontend stepper-i üçün pipeline mərhələsini yazır (xəta-təhlükəsiz)."""
    if not meeting_id:
        return
    try:
        from app.services import pipeline_status
        pipeline_status.set(meeting_id, stage=stage, **fields)
    except Exception:  # noqa: BLE001 — status yazısı pipeline-ı pozmasın
        pass


def _staged(fn, stage: str):
    """Qovşağı icra edir və bitəndən sonra mərhələni status-a yazır."""
    def wrapped(state: PipelineState) -> PipelineState:
        result = fn(state)
        _set_stage(state.get("meeting_id"), stage)
        return result
    wrapped.__name__ = getattr(fn, "__name__", "node")
    return wrapped


def _run_with_langgraph(state: PipelineState) -> PipelineState:
    """LangGraph StateGraph + MemorySaver checkpointer ilə icra."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, StateGraph

    graph = StateGraph(PipelineState)
    # Hər qovşaq bitəndə mərhələ status-a yazılır (deliver → yekun "done" tutur)
    graph.add_node("assemble", _staged(node_assemble, "assembled"))
    graph.add_node("summarize", _staged(node_summarize, "summarized"))
    graph.add_node("actions", _staged(node_actions, "actions"))
    graph.add_node("memorize", _staged(node_memorize, "memorized"))
    graph.add_node("card", _staged(node_card, "card"))
    graph.add_node("deliver", node_deliver)

    # Xətti axın: hər qovşaq növbətiyə keçir
    graph.set_entry_point("assemble")
    graph.add_edge("assemble", "summarize")
    graph.add_edge("summarize", "actions")
    graph.add_edge("actions", "memorize")
    graph.add_edge("memorize", "card")
    graph.add_edge("card", "deliver")
    graph.add_edge("deliver", END)

    # MemorySaver — hər addımın vəziyyətini thread_id üzrə saxlayır
    app_graph = graph.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": state["meeting_id"]}}
    return app_graph.invoke(state, config)


def _run_sequential(state: PipelineState) -> PipelineState:
    """LangGraph olmayanda eyni qovşaqlar sadə ardıcıllıqla işləyir."""
    for node in (_staged(node_assemble, "assembled"), _staged(node_summarize, "summarized"),
                 _staged(node_actions, "actions"), _staged(node_memorize, "memorized"),
                 _staged(node_card, "card"), node_deliver):
        state.update(node(state))
    return state


def run_post_meeting_pipeline(meeting: Meeting) -> MeetingReport:
    """İclas-sonrası tam pipeline: icra edir və hesabatı saxlayır."""
    state: PipelineState = {"meeting_id": meeting.id, "topic": meeting.topic}

    try:
        try:
            state = _run_with_langgraph(state)
        except ImportError:
            logger.warning("LangGraph tapılmadı — ardıcıl fallback işlədilir")
            state = _run_sequential(state)

        # Entity yaddaşından toplananları hesabata əlavə et
        from app.services.meeting_service import get_memory

        mem = get_memory(meeting.id)
        if mem:
            # Canlı axında təxirə salınmış varlıq çıxarılmasını indi toplu emal edirik
            mem.entities.flush()
        entities = mem.entities.as_dicts() if mem else []

        report = MeetingReport(
            meeting_id=meeting.id,
            topic=meeting.topic,
            transcript=state.get("transcript", ""),
            summary=state.get("summary", {}),
            action_items=state.get("action_items", []),
            entities=entities,
            card_url=state.get("card_url"),
            delivered=state.get("delivered", False),
            delivery_info=state.get("delivery_info"),
        )
        repo.save_report(report)
        repo.add_feed_event(meeting.id, "info", {"message": "Hesabat hazırdır",
                                                 "card_url": report.card_url})
        logger.info("Hesabat hazırlandı: %s", meeting.id)
        _set_stage(meeting.id, "done", delivered=bool(report.delivered))
        return report
    except Exception:
        # Mərhələni itirməmək üçün stage-i saxlayırıq, yalnız error bayrağı qoyuruq
        try:
            from app.services import pipeline_status
            pipeline_status.set(meeting.id, error=True, done=True)
        except Exception:  # noqa: BLE001
            pass
        raise


def synthesize_summary_audio(meeting_id: str) -> Optional[str]:
    """Xülasəni TTS ilə səsləndirir (istəyə bağlı), fayl yolunu qaytarır."""
    report = repo.get_report(meeting_id)
    if not report:
        return None
    tts = get_tts()
    path = get_settings().data_path("tts", f"{meeting_id}.{tts.extension}")
    # Keş: eyni hesabat üçün təkrar sintez etmirik (API xərcinə qənaət)
    if path.exists():
        return str(path)
    text = report.summary.get("overview", "") or report.summary.get("headline", "")
    audio = tts.synthesize(text)
    path.write_bytes(audio)
    return str(path)
