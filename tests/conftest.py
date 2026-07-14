"""Test konfiqurasiyası.

Vacib: mühit dəyişənləri app import olunmazdan ƏVVƏL qurulmalıdır —
pytest conftest-i test modullarından əvvəl yüklədiyi üçün bu işləyir.
Bütün testlər mock provayderlərlə və müvəqqəti SQLite ilə işləyir.
"""
import os
import tempfile

# Testlər üçün tam təcrid olunmuş mühit
_tmp = tempfile.mkdtemp(prefix="meeting-assistant-test-")
os.environ.update({
    "LLM_PROVIDER": "mock",
    "STT_PROVIDER": "mock",
    "TTS_PROVIDER": "mock",
    "EMBEDDING_PROVIDER": "mock",
    "VECTOR_BACKEND": "memory",
    "LONGTERM_PROVIDER": "mock",
    "CALENDAR_PROVIDER": "mock",
    "CARD_PROVIDER": "mock",
    "DELIVERY_PROVIDER": "mock",
    "AUTH_ENABLED": "false",
    "SCHEDULER_ENABLED": "false",
    "SQLITE_PATH": f"{_tmp}/test.db",
    "DATA_DIR": _tmp,
    "LOG_LEVEL": "WARNING",
})

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Lifespan-lı TestClient — hər test təmiz runtime ilə başlayır."""
    from app.main import app
    from app.runtime import reset_runtime

    reset_runtime()
    with TestClient(app) as c:
        yield c
