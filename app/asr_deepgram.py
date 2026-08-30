"""Deepgram Nova transcription with ticker keyterms."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .asr_fix import WHISPER_HOTWORDS, fix_asr
from .config import DATA_DIR, ensure_dirs, settings


def _ticker_keyterms() -> list[str]:
    # Nova-3 keyterm: boost domain words (tickers + company names)
    terms = []
    for tok in WHISPER_HOTWORDS.split():
        t = tok.strip()
        if t and t not in terms:
            terms.append(t)
    extras = [
        "Figma",
        "JFrog",
        "SpaceX",
        "CoreWeave",
        "Sandisk",
        "CrowdStrike",
        "Datadog",
        "UiPath",
        "Robinhood",
        "Twilio",
        "Okta",
        "Fortinet",
        "Palo Alto",
        "Semtech",
        "Bloom Energy",
    ]
    for e in extras:
        if e not in terms:
            terms.append(e)
    return terms[:100]  # API soft cap


def _api_key() -> str:
    key = (settings.deepgram_api_key or "").strip()
    if key:
        return key
    import os

    return (os.environ.get("DEEPGRAM_API_KEY") or "").strip()


def transcribe_audio_deepgram(audio_path: Path, *, model: str | None = None) -> list[dict[str, Any]]:
    try:
        from deepgram import DeepgramClient
    except ImportError as e:
        raise RuntimeError("deepgram-sdk not installed. Run: pip install deepgram-sdk") from e

    api_key = _api_key()
    if not api_key:
        raise RuntimeError(
            "Deepgram API key missing. Set TUBEON_DEEPGRAM_API_KEY or DEEPGRAM_API_KEY in .env"
        )

    model = model or settings.deepgram_model
    client = DeepgramClient(api_key=api_key)
    audio_bytes = audio_path.read_bytes()
    keyterms = _ticker_keyterms()

    # nova-3 prefers keyterm; keywords still accepted on older models
    kwargs: dict[str, Any] = {
        "request": audio_bytes,
        "model": model,
        "smart_format": True,
        "punctuate": True,
        "utterances": True,
        "language": "en",
    }
    try:
        response = client.listen.v1.media.transcribe_file(**kwargs, keyterm=keyterms)
    except TypeError:
        # SDK / model may not accept keyterm — retry with keywords
        try:
            response = client.listen.v1.media.transcribe_file(
                **kwargs, keywords=[f"{t}:1.5" for t in keyterms[:50]]
            )
        except TypeError:
            response = client.listen.v1.media.transcribe_file(**kwargs)

    return _response_to_snippets(response)


def _response_to_snippets(response: Any) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []

    # Prefer utterances (natural speech chunks with timestamps)
    utterances = None
    try:
        utterances = response.results.utterances
    except Exception:
        utterances = None
    if utterances:
        for u in utterances:
            text = fix_asr((getattr(u, "transcript", None) or "").strip())
            if not text:
                continue
            start = float(getattr(u, "start", 0) or 0)
            end = float(getattr(u, "end", start) or start)
            snippets.append(
                {"start": start, "duration": max(0.01, end - start), "text": text}
            )
        if snippets:
            return snippets

    # Fallback: words → pack into ~8s groups
    words = None
    try:
        words = response.results.channels[0].alternatives[0].words
    except Exception:
        words = None
    if words:
        buf: list[str] = []
        seg_start: float | None = None
        last_end = 0.0
        for w in words:
            wt = (getattr(w, "punctuated_word", None) or getattr(w, "word", "") or "").strip()
            ws = float(getattr(w, "start", 0) or 0)
            we = float(getattr(w, "end", ws) or ws)
            if seg_start is None:
                seg_start = ws
            buf.append(wt)
            last_end = we
            if we - seg_start >= 8.0 or wt.endswith((".", "?", "!")):
                text = fix_asr(" ".join(buf).strip())
                if text:
                    snippets.append(
                        {
                            "start": seg_start,
                            "duration": max(0.01, last_end - seg_start),
                            "text": text,
                        }
                    )
                buf = []
                seg_start = None
        if buf and seg_start is not None:
            text = fix_asr(" ".join(buf).strip())
            if text:
                snippets.append(
                    {
                        "start": seg_start,
                        "duration": max(0.01, last_end - seg_start),
                        "text": text,
                    }
                )
        if snippets:
            return snippets

    # Last resort: whole transcript
    try:
        full = response.results.channels[0].alternatives[0].transcript or ""
    except Exception:
        full = ""
    full = fix_asr(full.strip())
    if full:
        snippets.append({"start": 0.0, "duration": 1.0, "text": full})
    return snippets


def fetch_via_deepgram(video_id: str, *, audio_path: Path | None = None) -> list[dict[str, Any]]:
    from .whisper_fallback import download_audio

    ensure_dirs()
    audio = audio_path or download_audio(video_id)
    snippets = transcribe_audio_deepgram(audio)
    cache = DATA_DIR / "transcripts" / f"{video_id}.deepgram.json"
    cache.write_text(json.dumps(snippets, ensure_ascii=False, indent=2), encoding="utf-8")
    return snippets
