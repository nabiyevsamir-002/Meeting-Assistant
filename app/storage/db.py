"""SQLite bağlantısı və sxem inisializasiyası.

ORM istifadə etmirik — kurs məqsədi üçün təmiz SQL daha oxunaqlıdır.
Hər əməliyyat üçün qısa ömürlü bağlantı açılır (bu miqyas üçün kifayətdir).
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import get_settings

# Verilənlər bazasının sxemi — bütün cədvəllər burada
SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id           TEXT PRIMARY KEY,
    topic        TEXT NOT NULL,
    status       TEXT NOT NULL,
    language     TEXT NOT NULL DEFAULT 'az',
    source       TEXT NOT NULL DEFAULT 'manual',
    user_name    TEXT,
    scheduled_at TEXT,
    started_at   TEXT,
    ended_at     TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS segments (
    id         TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    text       TEXT NOT NULL,
    speaker    TEXT,
    duration   REAL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feed_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id TEXT NOT NULL,
    type       TEXT NOT NULL,
    payload    TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    source_type  TEXT NOT NULL,
    url          TEXT,
    meeting_topic TEXT,
    chunk_count  INTEGER DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    meeting_id    TEXT PRIMARY KEY,
    topic         TEXT NOT NULL,
    transcript    TEXT NOT NULL,
    summary       TEXT NOT NULL,
    action_items  TEXT NOT NULL,
    entities      TEXT NOT NULL DEFAULT '[]',
    card_url      TEXT,
    delivered     INTEGER DEFAULT 0,
    delivery_info TEXT,
    created_at    TEXT NOT NULL
);

-- Uzunmüddətli yaddaşın mock saxlanması (mem0 olmayanda)
CREATE TABLE IF NOT EXISTS long_term_memories (
    id         TEXT PRIMARY KEY,
    meeting_id TEXT,
    kind       TEXT NOT NULL DEFAULT 'episode',
    text       TEXT NOT NULL,
    meta       TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""


def _db_path() -> str:
    """SQLite faylının yolunu qaytarır, qovluğu yaradır."""
    p = Path(get_settings().sqlite_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Sətirlərə dict kimi baxmağa imkan verən bağlantı konteksti."""
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Bütün cədvəlləri yaradır (mövcuddursa toxunmur) və miqrasiyaları tətbiq edir."""
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Miqrasiya: köhnə bazalarda user_name sütunu yoxdur — əlavə edirik.
        # (İclasa bağlı ad: suallar "bu şəxsə ünvanlanıb?" yoxlamasında istifadə olunur.)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(meetings)")}
        if "user_name" not in cols:
            conn.execute("ALTER TABLE meetings ADD COLUMN user_name TEXT")
