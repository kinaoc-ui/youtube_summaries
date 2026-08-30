from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi

from .config import TRANSCRIPT_DIR, ensure_dirs, settings

VIDEO_ID_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|live/|embed/|shorts/)|^[a-zA-Z0-9_-]{11}$)([a-zA-Z0-9_-]{11})"
)


class CaptionsDisabledError(RuntimeError):
    """YouTube has no captions for this video — need Whisper/audio fallback."""


def extract_video_id(url_or_id: str) -> str:
    text = url_or_id.strip()
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", text):
        return text
    m = re.search(r"(?:v=|/live/|/embed/|/shorts/|youtu\.be/)([a-zA-Z0-9_-]{11})", text)
    if not m:
        raise ValueError(f"Cannot parse YouTube video id from: {url_or_id}")
    return m.group(1)


def format_ts(seconds: float) -> str:
    sec = max(0, int(seconds))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def fetch_captions(video_id: str, languages: list[str] | None = None) -> list[dict[str, Any]]:
    languages = languages or ["en", "en-US", "en-GB", "zh-Hans", "zh-Hant", "zh", "yue"]
    api = YouTubeTranscriptApi()
    fetched = api.fetch(video_id, languages=languages)
    return [
        {"start": float(s.start), "duration": float(s.duration), "text": s.text.replace("\n", " ").strip()}
        for s in fetched
        if s.text and s.text.strip()
    ]


def fetch_transcript(
    video_id: str,
    languages: list[str] | None = None,
    *,
    allow_whisper: bool | None = None,
) -> list[dict[str, Any]]:
    """Try YouTube captions first; optionally fall back to Whisper audio STT."""
    allow_whisper = settings.whisper_auto if allow_whisper is None else allow_whisper
    try:
        return fetch_captions(video_id, languages=languages)
    except Exception as e:
        name = type(e).__name__
        msg = str(e)
        captions_disabled = (
            "TranscriptsDisabled" in name
            or "Subtitles are disabled" in msg
            or "No transcripts were found" in msg
            or "Could not retrieve a transcript" in msg
        )
        if not captions_disabled:
            raise
        if not allow_whisper:
            raise CaptionsDisabledError(
                f"呢條片關咗字幕（{video_id}），youtube-transcript-api 拎唔到。"
                "需要用 Whisper／Deepgram 轉音訊。設 TUBEON_WHISPER_AUTO=true。"
            ) from e
        provider = (settings.asr_provider or "whisper").lower()
        if provider == "deepgram":
            from .asr_deepgram import fetch_via_deepgram

            return fetch_via_deepgram(video_id)
        if provider == "whisperx":
            from .asr_whisperx import fetch_via_whisperx

            return fetch_via_whisperx(video_id)
        from .whisper_fallback import fetch_via_whisper

        return fetch_via_whisper(video_id)


def chunk_transcript(snippets: list[dict[str, Any]], window_seconds: int = 90) -> list[dict[str, Any]]:
    if not snippets:
        return []
    chunks: list[dict[str, Any]] = []
    cur_start = None
    cur_end = None
    cur_texts: list[str] = []

    for s in snippets:
        if cur_start is None:
            cur_start = s["start"]
            cur_end = s["start"] + s["duration"]
            cur_texts = [s["text"]]
            continue
        if s["start"] - cur_start < window_seconds:
            cur_texts.append(s["text"])
            cur_end = s["start"] + s["duration"]
        else:
            text = " ".join(cur_texts).strip()
            if text:
                chunks.append(
                    {
                        "start": cur_start,
                        "end": cur_end,
                        "t": format_ts(cur_start),
                        "text": text,
                    }
                )
            cur_start = s["start"]
            cur_end = s["start"] + s["duration"]
            cur_texts = [s["text"]]

    if cur_texts and cur_start is not None:
        text = " ".join(cur_texts).strip()
        if text:
            chunks.append(
                {
                    "start": cur_start,
                    "end": cur_end,
                    "t": format_ts(cur_start),
                    "text": text,
                }
            )
    return chunks


def save_transcript(
    video_id: str,
    snippets: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    *,
    source: str = "captions",
) -> Path:
    from .asr_fix import fix_asr

    ensure_dirs()
    fixed_snips = []
    for s in snippets:
        row = dict(s)
        if "text" in row:
            row["text"] = fix_asr(str(row["text"]))
        fixed_snips.append(row)
    fixed_chunks = []
    for c in chunks:
        row = dict(c)
        if "text" in row:
            row["text"] = fix_asr(str(row["text"]))
        fixed_chunks.append(row)
    path = TRANSCRIPT_DIR / f"{video_id}.json"
    path.write_text(
        json.dumps(
            {"video_id": video_id, "source": source, "snippets": fixed_snips, "chunks": fixed_chunks},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def load_transcript(video_id: str) -> dict[str, Any] | None:
    path = TRANSCRIPT_DIR / f"{video_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


_MUSIC_CC = re.compile(r"\[music\]|>>", re.I)


def captions_usable(snippets: list[dict[str, Any]] | None) -> bool:
    """True if YouTube CC has real speech, not just intro music / Heat. Heat."""
    chars = 0
    for s in snippets or []:
        t = _MUSIC_CC.sub(" ", str(s.get("text") or ""))
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) < 16:
            continue
        if t.lower() in {"heat. heat.", "heat.", "heat"}:
            continue
        chars += len(t)
        if chars >= 180:
            return True
    return False


def load_caption_snippets(video_id: str) -> list[dict[str, Any]]:
    """YouTube CC snippets when the cached main transcript is captions with real speech."""
    tr = load_transcript(video_id)
    if not tr:
        return []
    src = str(tr.get("source") or "").lower()
    if src.startswith("whisper") or src.startswith("deepgram"):
        return []
    snips = list(tr.get("snippets") or [])
    if captions_usable(snips):
        return snips
    return []
