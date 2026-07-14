"""Fayl rejimi — əvvəlcədən yazılmış WAV faylını parçalayıb API-yə göndərir.

BlackHole quraşdırmadan bütün audio pipeline-ı test etməyə imkan verir:

  python capture/send_file.py --meeting-id <ID> --file iclas.wav

Fayl CHUNK_SECONDS-luq hissələrə bölünür və hər hissə real vaxtdakı kimi
ardıcıl POST edilir. Yalnız stdlib istifadə olunur (wave), əlavə asılılıq yoxdur.
Qeyd: MP3/M4A üçün əvvəlcə WAV-a çevirin: ffmpeg -i iclas.m4a iclas.wav
"""
import argparse
import io
import time
import wave

import httpx

CHUNK_SECONDS = 20


def iter_wav_chunks(path: str):
    """WAV faylını CHUNK_SECONDS-luq WAV parçalarına bölür."""
    with wave.open(path, "rb") as w:
        params = w.getparams()
        frames_per_chunk = int(params.framerate * CHUNK_SECONDS)
        while True:
            frames = w.readframes(frames_per_chunk)
            if not frames:
                break
            buf = io.BytesIO()
            with wave.open(buf, "wb") as out:
                out.setnchannels(params.nchannels)
                out.setsampwidth(params.sampwidth)
                out.setframerate(params.framerate)
                out.writeframes(frames)
            yield buf.getvalue()


def main() -> None:
    """Faylı oxu, parçala, ardıcıl göndər."""
    parser = argparse.ArgumentParser(description="WAV faylını parçalarla API-yə göndər")
    parser.add_argument("--meeting-id", required=True)
    parser.add_argument("--file", required=True, help="WAV faylının yolu")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--token", default=None, help="JWT token (AUTH_ENABLED=true isə)")
    parser.add_argument("--realtime", action="store_true",
                        help="Parçalar arasında real gecikmə saxla (canlı simulyasiya)")
    args = parser.parse_args()

    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    for i, chunk in enumerate(iter_wav_chunks(args.file), start=1):
        resp = httpx.post(
            f"{args.api}/api/meetings/{args.meeting_id}/segments/audio",
            files={"file": (f"chunk{i}.wav", chunk, "audio/wav")},
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()
        print(f"parça {i} -> {resp.json()['text'][:100]}")
        if args.realtime:
            time.sleep(CHUNK_SECONDS)  # canlı iclası simulyasiya et


if __name__ == "__main__":
    main()
