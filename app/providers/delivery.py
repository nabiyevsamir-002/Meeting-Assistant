"""Çatdırılma provayderləri: n8n webhook (real) | mock.

İclas hesabatı n8n-ə POST edilir, n8n workflow-u onu email və
Telegram ilə çatdırır (bax: n8n/delivery_workflow.json).
Mock rejimdə payload data/outbox/ qovluğuna JSON kimi yazılır.
"""
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class BaseDeliveryProvider(ABC):
    """Hesabatı çatdıran provayderlərin interfeysi."""

    name: str = "base"

    @abstractmethod
    def deliver(self, payload: dict[str, Any]) -> str:
        """Hesabatı göndərir, nəticə təsviri qaytarır."""


class MockDeliveryProvider(BaseDeliveryProvider):
    """Payload-u lokal outbox qovluğuna yazır."""

    name = "mock"

    def deliver(self, payload: dict[str, Any]) -> str:
        meeting_id = payload.get("meeting_id", "unknown")
        path = get_settings().data_path("outbox", f"{meeting_id}.json")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Mock çatdırılma outbox-a yazıldı: %s", path)
        return f"mock-outbox:{path}"


class N8NDeliveryProvider(BaseDeliveryProvider):
    """n8n webhook-una POST edir — oradan email/Telegram göndərilir."""

    name = "n8n"

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def deliver(self, payload: dict[str, Any]) -> str:
        import httpx

        resp = httpx.post(self._webhook_url, json=payload, timeout=30)
        resp.raise_for_status()
        return f"n8n-webhook:{resp.status_code}"


def create_delivery_provider(settings: Settings) -> BaseDeliveryProvider:
    """DELIVERY_PROVIDER dəyişəninə görə provayder qurur."""
    if settings.delivery_provider.lower() == "n8n":
        if settings.n8n_delivery_webhook_url:
            return N8NDeliveryProvider(settings.n8n_delivery_webhook_url)
        logger.warning("N8N_DELIVERY_WEBHOOK_URL boşdur — çatdırılma mock rejimə keçdi")
    return MockDeliveryProvider()
