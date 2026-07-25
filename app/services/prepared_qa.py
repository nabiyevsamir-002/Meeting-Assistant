"""J — öncədən hazırlanmış Q&A keşi (semantik sürətləndirici).

İdeya: PDF yüklənəndə (vaxt kritik OLMAYAN an) LLM sənəddən ehtimal olunan
sual/cavab cütləri hazırlayır və hər sualın embedding-i saxlanır. İclasda
sual aşkarlananda onun vektoru bu suallarla tutuşdurulur — yüksək oxşarlıqda
hazır cavab DƏRHAL verilir (0 LLM çağırışı). Zəif uyğunluqda adi RAG yoluna
düşülür. Beləliklə cavab generasiyası kritik yoldan çıxarılır.

Qeyd: bu modul settings.prepared_qa_enabled bayrağını YOXLAMIR — onu çağıran
yerlər (ingest, meeting_service) yoxlayır. Beləliklə funksiyalar birbaşa
(məs. testdə) çağırıla bilir.
"""
import logging
import math
import re
import threading
from dataclasses import dataclass

from app.config import get_settings
from app.models.structured import PreparedQAList
from app.prompts import GENERATE_QA
from app.runtime import get_embedder, get_llm

logger = logging.getLogger(__name__)


@dataclass
class Prepared:
    """Bir hazır Q&A cütü + sualın vektoru."""
    question: str
    answer: str
    vector: list[float]


# Qlobal keş (bilik bazası kimi qlobaldır — bütün sənədlərdən toplanır)
_store: list[Prepared] = []
_lock = threading.Lock()


def reset() -> None:
    """Keşi sıfırlayır (testlərdə və runtime reset-də)."""
    with _lock:
        _store.clear()


def size() -> int:
    """Keşdəki hazır Q&A sayı."""
    with _lock:
        return len(_store)


def _normalize(text: str) -> str:
    """Müqayisə üçün sadə normallaşdırma."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _cosine(a: list[float], b: list[float]) -> float:
    """İki vektor arasında kosinus oxşarlığı (normalizasiyadan asılı olmadan)."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def build_from_text(text: str, doc_id: str | None = None) -> int:
    """Sənəd mətnindən ehtimal Q&A hazırlayıb keşə əlavə edir; sayı qaytarır.

    `doc_id` verilibsə, mərhələlər ingest_status-a yazılır ki, frontend
    onları canlı göstərə bilsin. Xəta-təhlükəsizdir: hər hansı addım
    alınmasa 0 qaytarır və ingest-i pozmur.
    """
    def _status(stage: str, **f) -> None:
        if doc_id:
            from app.services import ingest_status
            ingest_status.set(doc_id, stage=stage, **f)

    if not text or not text.strip():
        _status("done", done=True, qa=0)
        return 0
    settings = get_settings()
    _status("extracting")
    try:
        qa: PreparedQAList = get_llm().generate_structured(
            GENERATE_QA.format(count=settings.prepared_qa_count, text=text[:6000]),
            PreparedQAList,
        )
    except Exception as exc:  # noqa: BLE001 — hazırlıq xətası ingest-i pozmasın
        logger.warning("Öncədən Q&A generasiyası alınmadı: %s", exc)
        _status("error", done=True, error=str(exc))
        return 0

    pairs = [
        (p.question.strip(), p.answer.strip())
        for p in qa.items
        if p.question.strip() and p.answer.strip()
    ]
    if not pairs:
        _status("done", done=True, qa=0)
        return 0

    # Suallar çıxarıldı — indi embedding-ləyib yaddaşa yazırıq
    _status("extracted", qa=len(pairs))
    try:
        vectors = get_embedder().embed([q for q, _ in pairs])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Q&A embedding-i alınmadı: %s", exc)
        _status("error", done=True, error=str(exc))
        return 0

    with _lock:
        existing = {_normalize(p.question) for p in _store}
        added = 0
        for (q, a), v in zip(pairs, vectors):
            if _normalize(q) in existing:
                continue  # təkrar yükləmədə dublikatı əlavə etmirik
            _store.append(Prepared(question=q, answer=a, vector=v))
            added += 1
    logger.info("Öncədən %d Q&A hazırlandı (keş ölçüsü=%d)", added, size())
    _status("done", done=True, qa=len(pairs))
    return added


def match(question: str, threshold: float | None = None) -> Prepared | None:
    """Canlı sualı keşlə tutuşdurur; yüksək oxşarlıqda Prepared, yoxsa None."""
    with _lock:
        items = list(_store)
    if not items or not question.strip():
        return None
    thr = get_settings().prepared_qa_threshold if threshold is None else threshold
    try:
        qv = get_embedder().embed_one(question)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sual embedding-i alınmadı: %s", exc)
        return None

    best: Prepared | None = None
    best_score = 0.0
    for it in items:
        s = _cosine(qv, it.vector)
        if s > best_score:
            best, best_score = it, s
    if best is not None and best_score >= thr:
        logger.info("J: hazır cavab uyğunlaşdı (oxşarlıq=%.3f)", best_score)
        return best
    return None
