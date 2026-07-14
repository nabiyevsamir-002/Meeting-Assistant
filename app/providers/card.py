"""Xülasə kartı provayderləri: htmlcsstoimage.com (real) | mock.

İclasdan sonra HTML şablonundan vizual xülasə kartı yaradılır.
Mock rejimdə HTML fayl lokal data/cards/ qovluğuna yazılır —
brauzerdə açıb görmək olur; real rejimdə HCTI API PNG link qaytarır.
"""
import logging
from abc import ABC, abstractmethod

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Kartın HTML şablonu — inline CSS ilə (HCTI xarici CSS-i ayrıca parametrlə alır)
CARD_TEMPLATE = """<!DOCTYPE html>
<html lang="az">
<head><meta charset="utf-8">
<style>
  body {{ margin:0; font-family: -apple-system, 'Segoe UI', sans-serif; }}
  .card {{ width: 640px; padding: 32px; box-sizing: border-box;
          background: linear-gradient(135deg, #1e293b, #0f172a); color: #f1f5f9;
          border-radius: 16px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; color: #7dd3fc; }}
  .date {{ font-size: 13px; color: #94a3b8; margin-bottom: 16px; }}
  h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: 1px;
       color: #38bdf8; margin: 18px 0 8px; }}
  ul {{ margin: 0; padding-left: 20px; }}
  li {{ margin: 4px 0; font-size: 14px; line-height: 1.5; }}
  .overview {{ font-size: 14px; line-height: 1.6; color: #cbd5e1; }}
</style></head>
<body><div class="card">
  <h1>{headline}</h1>
  <div class="date">{topic} &middot; {date}</div>
  <p class="overview">{overview}</p>
  <h2>Əsas məqamlar</h2>
  <ul>{key_points}</ul>
  <h2>Növbəti addımlar</h2>
  <ul>{actions}</ul>
</div></body></html>"""


class BaseCardProvider(ABC):
    """HTML-dən vizual kart yaradan provayderlərin interfeysi."""

    name: str = "base"

    @abstractmethod
    def render(self, html: str, meeting_id: str) -> str:
        """HTML-i karta çevirir və URL/yol qaytarır."""


class MockCardProvider(BaseCardProvider):
    """HTML kartı lokal fayla yazır — açarsız vizual nəticə."""

    name = "mock"

    def render(self, html: str, meeting_id: str) -> str:
        path = get_settings().data_path("cards", f"{meeting_id}.html")
        path.write_text(html, encoding="utf-8")
        logger.info("Mock kart yazıldı: %s", path)
        return str(path)


class HCTICardProvider(BaseCardProvider):
    """htmlcsstoimage.com API — HTML-dən hostlanmış PNG şəkil yaradır."""

    name = "hcti"

    def __init__(self, user_id: str, api_key: str) -> None:
        self._user_id = user_id
        self._api_key = api_key

    def render(self, html: str, meeting_id: str) -> str:
        import httpx

        resp = httpx.post(
            "https://hcti.io/v1/image",
            auth=(self._user_id, self._api_key),
            data={"html": html, "device_scale": 2},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["url"]


def create_card_provider(settings: Settings) -> BaseCardProvider:
    """CARD_PROVIDER dəyişəninə görə provayder qurur."""
    if settings.card_provider.lower() == "hcti":
        if settings.hcti_user_id and settings.hcti_api_key:
            return HCTICardProvider(settings.hcti_user_id, settings.hcti_api_key)
        logger.warning("HCTI açarları boşdur — kart mock rejimə keçdi")
    return MockCardProvider()
