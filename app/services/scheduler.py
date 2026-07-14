"""APScheduler — iclasdan əvvəl avtomatik hazırlıq.

Hər CALENDAR_POLL_MINUTES dəqiqədən bir təqvim yoxlanılır:
yaxın LOOKAHEAD pəncərəsində başlayacaq iclas varsa, onun üçün
"scheduled" statuslu iclas qeydi yaradılır (dublikatsız).
Beləliklə iclas başlayanda sistem artıq hazır olur.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.models.core import Meeting
from app.runtime import get_calendar
from app.storage import repo

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def prepare_upcoming_meetings() -> int:
    """Təqvimdəki yaxın iclaslar üçün qeyd yaradır; yaradılan sayı qaytarır."""
    settings = get_settings()
    calendar = get_calendar()
    created = 0
    try:
        events = calendar.list_upcoming(settings.calendar_lookahead_minutes)
    except Exception as exc:  # noqa: BLE001 — təqvim xətası planlayıcını öldürməsin
        logger.warning("Təqvim sorğusu alınmadı: %s", exc)
        return 0

    for event in events:
        # Eyni mövzulu iclas artıq varsa, təkrar yaratmırıq
        if repo.find_meeting_by_topic(event.title):
            continue
        meeting = Meeting(
            topic=event.title,
            status="scheduled",
            source="calendar",
            scheduled_at=event.start,
        )
        repo.save_meeting(meeting)
        created += 1
        logger.info("Təqvimdən iclas hazırlandı: «%s» (%s)", event.title, event.start)
    return created


def start_scheduler() -> None:
    """Fon planlayıcısını işə salır (app startup-da çağırılır)."""
    global _scheduler
    settings = get_settings()
    if not settings.scheduler_enabled or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        prepare_upcoming_meetings,
        "interval",
        minutes=settings.calendar_poll_minutes,
        id="calendar-poll",
        # Başlanğıcda da bir dəfə işləsin deyə next_run_time-ı indiyə qoymuruq —
        # startup-da prepare_upcoming_meetings() ayrıca çağırılır
    )
    _scheduler.start()
    logger.info("Planlayıcı başladı (hər %d dəqiqə)", settings.calendar_poll_minutes)


def stop_scheduler() -> None:
    """Planlayıcını dayandırır (app shutdown-da çağırılır)."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Planlayıcı dayandırıldı")
