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
    "CARD_PROVIDER": "mock",
    "DELIVERY_PROVIDER": "mock",
    "AUTH_ENABLED": "false",
    # Testlər TAM kurs pipeline-ını yoxlayır (ReAct agent + bütün suallar).
    # Canlı demo isə sürət üçün default olaraq sadələşdirilmiş yolla işləyir.
    "LIVE_FAST_ANSWERS": "false",
    "ANSWER_ONLY_DIRECTED": "false",
    # J (öncədən Q&A) uçdan-uca testdə arxa plan thread-i yaratmasın —
    # onu ayrıca birbaşa unit testdə yoxlayırıq (test_providers.py).
    "PREPARED_QA_ENABLED": "false",
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
