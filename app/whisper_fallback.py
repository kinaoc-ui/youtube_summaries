from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .asr_fix import WHISPER_HOTWORDS, WHISPER_INITIAL_PROMPT, fix_asr
from .config import DATA_DIR, ensure_dirs, settings

AUDIO_DIR = DATA_DIR / "audio"


def download_audio(video_id: str) -> Path:
    """Download best audio as wav/m4a via yt-dlp."""
    ensure_dirs()
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(AUDIO_DIR / f"{video_id}.%(ext)s")
    # Prefer m4a/webm; convert to wav if ffmpeg available for whisper
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        from yt_dlp import YoutubeDL
    except ImportError as e:
        raise RuntimeError("yt-dlp not installed. Run: pip install yt-dlp") from e

    opts = {
        "format": "bestaudio/best",
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "96",
            }
        ],
    }
    with YoutubeDL(opts) as ydl:
        ydl.download([url])

    for ext in ("mp3", "m4a", "webm", "opus", "wav"):
        p = AUDIO_DIR / f"{video_id}.{ext}"
        if p.exists():
            return p
    matches = list(AUDIO_DIR.glob(f"{video_id}.*"))
    if matches:
        return matches[0]
    raise RuntimeError(f"Audio download failed for {video_id}")


def transcribe_audio(audio_path: Path, model_size: str | None = None) -> list[dict[str, Any]]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("faster-whisper not installed. Run: pip install faster-whisper") from e

    model_size = model_size or getattr(settings, "whisper_model", "base")
    # CPU int8 is the portable default; CUDA used automatically if available
    device = getattr(settings, "whisper_device", "cpu")
    compute = getattr(settings, "whisper_compute", "int8")
    model = WhisperModel(model_size, device=device, compute_type=compute)
    segments, _info = model.transcribe(
        str(audio_path),
        vad_filter=True,
        language="en",
        beam_size=5,
        best_of=5,
        temperature=0.0,
        condition_on_previous_text=False,
        initial_prompt=WHISPER_INITIAL_PROMPT,
        hotwords=WHISPER_HOTWORDS,
    )
    snippets: list[dict[str, Any]] = []
    for seg in segments:
        text = fix_asr((seg.text or "").strip())
        if not text:
            continue
        start = float(seg.start or 0)
        end = float(seg.end or start)
        snippets.append({"start": start, "duration": max(0.01, end - start), "text": text})
    return snippets


def fetch_via_whisper(
    video_id: str,
    *,
    model_size: str | None = None,
    audio_path: Path | None = None,
) -> list[dict[str, Any]]:
    audio = audio_path or download_audio(video_id)
    model_size = model_size or getattr(settings, "whisper_model", "base")
    snippets = transcribe_audio(audio, model_size=model_size)
    ensure_dirs()
    # Keep legacy .whisper.json + tagged copy for A/B (e.g. .whisper-large-v3-turbo.json)
    legacy = DATA_DIR / "transcripts" / f"{video_id}.whisper.json"
    tagged = DATA_DIR / "transcripts" / f"{video_id}.whisper-{model_size}.json"
    payload = json.dumps(snippets, ensure_ascii=False, indent=2)
    legacy.write_text(payload, encoding="utf-8")
    tagged.write_text(payload, encoding="utf-8")
    return snippets
