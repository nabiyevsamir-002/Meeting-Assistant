"""İclas endpointləri (Phase 2 və 3) — canlı pipeline-ın API üzü."""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import require_user
from app.models.core import (
    FeedEvent,
    Meeting,
    MeetingCreate,
    MeetingReport,
    SegmentIn,
    TranscriptSegment,
)
from app.services import meeting_service
from app.storage import repo

router = APIRouter(dependencies=[Depends(require_user)])


def _get_or_404(meeting_id: str) -> Meeting:
    """İclası tapır, yoxdursa 404 qaytarır."""
    meeting = repo.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="İclas tapılmadı")
    return meeting


@router.post("", response_model=Meeting)
def create_meeting(req: MeetingCreate) -> Meeting:
    """Yeni iclas yaradır (hələ başlamır)."""
    meeting = Meeting(topic=req.topic, language=req.language,
                      scheduled_at=req.scheduled_at, user_name=req.user_name)
    repo.save_meeting(meeting)
    return meeting


@router.get("", response_model=list[Meeting])
def list_meetings() -> list[Meeting]:
    """Bütün iclasların siyahısı."""
    return repo.list_meetings()


@router.get("/{meeting_id}", response_model=Meeting)
def get_meeting(meeting_id: str) -> Meeting:
    """Bir iclasın detalları."""
    return _get_or_404(meeting_id)


@router.delete("/{meeting_id}")
def delete_meeting(meeting_id: str) -> dict:
    """İclası bütün məlumatları ilə silir (köhnə test iclaslarını təmizləmək üçün)."""
    meeting = _get_or_404(meeting_id)
    if meeting.status == "live":
        raise HTTPException(status_code=409, detail="Canlı iclası əvvəlcə bitirin")
    repo.delete_meeting(meeting_id)
    meeting_service.forget_meeting(meeting_id)
    return {"deleted": meeting_id}


@router.post("/{meeting_id}/start", response_model=Meeting)
def start_meeting(meeting_id: str) -> Meeting:
    """İclası canlı rejimə keçirir."""
    return meeting_service.start_meeting(_get_or_404(meeting_id))


@router.post("/{meeting_id}/segments/text", response_model=TranscriptSegment)
def add_text_segment(meeting_id: str, seg: SegmentIn) -> TranscriptSegment:
    """Mətn seqmentini pipeline-a göndərir (audio olmadan test rejimi)."""
    meeting = _get_or_404(meeting_id)
    if meeting.status != "live":
        raise HTTPException(status_code=409, detail="İclas canlı deyil — əvvəlcə /start çağırın")
    return meeting_service.process_text_segment(meeting, seg)


@router.post("/{meeting_id}/segments/audio", response_model=TranscriptSegment)
async def add_audio_segment(meeting_id: str, file: UploadFile) -> TranscriptSegment:
    """Audio parçasını (15-30s) qəbul edib STT -> pipeline axınına ötürür."""
    meeting = _get_or_404(meeting_id)
    if meeting.status != "live":
        raise HTTPException(status_code=409, detail="İclas canlı deyil — əvvəlcə /start çağırın")
    audio = await file.read()
    # VACİB: STT + LLM çağırışları sinxron və uzundur (real provayderlə onlarla
    # saniyə). Birbaşa çağırsaq event loop kilidlənir və BÜTÜN server donur —
    # ona görə işi thread hovuzuna veririk, loop isə digər sorğulara cavab verir.
    return await run_in_threadpool(
        meeting_service.process_audio_chunk, meeting, audio, file.filename or "chunk.wav"
    )


@router.get("/{meeting_id}/feed", response_model=list[FeedEvent])
def feed(meeting_id: str, after_id: int = 0) -> list[FeedEvent]:
    """Canlı feed — UI son gördüyü hadisədən sonrakıları alır (polling)."""
    _get_or_404(meeting_id)
    return repo.list_feed_events(meeting_id, after_id)


@router.get("/{meeting_id}/stream")
async def stream_feed(meeting_id: str, request: Request, after_id: int = 0):
    """Feed-in SSE (streaming) versiyası — hadisələr yazılan kimi DƏRHAL çatır.

    Panel bunu EventSource ilə oxuyur; 2 saniyəlik polling gecikməsi aradan qalxır.
    Alınmazsa panel avtomatik polling-ə keçir (etibarlılıq üçün ehtiyat).
    """
    _get_or_404(meeting_id)

    async def gen():
        last = after_id
        while True:
            if await request.is_disconnected():
                break
            # SQLite oxunuşu sinxrondur — event loop-u bloklamamaq üçün thread hovuzunda
            events = await run_in_threadpool(repo.list_feed_events, meeting_id, last)
            for e in events:
                last = max(last, e.id)
                yield f"data: {json.dumps(e.model_dump(), ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.2)  # yeni hadisələri ~0.2s-də bir yoxla (daha canlı)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )


@router.post("/{meeting_id}/end", response_model=MeetingReport)
def end_meeting(meeting_id: str) -> MeetingReport:
    """İclası bitirir, iclas-sonrası pipeline işləyir və hesabat qayıdır."""
    meeting = _get_or_404(meeting_id)
    meeting_service.end_meeting(meeting)
    report = repo.get_report(meeting_id)
    if not report:
        raise HTTPException(status_code=500, detail="Hesabat yaradıla bilmədi")
    return report


@router.get("/{meeting_id}/end-status")
def end_status(meeting_id: str) -> dict:
    """İclas-sonrası pipeline mərhələsi — frontend «Bitir» prosesini canlı göstərir."""
    from app.services import pipeline_status

    return pipeline_status.get(meeting_id) or {"meeting_id": meeting_id, "stage": "ended"}


@router.get("/{meeting_id}/report", response_model=MeetingReport)
def get_report(meeting_id: str) -> MeetingReport:
    """Hazır hesabatı qaytarır."""
    report = repo.get_report(meeting_id)
    if not report:
        raise HTTPException(status_code=404, detail="Hesabat hələ hazır deyil")
    return report


@router.get("/{meeting_id}/summary-audio")
def summary_audio(meeting_id: str) -> FileResponse:
    """Xülasənin səsli versiyası (TTS, istəyə bağlı)."""
    from app.services.post_meeting import synthesize_summary_audio

    path = synthesize_summary_audio(meeting_id)
    if not path:
        raise HTTPException(status_code=404, detail="Hesabat hələ hazır deyil")
    return FileResponse(path)
