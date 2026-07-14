"""Təqvim provayder factory-si: mock | google."""
import logging

from app.config import Settings
from app.providers.calendar.base import BaseCalendarProvider
from app.providers.calendar.mock import MockCalendarProvider

logger = logging.getLogger(__name__)


def create_calendar_provider(settings: Settings) -> BaseCalendarProvider:
    """CALENDAR_PROVIDER dəyişəninə görə provayder qurur."""
    if settings.calendar_provider.lower() == "google":
        if settings.google_client_id and settings.google_client_secret:
            from app.providers.calendar.google import GoogleCalendarProvider

            return GoogleCalendarProvider(settings)
        logger.warning("Google OAuth məlumatları boşdur — təqvim mock rejimə keçdi")
    return MockCalendarProvider()
