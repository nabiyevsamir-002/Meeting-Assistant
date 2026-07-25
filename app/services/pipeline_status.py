"""İclas-sonrası pipeline mərhələlərinin yüngül in-memory izləyicisi.

Frontend «Bitir» basanda `/api/meetings/{id}/end-status`-i poll edir və
hesabatın hazırlanma addımlarını canlı göstərir:
  ended → assembled → summarized → actions → memorized → card → done

`delivered` sahəsi çatdırılmanın (email + Telegram) uğurunu bildirir.
"""
import threading
import time

_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_MAX = 24


def set(meeting_id: str, **fields) -> None:
    """Bir iclasın pipeline vəziyyətini yeniləyir (yoxdursa yaradır)."""
    with _lock:
        job = _jobs.get(meeting_id) or {"meeting_id": meeting_id, "created": time.time()}
        job.update(fields)
        _jobs[meeting_id] = job
        if len(_jobs) > _MAX:
            oldest = min(_jobs, key=lambda k: _jobs[k].get("created", 0))
            _jobs.pop(oldest, None)


def get(meeting_id: str) -> dict | None:
    """İclasın pipeline vəziyyətini qaytarır (yoxdursa None)."""
    with _lock:
        job = _jobs.get(meeting_id)
        return dict(job) if job else None


def reset() -> None:
    """Bütün izləməni sıfırlayır (testlərdə və runtime reset-də)."""
    with _lock:
        _jobs.clear()
