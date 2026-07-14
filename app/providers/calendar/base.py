"""Təqvim provayderlərinin baza interfeysi."""
from abc import ABC, abstractmethod

from app.models.core import CalendarEvent


class BaseCalendarProvider(ABC):
    """Yaxınlaşan iclasları qaytaran provayderlərin interfeysi."""

    name: str = "base"

    @abstractmethod
    def list_upcoming(self, lookahead_minutes: int = 30) -> list[CalendarEvent]:
        """Verilən müddət ərzində başlayacaq hadisələri qaytarır."""
