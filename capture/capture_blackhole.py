"""Mac sistem səsinin BlackHole ilə tutulması və API-yə göndərilməsi.

Quraşdırma (bir dəfəlik, SETUP.md-də ətraflı):
  1. brew install blackhole-2ch
  2. Audio MIDI Setup -> Multi-Output Device yaradın (dinamik + BlackHole)
  3. İclas zamanı sistem çıxışını həmin Multi-Output-a keçirin

İstifadə:
  pip install -r capture/requirements.txt
  python capture/capture_blackhole.py --meeting-id <ID> [--api http://localhost:8000]

Skript sistem səsini CHUNK_SECONDS-luq parçalarla yazır və hər parçanı
WAV kimi /api/meetings/{id}/segments/audio endpointinə POST edir.
"""
import argparse
import io
import sys
import wave

import httpx

# Parça uzunluğu — 15-30 saniyə tövsiyə olunur (STT xərci/gecikmə balansı)
CHUNK_SECONDS = 20
SAMPLE_RATE = 16000  # STT üçün 16kHz mono kifayətdir və trafik az olur


def find_device(name_part: str) -> int:
    """Giriş cihazları arasında adına görə cihaz tapır.

    Standart halda BlackHole axtarılır (yalnız qarşı tərəfin səsi).
    Öz mikrofonunuzu da transkripta salmaq üçün Audio MIDI Setup-da
    Aggregate Device (mikrofon + BlackHole) yaradıb --device ilə verin.
    """
    import sounddevice as sd

    for idx, dev in enumerate(sd.query_devices()):
        if name_part.lower() in dev["name"].lower() and dev["max_input_channels"] > 0:
            return idx
    print(f"XƏTA: «{name_part}» adlı giriş cihazı tapılmadı. Mövcud cihazlar:")
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            print(f"  #{idx}: {dev['name']}")
    print("SETUP.md-dəki quraşdırma addımlarına baxın.")
    sys.exit(1)


def record_chunk(device: int) -> bytes:
    """Bir parça səs yazır və WAV baytları qaytarır."""
    import numpy as np
    import sounddevice as sd

    frames = sd.rec(
        int(CHUNK_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=device,
    )
    sd.wait()  # yazma bitənə qədər gözlə

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(np.asarray(frames).tobytes())
    return buf.getvalue()


def send_chunk(api: str, meeting_id: str, audio: bytes, token: str | None) -> None:
    """Parçanı API-yə göndərir; cavabdakı transkripti çap edir."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = httpx.post(
        f"{api}/api/meetings/{meeting_id}/segments/audio",
        files={"file": ("chunk.wav", audio, "audio/wav")},
        headers=headers,
        timeout=120,
    )
    resp.raise_for_status()
    print(f"  -> transkript: {resp.json()['text'][:100]}")


def main() -> None:
    """Əsas dövr: yaz -> göndər -> təkrar (Ctrl+C ilə dayandırın)."""
    parser = argparse.ArgumentParser(description="BlackHole sistem səsi tutucusu")
    parser.add_argument("--meeting-id", required=True, help="Canlı iclasın ID-si")
    parser.add_argument("--api", default="http://localhost:8000", help="API ünvanı")
    parser.add_argument("--token", default=None, help="JWT token (AUTH_ENABLED=true isə)")
    parser.add_argument("--device", default="blackhole",
                        help="Giriş cihazının adı (öz səsiniz üçün Aggregate Device adını verin)")
    args = parser.parse_args()

    device = find_device(args.device)
    print(f"Cihaz tapıldı (#{device}). {CHUNK_SECONDS}s parçalarla yazılır. Ctrl+C = dayandır.")
    try:
        while True:
            audio = record_chunk(device)
            send_chunk(args.api, args.meeting_id, audio, args.token)
    except KeyboardInterrupt:
        print("\nDayandırıldı.")


if __name__ == "__main__":
    main()
