# -*- coding: utf-8 -*-
"""Background ASR for caption-disabled videos (Whisper and/or Deepgram)."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DATA_DIR, ensure_dirs, settings  # noqa: E402
from app.transcript import chunk_transcript, save_transcript  # noqa: E402

STATUS_DIR = DATA_DIR / "whisper_jobs"


def status_path(video_id: str) -> Path:
    return STATUS_DIR / f"{video_id}.json"


def write_status(video_id: str, **kwargs) -> None:
    ensure_dirs()
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    path = status_path(video_id)
    cur = {}
    if path.exists():
        try:
            cur = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cur = {}
    cur.update(kwargs)
    cur["video_id"] = video_id
    path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")


def run(video_id: str, *, provider: str | None = None, whisper_model: str | None = None) -> None:
    provider = (provider or settings.asr_provider or "whisper").lower()
    model = whisper_model or settings.whisper_model
    write_status(
        video_id,
        status="running",
        step="download+transcribe",
        provider=provider,
        model=model if provider == "whisper" else settings.deepgram_model,
    )
    try:
        if provider == "deepgram":
            from app.asr_deepgram import fetch_via_deepgram

            snippets = fetch_via_deepgram(video_id)
            source = "deepgram"
        elif provider == "whisperx":
            from app.asr_whisperx import fetch_via_whisperx

            snippets = fetch_via_whisperx(video_id, model_size=model)
            source = f"whisperx-{model}"
        else:
            from app.whisper_fallback import fetch_via_whisper

            snippets = fetch_via_whisper(video_id, model_size=model)
            source = f"whisper-{model}"
        chunks = chunk_transcript(snippets, settings.chunk_seconds)
        save_transcript(video_id, snippets, chunks, source=source)
        write_status(
            video_id,
            status="done",
            step="done",
            provider=provider,
            snippet_count=len(snippets),
            chunk_count=len(chunks),
        )
        print(f"OK {video_id}: provider={provider} {len(snippets)} snippets, {len(chunks)} chunks")
    except Exception as e:
        write_status(video_id, status="error", error=str(e), traceback=traceback.format_exc())
        raise


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("video_id")
    p.add_argument("--provider", choices=["whisper", "whisperx", "deepgram"], default=None)
    p.add_argument("--whisper-model", default=None)
    args = p.parse_args()
    run(args.video_id, provider=args.provider, whisper_model=args.whisper_model)


if __name__ == "__main__":
    main()
