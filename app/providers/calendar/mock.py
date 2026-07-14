"""Mock təqvim — Google hesabı olmadan planlayıcını test etmək üçün.

Həmişə "20 dəqiqə sonra" başlayan bir iclas qaytarır ki,
APScheduler-in iclas hazırlama axını işləkliyini göstərmək mümkün olsun.
"""
from datetime import datetime, timedelta, timezone

from app.models.core import CalendarEvent
from app.providers.calendar.base import BaseCalendarProvider


class MockCalendarProvider(BaseCalendarProvider):
    """Sabit ssenarili təqvim hadisələri."""

    name = "mock"

    def list_upcoming(self, lookahead_minutes: int = 30) -> list[CalendarEvent]:
        now = datetime.now(timezone.utc)
        start = now + timedelta(minutes=20)
        events = [
            CalendarEvent(
                id="mock-event-1",
                title="AI Meeting Assistant — sprint planlaması",
                start=start.isoformat(),
                end=(start + timedelta(hours=1)).isoformat(),
                description="Layihənin növbəti sprintinin planlaşdırılması",
                meet_link="https://meet.google.com/mock-demo",
            )
        ]
        # Yalnız lookahead pəncərəsinə düşənləri qaytarırıq (real davranış kimi)
        horizon = now + timedelta(minutes=lookahead_minutes)
        return [e for e in events if datetime.fromisoformat(e.start) <= horizon]
