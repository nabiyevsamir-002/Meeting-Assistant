"""Repository funksiyaları — domen modelləri ilə SQLite arasında körpü."""
import json
from typing import Any, Optional

from app.models.core import FeedEvent, Meeting, MeetingReport, TranscriptSegment
from app.storage.db import get_conn


# --- İclaslar ---

def save_meeting(m: Meeting) -> None:
    """İclası yazır və ya yeniləyir (UPSERT)."""
    with get_conn() as c:
        c.execute(
            """INSERT INTO meetings (id, topic, status, language, source, user_name,
                                     scheduled_at, started_at, ended_at, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 topic=excluded.topic, status=excluded.status,
                 user_name=excluded.user_name,
                 scheduled_at=excluded.scheduled_at,
                 started_at=excluded.started_at, ended_at=excluded.ended_at""",
            (m.id, m.topic, m.status, m.language, m.source, m.user_name,
             m.scheduled_at, m.started_at, m.ended_at, m.created_at),
        )


def get_meeting(meeting_id: str) -> Optional[Meeting]:
    """İclası ID ilə tapır."""
    with get_conn() as c:
        row = c.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
    return Meeting(**dict(row)) if row else None


def list_meetings() -> list[Meeting]:
    """Bütün iclasları yenidən köhnəyə sıralayır."""
    with get_conn() as c:
        rows = c.execute("SELECT * FROM meetings ORDER BY created_at DESC").fetchall()
    return [Meeting(**dict(r)) for r in rows]


def delete_meeting(meeting_id: str) -> None:
    """İclası bütün əlaqəli məlumatları ilə birlikdə silir."""
    with get_conn() as c:
        c.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))
        c.execute("DELETE FROM segments WHERE meeting_id=?", (meeting_id,))
        c.execute("DELETE FROM feed_events WHERE meeting_id=?", (meeting_id,))
        c.execute("DELETE FROM reports WHERE meeting_id=?", (meeting_id,))


def end_stale_live_meetings() -> int:
    """Server yenidən başlayanda 'canlı' qalmış iclasları bitmiş sayır.

    Canlı iclasın vəziyyəti (yaddaş/agent) yalnız prosesin içindədir; proses
    yenidən başlayanda o itir. Belə 'zombi' iclaslar panel/agent-i çaşdırmasın
    deyə onları 'ended' işarələyirik (hesabatsız — natamam ola bilər).
    """
    from app.models.core import utcnow_iso

    with get_conn() as c:
        cur = c.execute(
            "UPDATE meetings SET status='ended', ended_at=? "
            "WHERE status='live'",
            (utcnow_iso(),),
        )
        return cur.rowcount


def find_meeting_by_topic(topic: str) -> Optional[Meeting]:
    """Mövzuya görə iclas axtarır (planlayıcı dublikat yaratmasın deyə)."""
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM meetings WHERE topic=? ORDER BY created_at DESC LIMIT 1",
            (topic,),
        ).fetchone()
    return Meeting(**dict(row)) if row else None


# --- Seqmentlər ---

def save_segment(s: TranscriptSegment) -> None:
    """Transkript seqmentini yazır."""
    with get_conn() as c:
        c.execute(
            """INSERT INTO segments (id, meeting_id, seq, text, speaker, duration, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (s.id, s.meeting_id, s.seq, s.text, s.speaker, s.duration, s.created_at),
        )


def list_segments(meeting_id: str) -> list[TranscriptSegment]:
    """İclasın bütün seqmentlərini ardıcıllıqla qaytarır."""
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM segments WHERE meeting_id=? ORDER BY seq", (meeting_id,)
        ).fetchall()
    return [TranscriptSegment(**dict(r)) for r in rows]


def next_segment_seq(meeting_id: str) -> int:
    """Növbəti seqment nömrəsini hesablayır."""
    with get_conn() as c:
        row = c.execute(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM segments WHERE meeting_id=?",
            (meeting_id,),
        ).fetchone()
    return int(row["m"]) + 1


# --- Feed hadisələri ---

def add_feed_event(meeting_id: str, type_: str, payload: dict[str, Any]) -> int:
    """Canlı feed-ə hadisə əlavə edir, avtoartan ID qaytarır."""
    from app.models.core import utcnow_iso

    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO feed_events (meeting_id, type, payload, created_at) VALUES (?,?,?,?)",
            (meeting_id, type_, json.dumps(payload, ensure_ascii=False), utcnow_iso()),
        )
        return int(cur.lastrowid)


def list_feed_events(meeting_id: str, after_id: int = 0) -> list[FeedEvent]:
    """after_id-dən sonrakı hadisələri qaytarır (polling üçün)."""
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM feed_events WHERE meeting_id=? AND id>? ORDER BY id",
            (meeting_id, after_id),
        ).fetchall()
    return [
        FeedEvent(
            id=r["id"], meeting_id=r["meeting_id"], type=r["type"],
            payload=json.loads(r["payload"]), created_at=r["created_at"],
        )
        for r in rows
    ]


# --- Sənədlər ---

def save_document(doc_id: str, title: str, source_type: str, url: Optional[str],
                  meeting_topic: Optional[str], chunk_count: int) -> None:
    """Bilik bazasına yüklənmiş sənədin metadatasını yazır."""
    from app.models.core import utcnow_iso

    with get_conn() as c:
        c.execute(
            """INSERT INTO documents (id, title, source_type, url, meeting_topic, chunk_count, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (doc_id, title, source_type, url, meeting_topic, chunk_count, utcnow_iso()),
        )


def list_documents() -> list[dict[str, Any]]:
    """Yüklənmiş sənədlərin siyahısı."""
    with get_conn() as c:
        rows = c.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


# --- Hesabatlar ---

def save_report(r: MeetingReport) -> None:
    """Yekun hesabatı yazır (UPSERT)."""
    with get_conn() as c:
        c.execute(
            """INSERT INTO reports (meeting_id, topic, transcript, summary, action_items,
                                    entities, card_url, delivered, delivery_info, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(meeting_id) DO UPDATE SET
                 transcript=excluded.transcript, summary=excluded.summary,
                 action_items=excluded.action_items, entities=excluded.entities,
                 card_url=excluded.card_url, delivered=excluded.delivered,
                 delivery_info=excluded.delivery_info""",
            (r.meeting_id, r.topic, r.transcript,
             json.dumps(r.summary, ensure_ascii=False),
             json.dumps(r.action_items, ensure_ascii=False),
             json.dumps(r.entities, ensure_ascii=False),
             r.card_url, int(r.delivered), r.delivery_info, r.created_at),
        )


def get_report(meeting_id: str) -> Optional[MeetingReport]:
    """Hesabatı ID ilə tapır."""
    with get_conn() as c:
        row = c.execute("SELECT * FROM reports WHERE meeting_id=?", (meeting_id,)).fetchone()
    if not row:
        return None
    return MeetingReport(
        meeting_id=row["meeting_id"], topic=row["topic"], transcript=row["transcript"],
        summary=json.loads(row["summary"]), action_items=json.loads(row["action_items"]),
        entities=json.loads(row["entities"]), card_url=row["card_url"],
        delivered=bool(row["delivered"]), delivery_info=row["delivery_info"],
        created_at=row["created_at"],
    )


# --- Statistika (UI dashboard-u üçün) ---

def get_stats() -> dict[str, int]:
    """Ümumi göstəricilər: iclas, hesabat, sənəd və action item sayı."""
    with get_conn() as c:
        meetings = c.execute("SELECT COUNT(*) AS n FROM meetings").fetchone()["n"]
        reports = c.execute("SELECT COUNT(*) AS n FROM reports").fetchone()["n"]
        documents = c.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
        rows = c.execute("SELECT action_items FROM reports").fetchall()
    # Action item-lər hesabatlarda JSON siyahı kimi saxlanır — sayını toplayırıq
    actions = sum(len(json.loads(r["action_items"])) for r in rows)
    return {"meetings": meetings, "reports": reports,
            "documents": documents, "action_items": actions}


# --- Uzunmüddətli yaddaş (mock mem0) ---

def save_long_term(mem_id: str, meeting_id: Optional[str], kind: str,
                   text: str, meta: dict[str, Any]) -> None:
    """Uzunmüddətli yaddaş qeydini yazır."""
    from app.models.core import utcnow_iso

    with get_conn() as c:
        c.execute(
            "INSERT INTO long_term_memories (id, meeting_id, kind, text, meta, created_at) VALUES (?,?,?,?,?,?)",
            (mem_id, meeting_id, kind, text, json.dumps(meta, ensure_ascii=False), utcnow_iso()),
        )


def search_long_term(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Sadə LIKE axtarışı — mock rejim üçün kifayətdir."""
    with get_conn() as c:
        rows = c.execute(
            """SELECT * FROM long_term_memories
               WHERE text LIKE ? ORDER BY created_at DESC LIMIT ?""",
            (f"%{query}%", limit),
        ).fetchall()
    return [
        {**dict(r), "meta": json.loads(r["meta"])}
        for r in rows
    ]
