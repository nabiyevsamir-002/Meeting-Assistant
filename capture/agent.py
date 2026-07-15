"""Capture agenti — iclas başlayanda səs tutmağı AVTOMATİK başladır.

Necə işləyir:
  1. Mac açılanda LaunchAgent bu skripti arxa planda işə salır
  2. Agent hər POLL_SECONDS saniyədə serverdən iclas siyahısını alır
  3. "live" statuslu iclas görünən kimi BlackHole-dan səs tutmağa başlayır
  4. İclas bitəndə (status dəyişəndə) tutma avtomatik dayanır

Konfiqurasiya faylı: ~/Library/Application Support/meeting-assistant/config
  API=https://api.visualkey.az
  USERNAME=samir
  PASSWORD=...
  DEVICE=blackhole          # öz səsiniz üçün Aggregate Device adı yazın
  POLL_SECONDS=5
  CHUNK_SECONDS=20

Quraşdırma: bash capture/install_agent.sh   (bir dəfəlik)
Loglar:     ~/Library/Logs/meeting-assistant-capture.log
"""
import io
import logging
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Optional

import httpx

CONFIG_PATH = Path.home() / "Library" / "Application Support" / "meeting-assistant" / "config"
LOG_PATH = Path.home() / "Library" / "Logs" / "meeting-assistant-capture.log"

SAMPLE_RATE = 16000  # STT üçün 16kHz mono kifayətdir

# --- Loglama: həm fayla, həm stdout-a ---
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("capture-agent")


def load_config() -> dict:
    """KEY=VALUE formatlı sadə konfiqurasiya faylını oxuyur."""
    cfg = {
        "API": "https://api.visualkey.az",
        "USERNAME": "",
        "PASSWORD": "",
        "DEVICE": "blackhole",
        "POLL_SECONDS": "5",
        "CHUNK_SECONDS": "20",
    }
    if not CONFIG_PATH.exists():
        log.error("Konfiqurasiya tapılmadı: %s — install_agent.sh işə salın", CONFIG_PATH)
        sys.exit(1)
    for line in CONFIG_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            cfg[key.strip()] = value.strip()
    return cfg


class CaptureAgent:
    """Serveri izləyib canlı iclas üçün səs tutmağı idarə edir."""

    def __init__(self, cfg: dict) -> None:
        self.api = cfg["API"].rstrip("/")
        self.username = cfg["USERNAME"]
        self.password = cfg["PASSWORD"]
        self.device_name = cfg["DEVICE"]
        self.poll_seconds = int(cfg["POLL_SECONDS"])
        self.chunk_seconds = int(cfg["CHUNK_SECONDS"])
        self._token: Optional[str] = None
        self._stop_capture = threading.Event()
        self._capture_thread: Optional[threading.Thread] = None
        self._capturing_meeting: Optional[str] = None
        # Cihaz tapılmayanda log spamının qarşısını alan cooldown
        self._device_warn_at = 0.0

    # --- API köməkçiləri ---

    def _login(self) -> None:
        """JWT alır; agent uzun işlədiyi üçün vaxtı bitəndə yenidən çağırılır."""
        resp = httpx.post(
            f"{self.api}/api/auth/token",
            json={"username": self.username, "password": self.password},
            timeout=30,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        log.info("Serverə daxil olundu (%s)", self.api)

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        """401 alanda avtomatik yenidən login edən sorğu."""
        if not self._token:
            self._login()
        headers = {"Authorization": f"Bearer {self._token}"}
        resp = httpx.request(method, f"{self.api}{path}", headers=headers, timeout=120, **kw)
        if resp.status_code == 401:
            self._login()
            headers = {"Authorization": f"Bearer {self._token}"}
            resp = httpx.request(method, f"{self.api}{path}", headers=headers, timeout=120, **kw)
        return resp

    def _find_live_meeting(self) -> Optional[dict]:
        """Canlı statuslu iclası qaytarır (ən yenisini)."""
        resp = self._request("GET", "/api/meetings")
        resp.raise_for_status()
        for m in resp.json():  # siyahı onsuz da yenidən köhnəyə sıralıdır
            if m.get("status") == "live":
                return m
        return None

    # --- Səs tutma ---

    def _find_device(self) -> Optional[int]:
        """Giriş cihazını adına görə axtarır; tapılmasa None."""
        import sounddevice as sd

        for idx, dev in enumerate(sd.query_devices()):
            if self.device_name.lower() in dev["name"].lower() and dev["max_input_channels"] > 0:
                return idx
        return None

    def _capture_loop(self, meeting_id: str) -> None:
        """Ayrıca thread-də: parça yaz -> göndər -> təkrar (stop olunana qədər)."""
        import numpy as np
        import sounddevice as sd

        device = self._find_device()
        if device is None:
            # Cihaz yoxdursa (məs. BlackHole qurulmayıb) — xəbərdarlıq edib çıxırıq;
            # əsas dövr 60 saniyədən bir yenidən cəhd edəcək
            now = time.time()
            if now - self._device_warn_at > 60:
                log.warning("«%s» giriş cihazı tapılmadı — BlackHole quraşdırılıbmı?",
                            self.device_name)
                self._device_warn_at = now
            self._capturing_meeting = None
            return

        log.info("Səs tutma başladı: iclas=%s, cihaz #%d", meeting_id, device)
        seq = 0
        while not self._stop_capture.is_set():
            try:
                frames = sd.rec(
                    int(self.chunk_seconds * SAMPLE_RATE),
                    samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=device,
                )
                # stop siqnalını gecikmədən tutmaq üçün kiçik addımlarla gözləyirik
                waited = 0.0
                while waited < self.chunk_seconds and not self._stop_capture.is_set():
                    time.sleep(0.25)
                    waited += 0.25
                sd.stop()
                if self._stop_capture.is_set():
                    break

                buf = io.BytesIO()
                with wave.open(buf, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(SAMPLE_RATE)
                    w.writeframes(np.asarray(frames).tobytes())

                seq += 1
                resp = self._request(
                    "POST", f"/api/meetings/{meeting_id}/segments/audio",
                    files={"file": (f"chunk{seq}.wav", buf.getvalue(), "audio/wav")},
                )
                if resp.status_code == 409:
                    log.info("İclas artıq canlı deyil — tutma dayandırılır")
                    break
                resp.raise_for_status()
                text = resp.json().get("text", "")
                if text.strip():
                    log.info("Transkript #%d: %s", seq, text[:80])
            except Exception as exc:  # noqa: BLE001 — şəbəkə xətası dövrü öldürməsin
                log.warning("Parça göndərilmədi (%s) — 5s sonra davam", exc)
                time.sleep(5)
        log.info("Səs tutma bitdi: iclas=%s (%d parça)", meeting_id, seq)
        self._capturing_meeting = None

    def _start_capture(self, meeting_id: str) -> None:
        """Tutma thread-ini işə salır."""
        self._stop_capture.clear()
        self._capturing_meeting = meeting_id
        self._capture_thread = threading.Thread(
            target=self._capture_loop, args=(meeting_id,), daemon=True
        )
        self._capture_thread.start()

    def _stop_capture_now(self) -> None:
        """Tutma thread-ini dayandırır."""
        self._stop_capture.set()
        if self._capture_thread:
            self._capture_thread.join(timeout=10)
        self._capturing_meeting = None

    # --- Əsas dövr ---

    def run(self) -> None:
        """Sonsuz izləmə dövrü: canlı iclas var -> tut, yoxdur -> dayandır."""
        log.info("Capture agenti başladı: %s (cihaz: %s, hər %ds yoxlama)",
                 self.api, self.device_name, self.poll_seconds)
        while True:
            try:
                live = self._find_live_meeting()
                live_id = live["id"] if live else None

                if live_id and self._capturing_meeting is None:
                    log.info("Canlı iclas tapıldı: «%s» — tutma başladılır", live["topic"])
                    self._start_capture(live_id)
                elif live_id is None and self._capturing_meeting:
                    log.info("Canlı iclas qalmadı — tutma dayandırılır")
                    self._stop_capture_now()
                elif live_id and self._capturing_meeting and live_id != self._capturing_meeting:
                    # Başqa iclas canlı olub — köhnəni dayandırıb yenisinə keçirik
                    log.info("Yeni canlı iclas: %s — keçid edilir", live_id)
                    self._stop_capture_now()
                    self._start_capture(live_id)
            except Exception as exc:  # noqa: BLE001 — server əlçatmazdırsa səbrlə gözlə
                log.warning("Server yoxlanışı alınmadı: %s", exc)
            time.sleep(self.poll_seconds)


if __name__ == "__main__":
    CaptureAgent(load_config()).run()
