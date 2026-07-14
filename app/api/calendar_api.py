"""Təqvim endpointləri (Phase 1) — yaxınlaşan iclaslar."""
from fastapi import APIRouter, Depends

from app.api.deps import require_user
from app.config import get_settings
from app.models.core import CalendarEvent
from app.runtime import get_calendar

router = APIRouter(dependencies=[Depends(require_user)])


@router.get("/upcoming", response_model=list[CalendarEvent])
def upcoming() -> list[CalendarEvent]:
    """Yaxın pəncərədə başlayacaq təqvim hadisələri (mock və ya Google)."""
    settings = get_settings()
    return get_calendar().list_upcoming(settings.calendar_lookahead_minutes)


@router.post("/prepare")
def prepare_now() -> dict:
    """Planlayıcının işini əl ilə işə salır — nümayiş üçün faydalıdır."""
    from app.services.scheduler import prepare_upcoming_meetings

    created = prepare_upcoming_meetings()
    return {"created_meetings": created}
