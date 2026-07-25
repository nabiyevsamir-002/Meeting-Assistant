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
import threading
import time
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
from app.prompts import ANSWER_STREAM, DETECT_QUESTIONS, QUICK_SUMMARY, STRUCTURE_ANSWERS
from app.runtime import get_llm, get_stt
from app.storage import repo
from app.text_fixes import correct_transcript, has_question_signal

logger = logging.getLogger(__name__)


@dataclass
class MeetingRuntime:
    """Canlı iclasın in-process vəziyyəti (yaddaş + agent)."""
    memory: MeetingMemory
    agent_executor: object = None  # tənbəl qurulur (lazy)
    segment_count: int = field(default=0)
    # Arxa plan təhlilini iclas daxilində ardıcıl saxlayan kilid —
    # LangChain yaddaşı thread-safe deyil, paralel emala icazə vermirik
    lock: threading.Lock = field(default_factory=threading.Lock)
    ended: bool = field(default=False)  # iclas bitibsə, gecikən arxa plan işi atlanır
    # C: son cavablanmış suallar (normallaşdırılmış mətn -> monotonic vaxt) —
    # üst-üstə düşən chunk-larda yaranan dublikat sualların qarşısını alır
    answered: dict[str, float] = field(default_factory=dict)


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
    """Audio parçasını STT ilə mətnə çevirir; AI təhlilini arxa plana ötürür.

    SÜRƏT: agent yalnız STT qədər gözləyir — sual aşkarlama/cavab kimi LLM
    mərhələləri ayrıca thread-də (iclas kilidi ilə ardıcıl) icra olunur.
    Beləliklə növbəti audio parçası AI-nin arxasında növbəyə düşmür.
    """
    stt = get_stt()
    result = stt.transcribe(
        audio, filename=filename, language=meeting.language,
        user_name=meeting.user_name or get_settings().user_name,  # mock ssenarisi üçün
    )
    logger.info("STT (%s): %s", result.provider, result.text[:80])
    # Sükut/boş nəticə — pipeline işə salınmır, boş seqment də saxlanmır
    if not result.text.strip():
        return TranscriptSegment(meeting_id=meeting.id, seq=0, text="")

    def _bg() -> None:
        # İclas hələ də canlıdırmı? (server yenidən başlayıbsa reyestr boş ola bilər,
        # amma iclas bazada canlı qalır — bu halda emal DAVAM etməlidir)
        fresh = repo.get_meeting(meeting.id)
        if not fresh or fresh.status != "live":
            return  # iclas bitib və ya silinib — emal etmirik
        rt = _get_runtime(meeting.id)  # yoxdursa yaradır → restartdan sonra da işləyir
        with rt.lock:
            if rt.ended:  # kilidi gözləyərkən iclas bitibsə emal etmirik
                return
            try:
                process_text_segment(fresh, SegmentIn(text=result.text))
            except Exception:  # noqa: BLE001 — arxa plan xətası serveri yıxmasın
                logger.exception("Arxa plan seqment emalı alınmadı")

    threading.Thread(target=_bg, daemon=True).start()
    return TranscriptSegment(meeting_id=meeting.id, seq=0, text=result.text)


def process_text_segment(meeting: Meeting, seg_in: SegmentIn) -> TranscriptSegment:
    """Bir transkript seqmentini tam pipeline-dan keçirir."""
    settings = get_settings()
    llm = get_llm()
    rt = _get_runtime(meeting.id)
    # Ad iclasa bağlıdır: kim daxil olubsa, suallar ONA görə süzülür
    user_name = meeting.user_name or settings.user_name

    # E: STT texniki-termin düzəlişi (məs. "epi"→"API") — mətni emaldan
    # əvvəl təmizləyirik ki, həm sual aşkarlama, həm cavab dəqiq olsun
    text = correct_transcript(seg_in.text)

    # 1) Seqmenti saxla və yaddaşa əlavə et
    seq = repo.next_segment_seq(meeting.id)
    segment = TranscriptSegment(
        meeting_id=meeting.id, seq=seq, text=text, speaker=seg_in.speaker
    )
    repo.save_segment(segment)
    rt.memory.add_segment(text, seg_in.speaker)
    rt.segment_count += 1
    repo.add_feed_event(meeting.id, "segment",
                        {"seq": seq, "text": text, "speaker": seg_in.speaker})

    # 2) Sual aşkarlama (structured output).
    # A: LLM-dən ƏVVƏL lokal ön-filtr — sual əlaməti ("?", sual sözü, ad)
    # yoxdursa LLM çağırışını TAM atlayırıq (seqmentlərin çoxu adi cümlədir).
    detected = DetectedQuestions()
    if not settings.local_prefilter or has_question_signal(text, user_name):
        try:
            detected = llm.generate_structured(
                DETECT_QUESTIONS.format(user_name=user_name, text=text),
                DetectedQuestions,
            )
        except Exception as exc:  # noqa: BLE001 — aşkarlama xətası axını dayandırmasın
            logger.warning("Sual aşkarlama alınmadı: %s", exc)
            detected = DetectedQuestions()

    # C: yaxınlarda cavablanmış eyni sualı təkrar emal etmirik (dublikatsız).
    # answer_only_directed=True olduqda yalnız ünvanlı suallara cavab hazırlanır.
    now = time.monotonic()
    window = settings.answer_dedup_seconds
    to_answer: list[str] = []
    for q in detected.questions:
        norm = _normalize_q(q.question)
        last = rt.answered.get(norm)
        if last is not None and (now - last) < window:
            continue  # C: son N saniyədə eyni sual — nə emit, nə cavab
        rt.answered[norm] = now
        repo.add_feed_event(meeting.id, "question", q.model_dump())
        if not settings.answer_only_directed or _is_directed(q, user_name):
            to_answer.append(q.question)

    # 3-4) Cavabları hazırla. Bir seqmentdə birdən çox sual olsa, PARALEL
    # (sürətli rejimdə çağırışlar stateless-dir; agent rejimində ardıcıl saxlayırıq)
    if len(to_answer) > 1 and settings.live_fast_answers:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=min(3, len(to_answer))) as ex:
            list(ex.map(lambda qq: _answer_question(meeting, rt, qq), to_answer))
    else:
        for qq in to_answer:
            _answer_question(meeting, rt, qq)

    # 5) Hər N seqmentdən bir sürətli xülasə
    if rt.segment_count % settings.quick_summary_every == 0:
        _quick_summary(meeting, rt)

    return segment


def _normalize_q(question: str) -> str:
    """Sualı dedup üçün normallaşdırır (kiçik hərf, yalnız söz simvolları)."""
    import re

    return re.sub(r"\W+", " ", question.lower()).strip()


def _is_directed(q, user_name: str) -> bool:
    """Sual istifadəçiyə ünvanlanıb? (LLM bayrağı VƏ YA adın mətndə keçməsi).
    Panel filtri ilə eyni məntiq — beləliklə cavabladığımız sual paneldə görünür."""
    if getattr(q, "directed_to_user", False):
        return True
    name = (user_name or "").strip().lower()
    return len(name) > 1 and name in q.question.lower()


def _answer_question(meeting: Meeting, rt: MeetingRuntime, question: str) -> None:
    """Suala 2-3 tonlu cavab variantı hazırlayır.

    SÜRƏTLİ rejim (default): kontekst axtarışı + TƏK strukturlaşdırma çağırışı.
    Tam rejim: çox addımlı ReAct agent (kurs nümayişi üçün, LIVE_FAST_ANSWERS=false).
    """
    settings = get_settings()
    llm = get_llm()
    draft = ""
    steps_info: list[dict] = []
    context_used = ""

    if settings.live_fast_answers:
        # J: öncədən hazırlanmış Q&A keşi — yüksək oxşarlıqda hazır cavabı
        # DƏRHAL veririk (0 LLM çağırışı). Uyğunluq zəifsə adi RAG yoluna düşürük.
        if settings.prepared_qa_enabled:
            from app.services import prepared_qa

            prep = prepared_qa.match(question)
            if prep is not None:
                repo.add_feed_event(meeting.id, "answer", {
                    "question": question, "text": prep.answer, "done": True,
                    "based_on_context": True, "prepared": True,
                    "source": "öncədən hazırlanmış cavab",
                })
                return

        # SÜRƏTLİ: 1 axtarış + axan (streaming) TƏK cavab (3 variant/Instructor yoxdur)
        from app.ingestion.service import search_context

        hits = search_context(question)
        context_used = "\n".join(h["text"][:200] for h in hits)
        # D: cavabın hansı sənədə əsaslandığını göstərmək üçün ən yaxın mənbə
        source = hits[0].get("title") if hits else None
        _stream_answer(meeting, question, context_used, source=source)
        return
    else:
        # Tam ReAct agent yolu — LangChain mövcud deyilsə sadə fallback işləyir
        try:
            if rt.agent_executor is None:
                from app.agent.react_agent import build_agent_executor

                rt.agent_executor = build_agent_executor(meeting.id, llm)
            result = rt.agent_executor.invoke({"input": question})
            draft = result.get("output", "")
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


def _stream_answer(meeting: Meeting, question: str, context: str,
                   source: Optional[str] = None) -> None:
    """Cavabı token-token axıdır və hissə-hissə feed-ə 'answer' hadisəsi kimi yazır.

    Panel (SSE) hər aralıq hadisəni alıб mətni yeniləyir — canlı "yazılma" effekti.
    Bu, 3 tonlu strukturlaşdırılmış cavabdan həm hamardır, həm sürətlidir.
    D: `source` — cavabın əsaslandığı sənəd adı (panel 📚 çipi kimi göstərir).
    """
    llm = get_llm()
    has_ctx = bool(context and "tapılmadı" not in context)
    src = source if has_ctx else None
    prompt = ANSWER_STREAM.format(question=question, context=context or "kontekst tapılmadı")
    acc = ""
    last_len = 0
    try:
        for token in llm.stream(prompt, max_tokens=400):
            acc += token
            # ~hər 24 simvolda bir aralıq yeniləmə (mətn kumulyativdir — panel əvəzləyir)
            if len(acc) - last_len >= 24:
                repo.add_feed_event(meeting.id, "answer",
                    {"question": question, "text": acc, "done": False,
                     "based_on_context": has_ctx, "source": src})
                last_len = len(acc)
    except Exception as exc:  # noqa: BLE001 — streaming alınmasa tam çağırışa düş
        logger.warning("Streaming cavab alınmadı (%s) — tam çağırış", exc)
        try:
            acc = llm.complete(prompt, max_tokens=400)
        except Exception:  # noqa: BLE001
            return
    # Yekun (tam) hadisə — done=True
    repo.add_feed_event(meeting.id, "answer",
        {"question": question, "text": acc.strip(), "done": True,
         "based_on_context": has_ctx, "source": src})


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
    # Frontend stepper üçün başlanğıc mərhələ (pipeline hələ başlamayıb)
    from app.services import pipeline_status
    pipeline_status.set(meeting.id, stage="ended", topic=meeting.topic, delivered=None)

    # Gedən arxa plan təhlili varsa bitməsini gözləyirik, sonra yenisini bloklayırıq —
    # beləliklə hesabat tam transkript üzərində qurulur və yarış vəziyyəti olmur
    rt = _registry.get(meeting.id)
    if rt is not None:
        with rt.lock:
            rt.ended = True

    # Phase 3: transkript, xülasə, action-lar, kart, çatdırılma
    from app.services.post_meeting import run_post_meeting_pipeline

    run_post_meeting_pipeline(meeting)
    # Bitmiş iclasın runtime-ı artıq lazım deyil — yaddaş sızmasının qarşısını alırıq
    # (pipeline entity yaddaşını istifadə etdiyi üçün yalnız ondan SONRA silinir)
    _registry.pop(meeting.id, None)
    return meeting


def forget_meeting(meeting_id: str) -> None:
    """İclas silinəndə runtime reyestrini də təmizləyir."""
    _registry.pop(meeting_id, None)
