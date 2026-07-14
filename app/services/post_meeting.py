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

def _run_with_langgraph(state: PipelineState) -> PipelineState:
    """LangGraph StateGraph + MemorySaver checkpointer ilə icra."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, StateGraph

    graph = StateGraph(PipelineState)
    graph.add_node("assemble", node_assemble)
    graph.add_node("summarize", node_summarize)
    graph.add_node("actions", node_actions)
    graph.add_node("memorize", node_memorize)
    graph.add_node("card", node_card)
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
    for node in (node_assemble, node_summarize, node_actions,
                 node_memorize, node_card, node_deliver):
        state.update(node(state))
    return state


def run_post_meeting_pipeline(meeting: Meeting) -> MeetingReport:
    """İclas-sonrası tam pipeline: icra edir və hesabatı saxlayır."""
    state: PipelineState = {"meeting_id": meeting.id, "topic": meeting.topic}

    try:
        state = _run_with_langgraph(state)
    except ImportError:
        logger.warning("LangGraph tapılmadı — ardıcıl fallback işlədilir")
        state = _run_sequential(state)

    # Entity yaddaşından toplananları hesabata əlavə et
    from app.services.meeting_service import get_memory

    mem = get_memory(meeting.id)
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
    return report


def synthesize_summary_audio(meeting_id: str) -> Optional[str]:
    """Xülasəni TTS ilə səsləndirir (istəyə bağlı), fayl yolunu qaytarır."""
    report = repo.get_report(meeting_id)
    if not report:
        return None
    tts = get_tts()
    text = report.summary.get("overview", "") or report.summary.get("headline", "")
    audio = tts.synthesize(text)
    path = get_settings().data_path("tts", f"{meeting_id}.{tts.extension}")
    path.write_bytes(audio)
    return str(path)
