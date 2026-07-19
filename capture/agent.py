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

    def _find_devices(self) -> list:
        """DEVICE konfiqurasiyasındakı (vergüllə ayrılmış) adlara uyğun cihazları tapır.

        Məsələn DEVICE=blackhole,mikrofon → həm sistem səsi (Meet/Zoom),
        həm də otaq mikrofonu paralel dinlənilir və qarışdırılır.
        """
        import sounddevice as sd

        found = []
        names = [n.strip().lower() for n in self.device_name.split(",") if n.strip()]
        devs = sd.query_devices()
        for part in names:
            for idx, dev in enumerate(devs):
                if part in dev["name"].lower() and dev["max_input_channels"] > 0:
                    found.append((idx, dev["name"]))
                    break
        return found

    def _capture_loop(self, meeting_id: str) -> None:
        """Ayrıca thread-də: bütün cihazlardan paralel oxu -> miksə -> göndər."""
        import numpy as np
        import sounddevice as sd

        devices = self._find_devices()
        if not devices:
            now = time.time()
            if now - self._device_warn_at > 60:
                log.warning("Heç bir giriş cihazı tapılmadı («%s»)", self.device_name)
                self._device_warn_at = now
            self._capturing_meeting = None
            return

        # Hər cihaz üçün callback-lı stream — nümunələr buferlərə yığılır
        buffers: dict = {idx: [] for idx, _ in devices}

        def make_cb(idx):
            def cb(indata, frames, t, status):  # noqa: ANN001 — sounddevice imzası
                buffers[idx].append(indata.copy())
            return cb

        streams = []
        for idx, name in devices:
            try:
                s = sd.InputStream(device=idx, channels=1, samplerate=SAMPLE_RATE,
                                   dtype="int16", callback=make_cb(idx))
                s.start()
                streams.append(s)
                log.info("Dinlənilir: #%d %s", idx, name)
            except Exception as exc:  # noqa: BLE001 — bir cihaz açılmasa, digəri işləsin
                log.warning("Cihaz #%d (%s) açılmadı: %s", idx, name, exc)

        if not streams:
            self._capturing_meeting = None
            return

        log.info("Səs tutma başladı: iclas=%s (%d cihaz)", meeting_id, len(streams))
        seq = 0
        try:
            while not self._stop_capture.is_set():
                # stop siqnalını gecikmədən tutmaq üçün kiçik addımlarla gözləyirik
                waited = 0.0
                while waited < self.chunk_seconds and not self._stop_capture.is_set():
                    time.sleep(0.25)
                    waited += 0.25
                if self._stop_capture.is_set():
                    break

                try:
                    # Yığılan nümunələri götürüb cihazları bir kanala qarışdırırıq
                    tracks = []
                    for idx in list(buffers):
                        chunks, buffers[idx] = buffers[idx], []
                        if chunks:
                            tracks.append(np.concatenate(chunks).astype(np.int32).flatten())
                    if not tracks:
                        continue
                    n = min(t.shape[0] for t in tracks)
                    mixed32 = np.zeros(n, dtype=np.int32)
                    for t_ in tracks:
                        mixed32 += t_[:n]
                    mixed = np.clip(mixed32, -32768, 32767).astype(np.int16)

                    # Sükut yoxlaması: tam sakit parçalar STT-yə göndərilmir
                    rms = float(np.sqrt(np.mean(mixed.astype("float64") ** 2)))
                    if rms < 60:
                        log.info("Sükut (RMS=%d) — parça ötürüldü", int(rms))
                        continue

                    buf = io.BytesIO()
                    with wave.open(buf, "wb") as w:
                        w.setnchannels(1)
                        w.setsampwidth(2)
                        w.setframerate(SAMPLE_RATE)
                        w.writeframes(mixed.tobytes())

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
        finally:
            for s in streams:
                try:
                    s.stop()
                    s.close()
                except Exception:  # noqa: BLE001
                    pass
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
