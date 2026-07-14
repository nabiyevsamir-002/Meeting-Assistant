"""Uçdan-uca smoke test — real HTTP üzərindən bütün sistemi yoxlayır.

İstifadə:
    .venv/bin/python scripts/smoke_test.py            # serveri özü qaldırır
    .venv/bin/python scripts/smoke_test.py --api http://localhost:8000  # mövcud serverə

Heç bir API açarı tələb etmir — mock provayderlərlə tam dövrü icra edir:
sənəd ingest -> iclas -> seqmentlər (mətn + audio) -> feed -> hesabat -> yaddaş.
"""
import argparse
import io
import os
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path

import httpx

PORT = 8123  # əsas serverlə toqquşmasın deyə ayrıca port

# Uzaq serverdə (AUTH_ENABLED=true) test üçün giriş məlumatları env-dən verilə bilər:
#   SMOKE_USERNAME=... SMOKE_PASSWORD=... python scripts/smoke_test.py --api https://...
SMOKE_USERNAME = os.environ.get("SMOKE_USERNAME", "admin")
SMOKE_PASSWORD = os.environ.get("SMOKE_PASSWORD", "admin123")


def sample_wav() -> bytes:
    """1 saniyəlik sadə sinus tonu olan WAV (mock STT məzmuna baxmır)."""
    import math

    rate = 16000
    frames = [int(12000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(rate)]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(frames)}h", *frames))
    return buf.getvalue()


def wait_for_health(api: str, timeout: float = 30.0) -> dict:
    """Server hazır olana qədər gözləyir."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{api}/health", timeout=2)
            if resp.status_code == 200:
                return resp.json()
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError("Server vaxtında qalxmadı")


def check(label: str, condition: bool) -> bool:
    """Yoxlama nəticəsini çap edir."""
    print(f"  {'✅' if condition else '❌'} {label}")
    return condition


def run_smoke(api: str) -> bool:
    """Bütün mərhələləri ardıcıl yoxlayır; hamısı keçərsə True."""
    ok = True
    health = wait_for_health(api)
    print(f"\n🔍 Server hazırdır. Aktiv provayderlər: {health['providers']}")

    # --- JWT (nümayiş — auth söndürülü olsa da token axını işləyir) ---
    resp = httpx.post(f"{api}/api/auth/token",
                      json={"username": SMOKE_USERNAME, "password": SMOKE_PASSWORD})
    ok &= check("JWT token verilir", resp.status_code == 200)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    # --- Phase 1: ingest (n8n-in göndərdiyi formatda) ---
    print("\n📚 Phase 1 — bilik bazası:")
    resp = httpx.post(f"{api}/api/ingest", headers=headers, json={
        "title": "Layihə brifi",
        "content": "AI Meeting Assistant layihəsinin deadline-ı 30 sentyabrdır. "
                   "Büdcə təsdiqlənib. İnteqrasiya üçün Claude API seçilib. "
                   "Vektor bazası kimi Qdrant istifadə olunacaq. "
                   "Komanda: Samir (backend), Aynur (test).",
        "source_type": "web",
        "url": "https://example.com/brief",
    })
    ok &= check("Sənəd ingest olunur", resp.status_code == 200)
    resp = httpx.get(f"{api}/api/ingest/search", headers=headers,
                     params={"q": "deadline nə vaxtdır"})
    ok &= check("Kontekst axtarışı nəticə tapır", bool(resp.json()))
    resp = httpx.get(f"{api}/api/calendar/upcoming", headers=headers)
    ok &= check("Təqvim yaxın iclası göstərir", bool(resp.json()))

    # --- Phase 2: canlı iclas ---
    print("\n🎙 Phase 2 — canlı iclas:")
    meeting = httpx.post(f"{api}/api/meetings", headers=headers,
                         json={"topic": "Smoke Test İclası"}).json()
    mid = meeting["id"]
    httpx.post(f"{api}/api/meetings/{mid}/start", headers=headers)

    # Mətn seqmentləri
    for text in [
        "Layihənin gedişatını nəzərdən keçiririk, hər şey plan üzrədir.",
        "Samir, layihənin deadline-ı nə vaxtdır?",
        "Samir sənədləri cümə gününə qədər hazırlayacaq, Aynur testləri yazacaq.",
    ]:
        resp = httpx.post(f"{api}/api/meetings/{mid}/segments/text",
                          headers=headers, json={"text": text}, timeout=60)
        assert resp.status_code == 200, resp.text
    ok &= check("Mətn seqmentləri emal olunur", True)

    # Audio seqment (fayl rejimi -> STT -> pipeline)
    resp = httpx.post(
        f"{api}/api/meetings/{mid}/segments/audio", headers=headers,
        files={"file": ("chunk.wav", sample_wav(), "audio/wav")}, timeout=60,
    )
    ok &= check("Audio seqment STT-dən keçir", resp.status_code == 200)

    feed = httpx.get(f"{api}/api/meetings/{mid}/feed", headers=headers).json()
    types = {e["type"] for e in feed}
    ok &= check("Feed-də sual aşkarlanıb", "question" in types)
    ok &= check("Feed-də cavab variantları var", "answer_options" in types)
    answers = [e for e in feed if e["type"] == "answer_options"]
    if answers:
        steps = answers[0]["payload"].get("agent_steps", [])
        ok &= check("ReAct agent search_context alətini çağırıb",
                    any(s.get("tool") == "search_context" for s in steps))

    # --- Phase 3: hesabat ---
    print("\n📋 Phase 3 — iclas-sonrası:")
    report = httpx.post(f"{api}/api/meetings/{mid}/end", headers=headers,
                        timeout=120).json()
    ok &= check("Xülasə hazırlanır", bool(report.get("summary", {}).get("headline")))
    ok &= check("Action item-lər çıxarılır", len(report.get("action_items", [])) >= 1)
    ok &= check("Xülasə kartı yaradılır (mock: HTML fayl)", bool(report.get("card_url")))
    ok &= check("Çatdırılma işləyir (mock: outbox JSON)", report.get("delivered") is True)

    resp = httpx.get(f"{api}/api/memory/search", headers=headers,
                     params={"q": "Smoke Test"})
    data = resp.json()
    ok &= check("Epizodik/uzunmüddətli yaddaş axtarışı",
                bool(data.get("episodes") or data.get("long_term")))

    print(f"\n{'🎉 SMOKE TEST UĞURLA KEÇDİ' if ok else '💥 SMOKE TEST UĞURSUZ OLDU'}")
    if report.get("card_url"):
        print(f"   Kart: {report['card_url']}")
    print(f"   UI:   {api}/ui/index.html")
    return ok


def main() -> None:
    """Serveri (lazımdırsa) qaldırır və smoke testi icra edir."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=None,
                        help="Mövcud serverin ünvanı (verilməsə, özü qaldırır)")
    args = parser.parse_args()

    if args.api:
        sys.exit(0 if run_smoke(args.api) else 1)

    # Serveri subprocess kimi qaldırırıq
    root = Path(__file__).parent.parent
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        success = run_smoke(f"http://127.0.0.1:{PORT}")
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
