"""Uçdan-uca iclas axını testi — bütün üç mərhələ mock rejimdə.

Ssenari: sənəd yüklə -> iclas yarat -> başlat -> seqmentlər göndər
-> feed-də sual + cavab variantları yoxla -> bitir -> hesabatı yoxla
-> yaddaşda axtar.
"""
import io
import struct
import wave


def _sample_wav() -> bytes:
    """1 saniyəlik səssiz WAV yaradır (mock STT məzmuna baxmır)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))
    return buf.getvalue()


def test_full_meeting_lifecycle(client):
    """Phase 1-2-3-ün tam dövrü mock provayderlərlə işləməlidir."""
    # --- Phase 1: bilik bazasına sənəd yüklə ---
    resp = client.post("/api/ingest", json={
        "title": "Layihə brifi",
        "content": "AI Meeting Assistant layihəsinin deadline-ı 30 sentyabrdır. "
                   "Büdcə artıq təsdiqlənib. İnteqrasiya üçün Claude API seçilib. "
                   "Vektor bazası kimi Qdrant istifadə olunacaq.",
        "source_type": "text",
    })
    assert resp.status_code == 200
    assert resp.json()["chunk_count"] >= 1

    # Kontekst axtarışı işləyir
    resp = client.get("/api/ingest/search", params={"q": "deadline"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # --- Phase 2: iclas yarat, başlat, seqmentlər göndər ---
    meeting = client.post("/api/meetings", json={"topic": "Sprint planlaması"}).json()
    mid = meeting["id"]

    # Başlamamış iclasa seqment göndərmək 409 olmalıdır
    resp = client.post(f"/api/meetings/{mid}/segments/text",
                       json={"text": "Test"})
    assert resp.status_code == 409

    client.post(f"/api/meetings/{mid}/start")

    # Adi seqment — sual yoxdur
    client.post(f"/api/meetings/{mid}/segments/text",
                json={"text": "Layihə planını nəzərdən keçiririk."})
    # Sual olan seqment — pipeline sual + cavab variantları çıxarmalıdır
    client.post(f"/api/meetings/{mid}/segments/text",
                json={"text": "Samir, layihənin deadline-ı nə vaxtdır?"})
    # Action item olan seqment
    client.post(f"/api/meetings/{mid}/segments/text",
                json={"text": "Samir sənədləri cümə gününə qədər hazırlayacaq."})

    # Audio seqment (mock STT ssenaridən cümlə qaytarır)
    resp = client.post(
        f"/api/meetings/{mid}/segments/audio",
        files={"file": ("chunk.wav", _sample_wav(), "audio/wav")},
    )
    assert resp.status_code == 200
    assert resp.json()["text"]

    # Feed-i yoxla
    feed = client.get(f"/api/meetings/{mid}/feed").json()
    types = {e["type"] for e in feed}
    assert "segment" in types
    assert "question" in types
    assert "answer_options" in types

    # Cavab variantları kontekstə əsaslanmalı və agent addımları görünməlidir
    answers = [e for e in feed if e["type"] == "answer_options"]
    assert len(answers[0]["payload"]["options"]) >= 2
    steps = answers[0]["payload"]["agent_steps"]
    assert any(s["tool"] == "search_context" for s in steps)

    # --- Phase 3: iclası bitir, hesabatı yoxla ---
    report = client.post(f"/api/meetings/{mid}/end").json()
    assert report["summary"]["headline"]
    assert report["transcript"]
    assert len(report["action_items"]) >= 1
    # Mock kart lokal fayla yazılır
    assert report["card_url"]
    # Mock çatdırılma outbox-a düşür
    assert report["delivered"] is True

    # Hesabat endpoint-i də işləyir
    resp = client.get(f"/api/meetings/{mid}/report")
    assert resp.status_code == 200

    # İclas-sonrası pipeline mərhələsi "done" olmalıdır (frontend stepper üçün)
    st = client.get(f"/api/meetings/{mid}/end-status").json()
    assert st["stage"] == "done"
    assert st["delivered"] is True

    # Yaddaş axtarışı epizodu tapmalıdır
    resp = client.get("/api/memory/search", params={"q": "Sprint planlaması"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["episodes"]) >= 1 or len(data["long_term"]) >= 1


def test_ingest_reports_status_stages(client):
    """Sənəd yüklənəndə mərhələ statusu izlənilməlidir (frontend stepper üçün)."""
    r = client.post("/api/ingest", json={
        "title": "Status testi",
        "content": "Salam. Layihənin son tarixi sentyabrdır. Büdcə təsdiqlənib.",
        "source_type": "text",
    }).json()
    doc_id = r["doc_id"]
    st = client.get(f"/api/ingest/status/{doc_id}").json()
    # PREPARED_QA_ENABLED=false (conftest) → mərhələ dərhal "done"; parçalar yazılıb
    assert st["stage"] in ("saved", "done")
    assert st["chunks"] >= 1


def test_delete_meeting(client):
    """İclas silinməli, canlı iclas isə silinməkdən qorunmalıdır."""
    m = client.post("/api/meetings", json={"topic": "Silinəcək iclas"}).json()
    mid = m["id"]

    # Canlı iclası silmək olmaz
    client.post(f"/api/meetings/{mid}/start")
    assert client.delete(f"/api/meetings/{mid}").status_code == 409

    # Bitmiş iclas silinir və artıq tapılmır
    client.post(f"/api/meetings/{mid}/end")
    assert client.delete(f"/api/meetings/{mid}").status_code == 200
    assert client.get(f"/api/meetings/{mid}").status_code == 404
    assert client.get(f"/api/meetings/{mid}/report").status_code == 404
