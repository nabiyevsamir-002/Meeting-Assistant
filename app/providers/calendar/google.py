"""Google Calendar provayderi — OAuth 2.0 (Authorization Code Flow).

Ağır Google SDK-ları əvəzinə axın httpx ilə "əl ilə" qurulub —
OAuth 2.0-ın necə işlədiyini kodda addım-addım görmək üçün:

  1. /api/auth/google/login  -> istifadəçi Google-un icazə səhifəsinə yönləndirilir
  2. Google geri /api/auth/google/callback?code=... çağırır
  3. code -> access_token + refresh_token mübadiləsi (exchange_code)
  4. Token data/google_token.json faylında saxlanır
  5. Vaxtı keçəndə refresh_token ilə yenilənir (_refresh)
"""
import json
import logging
import time
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from app.config import Settings, get_settings
from app.models.core import CalendarEvent
from app.providers.calendar.base import BaseCalendarProvider

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


def _token_path() -> str:
    """Token faylının yolu (data/ qovluğunda, git-ə düşmür)."""
    return str(get_settings().data_path("google_token.json"))


def build_auth_url(settings: Settings, state: str = "meeting-assistant") -> str:
    """İstifadəçini yönləndirmək üçün Google icazə URL-i qurur."""
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",   # refresh_token almaq üçün vacibdir
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(settings: Settings, code: str) -> dict[str, Any]:
    """Authorization code-u token-lərə dəyişir və fayla yazır."""
    resp = httpx.post(
        TOKEN_URL,
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.google_redirect_uri,
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()
    token["obtained_at"] = time.time()
    with open(_token_path(), "w", encoding="utf-8") as f:
        json.dump(token, f)
    logger.info("Google token alındı və saxlanıldı")
    return token


class GoogleCalendarProvider(BaseCalendarProvider):
    """Saxlanmış OAuth token ilə Google Calendar-dan hadisələr oxuyur."""

    name = "google"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _load_token(self) -> Optional[dict[str, Any]]:
        """Diskdən token oxuyur, yoxdursa None."""
        try:
            with open(_token_path(), encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def _refresh(self, token: dict[str, Any]) -> dict[str, Any]:
        """Vaxtı keçmiş access_token-i refresh_token ilə yeniləyir."""
        resp = httpx.post(
            TOKEN_URL,
            data={
                "client_id": self._settings.google_client_id,
                "client_secret": self._settings.google_client_secret,
                "refresh_token": token["refresh_token"],
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        resp.raise_for_status()
        fresh = resp.json()
        # refresh cavabında refresh_token olmur — köhnəni saxlayırıq
        token.update(fresh)
        token["obtained_at"] = time.time()
        with open(_token_path(), "w", encoding="utf-8") as f:
            json.dump(token, f)
        return token

    def _access_token(self) -> Optional[str]:
        """Etibarlı access_token qaytarır (lazımdırsa yeniləyir)."""
        token = self._load_token()
        if not token:
            logger.warning("Google token yoxdur — əvvəlcə /api/auth/google/login keçin")
            return None
        expires_in = token.get("expires_in", 3600)
        # 60 saniyə ehtiyat pəncərəsi ilə yoxlayırıq
        if time.time() > token.get("obtained_at", 0) + expires_in - 60:
            if "refresh_token" not in token:
                return None
            token = self._refresh(token)
        return token.get("access_token")

    def list_upcoming(self, lookahead_minutes: int = 30) -> list[CalendarEvent]:
        access = self._access_token()
        if not access:
            return []
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        params = {
            "timeMin": now.isoformat(),
            "timeMax": (now + timedelta(minutes=lookahead_minutes)).isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "10",
        }
        resp = httpx.get(
            EVENTS_URL,
            params=params,
            headers={"Authorization": f"Bearer {access}"},
            timeout=30,
        )
        resp.raise_for_status()
        events = []
        for item in resp.json().get("items", []):
            start = item.get("start", {})
            end = item.get("end", {})
            events.append(
                CalendarEvent(
                    id=item["id"],
                    title=item.get("summary", "Adsız iclas"),
                    start=start.get("dateTime", start.get("date", "")),
                    end=end.get("dateTime", end.get("date")),
                    description=item.get("description"),
                    meet_link=item.get("hangoutLink"),
                )
            )
        return events
