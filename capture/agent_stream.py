"""Azure STREAMING STT capture agenti — canlı (real-vaxt) transkripsiya.

Fərq (köhnə agent.py ilə):
  - agent.py:       20/7/5 saniyəlik parçalar yazıб /segments/audio-a göndərir
                    (server ElevenLabs ilə transkript edir) — gecikmə ~6-10s.
  - agent_stream.py: mikrofon/blackhole səsini FASİLƏSİZ Azure-a axıdır, Azure
                    cümlələri canlı tanıyır (az-AZ) və hazır MƏTNİ /segments/text-ə
                    göndərir — gecikmə ~2-3s. Server STT-yə toxunmur.

Köhnə agent.py fallback kimi qalır (ElevenLabs, texniki terminlərdə daha dəqiq).

Konfiqurasiya (~/Library/Application Support/meeting-assistant/config):
  API=http://localhost:8000
  USERNAME=... / PASSWORD=...
  DEVICE=blackhole,mikrofon
  POLL_SECONDS=5
  AZURE_KEY=...        # yoxdursa layihə .env-dən AZURE_SPEECH_KEY oxunur
  AZURE_REGION=eastus  # yoxdursa .env-dən AZURE_SPEECH_REGION

İşə salma:  .venv/bin/python capture/agent_stream.py
"""
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import httpx

CONFIG_PATH = Path.home() / "Library" / "Application Support" / "meeting-assistant" / "config"
LOG_PATH = Path.home() / "Library" / "Logs" / "meeting-assistant-capture.log"
SAMPLE_RATE = 16000  # Azure push stream default: 16kHz, 16-bit, mono
PUSH_INTERVAL = 0.1  # hər 100ms yığılan səsi Azure-a ötürürük (canlı axın)

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("azure-stream-agent")


def _read_env_file(key: str) -> str:
    """Layihə .env-dən dəyər oxuyur (agent layihə qovluğundan işə salınanda)."""
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    return ""


def load_config() -> dict:
    """KEY=VALUE konfiqurasiyasını oxuyur; Azure açarı üçün .env-ə də baxır."""
    cfg = {
        "API": "http://localhost:8000",
        "USERNAME": "", "PASSWORD": "",
        "DEVICE": "blackhole,mikrofon",
        "POLL_SECONDS": "5",
        "AZURE_KEY": "", "AZURE_REGION": "eastus",
    }
    if CONFIG_PATH.exists():
        for line in CONFIG_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    # Azure açarı konfiqdə yoxdursa layihə .env-dən götür
    if not cfg["AZURE_KEY"]:
        cfg["AZURE_KEY"] = _read_env_file("AZURE_SPEECH_KEY")
    if not cfg.get("AZURE_REGION"):
        cfg["AZURE_REGION"] = _read_env_file("AZURE_SPEECH_REGION") or "eastus"
    return cfg


class StreamingAgent:
    """Serveri izləyir; canlı iclasda Azure ilə real-vaxt transkripsiya edir."""

    def __init__(self, cfg: dict) -> None:
        self.api = cfg["API"].rstrip("/")
        self.username = cfg["USERNAME"]
        self.password = cfg["PASSWORD"]
        self.device_name = cfg["DEVICE"]
        self.poll_seconds = int(cfg["POLL_SECONDS"])
        self.azure_key = cfg["AZURE_KEY"]
        self.azure_region = cfg["AZURE_REGION"]
        self._token: Optional[str] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._capturing: Optional[str] = None
        self._device_warn_at = 0.0

    # --- API köməkçiləri (agent.py ilə eyni) ---

    def _login(self) -> None:
        resp = httpx.post(f"{self.api}/api/auth/token",
                          json={"username": self.username, "password": self.password}, timeout=30)
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        log.info("Serverə daxil olundu (%s)", self.api)

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        if not self._token:
            self._login()
        headers = {"Authorization": f"Bearer {self._token}"}
        resp = httpx.request(method, f"{self.api}{path}", headers=headers, timeout=30, **kw)
        if resp.status_code == 401:
            self._login()
            headers = {"Authorization": f"Bearer {self._token}"}
            resp = httpx.request(method, f"{self.api}{path}", headers=headers, timeout=30, **kw)
        return resp

    def _find_live_meeting(self) -> Optional[dict]:
        resp = self._request("GET", "/api/meetings")
        resp.raise_for_status()
        for m in resp.json():
            if m.get("status") == "live":
                return m
        return None

    def _post_text(self, meeting_id: str, text: str) -> None:
        """Tanınan cümləni pipeline-a göndərir (server STT işlətmir)."""
        try:
            resp = self._request("POST", f"/api/meetings/{meeting_id}/segments/text",
                                 json={"text": text})
            if resp.status_code == 409:
                log.info("İclas artıq canlı deyil — tutma dayandırılır")
                self._stop.set()
            elif resp.status_code >= 400:
                log.warning("Mətn qəbul olunmadı (%s): %s", resp.status_code, text[:60])
        except Exception as exc:  # noqa: BLE001 — şəbəkə xətası dövrü öldürməsin
            log.warning("Mətn göndərilmədi: %s", exc)

    # --- Cihazlar (agent.py ilə eyni) ---

    def _find_devices(self) -> list:
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

    # --- Azure streaming tutma ---

    def _capture_loop(self, meeting_id: str) -> None:
        import azure.cognitiveservices.speech as speechsdk
        import numpy as np
        import sounddevice as sd

        devices = self._find_devices()
        if not devices:
            now = time.time()
            if now - self._device_warn_at > 60:
                log.warning("Heç bir giriş cihazı tapılmadı («%s»)", self.device_name)
                self._device_warn_at = now
            self._capturing = None
            return

        # 1) Azure push stream + tanıyıcı (az-AZ)
        fmt = speechsdk.audio.AudioStreamFormat(samples_per_second=SAMPLE_RATE,
                                                bits_per_sample=16, channels=1)
        push = speechsdk.audio.PushAudioInputStream(stream_format=fmt)
        speech_config = speechsdk.SpeechConfig(subscription=self.azure_key, region=self.azure_region)
        speech_config.speech_recognition_language = "az-AZ"
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=speechsdk.audio.AudioConfig(stream=push),
        )

        def on_recognized(evt):  # noqa: ANN001 — Azure SDK imzası
            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                text = (evt.result.text or "").strip()
                if text:
                    log.info("Transkript: %s", text[:90])
                    self._post_text(meeting_id, text)

        def on_canceled(evt):  # noqa: ANN001
            log.warning("Azure tanıma dayandı: %s", getattr(evt, "error_details", evt))

        recognizer.recognized.connect(on_recognized)
        recognizer.canceled.connect(on_canceled)
        recognizer.start_continuous_recognition()

        # 2) sounddevice cihazlarından fasiləsiz oxu → buferlərə yığ
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
            except Exception as exc:  # noqa: BLE001
                log.warning("Cihaz #%d (%s) açılmadı: %s", idx, name, exc)

        if not streams:
            recognizer.stop_continuous_recognition()
            self._capturing = None
            return

        log.info("Azure streaming başladı: iclas=%s (%d cihaz, az-AZ)", meeting_id, len(streams))

        # 3) Pusher dövrü: hər 100ms cihazları qarışdırıб Azure-a ötür
        try:
            while not self._stop.is_set():
                time.sleep(PUSH_INTERVAL)
                tracks = []
                for idx in list(buffers):
                    chunks, buffers[idx] = buffers[idx], []
                    if chunks:
                        tracks.append(np.concatenate(chunks).astype(np.int32).flatten())
                if not tracks:
                    continue
                n = min(t.shape[0] for t in tracks)
                if n == 0:
                    continue
                mixed32 = np.zeros(n, dtype=np.int32)
                for t_ in tracks:
                    mixed32 += t_[:n]
                mixed = np.clip(mixed32, -32768, 32767).astype(np.int16)
                push.write(mixed.tobytes())
        finally:
            for s in streams:
                try:
                    s.stop(); s.close()
                except Exception:  # noqa: BLE001
                    pass
            try:
                push.close()
                recognizer.stop_continuous_recognition()
            except Exception:  # noqa: BLE001
                pass
        log.info("Azure streaming bitdi: iclas=%s", meeting_id)
        self._capturing = None

    def _start(self, meeting_id: str) -> None:
        self._stop.clear()
        self._capturing = meeting_id
        self._thread = threading.Thread(target=self._capture_loop, args=(meeting_id,), daemon=True)
        self._thread.start()

    def _stop_now(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._capturing = None

    # --- Əsas dövr ---

    def run(self) -> None:
        if not self.azure_key:
            log.error("AZURE_KEY tapılmadı — config faylına və ya layihə .env-ə "
                      "AZURE_SPEECH_KEY əlavə edin.")
            sys.exit(1)
        log.info("Azure streaming agenti başladı: %s (cihaz: %s, region: %s, hər %ds yoxlama)",
                 self.api, self.device_name, self.azure_region, self.poll_seconds)
        while True:
            try:
                live = self._find_live_meeting()
                live_id = live["id"] if live else None
                if live_id and self._capturing is None:
                    log.info("Canlı iclas tapıldı: «%s» — Azure streaming başladılır", live["topic"])
                    self._start(live_id)
                elif live_id is None and self._capturing:
                    log.info("Canlı iclas qalmadı — tutma dayandırılır")
                    self._stop_now()
                elif live_id and self._capturing and live_id != self._capturing:
                    log.info("Yeni canlı iclas: %s — keçid edilir", live_id)
                    self._stop_now()
                    self._start(live_id)
                # Tutma thread-i özü dayanıbsa (409 və s.) reyestri təmizlə
                elif self._capturing and self._stop.is_set():
                    self._stop_now()
            except Exception as exc:  # noqa: BLE001
                log.warning("Server yoxlanışı alınmadı: %s", exc)
            time.sleep(self.poll_seconds)


if __name__ == "__main__":
    StreamingAgent(load_config()).run()
