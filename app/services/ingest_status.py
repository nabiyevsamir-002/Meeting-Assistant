"""Sənəd yükləmə mərhələlərinin yüngül in-memory izləyicisi.

Frontend PDF yükləyəndən sonra `/api/ingest/status/{doc_id}`-i poll edir və
mərhələləri canlı göstərir: yükləndi → bazaya yazıldı → ehtimal suallar
çıxarıldı → yaddaşa yazıldı.

Mərhələ (`stage`) dəyərləri:
  saved       — parçalar vektor bazasına yazıldı (chunks)
  extracting  — LLM ehtimal sualları hazırlayır (J)
  extracted   — suallar çıxarıldı (qa), indi yaddaşa yazılır
  done        — hazır (qa yaddaşa yazıldı) — qa=0 ola bilər (söndürülüb/tapılmadı)
  error       — hazırlıq alınmadı
"""
import threading
import time

_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_MAX = 24  # yaddaş sızmasının qarşısını almaq üçün son işlərin sayı


def set(doc_id: str, **fields) -> None:
    """Bir yükləmə işinin sahələrini yeniləyir (yoxdursa yaradır)."""
    with _lock:
        job = _jobs.get(doc_id) or {"doc_id": doc_id, "created": time.time()}
        job.update(fields)
        _jobs[doc_id] = job
        if len(_jobs) > _MAX:
            oldest = min(_jobs, key=lambda k: _jobs[k].get("created", 0))
            _jobs.pop(oldest, None)


def get(doc_id: str) -> dict | None:
    """İşin cari vəziyyətini qaytarır (yoxdursa None)."""
    with _lock:
        job = _jobs.get(doc_id)
        return dict(job) if job else None


def reset() -> None:
    """Bütün izləməni sıfırlayır (testlərdə və runtime reset-də)."""
    with _lock:
        _jobs.clear()
