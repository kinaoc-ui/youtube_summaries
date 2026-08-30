"""WhisperX path — faster-whisper + phoneme alignment (word-level timestamps)."""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .asr_fix import fix_asr
from .config import DATA_DIR, ensure_dirs, settings

ProgressCb = Callable[[str, dict[str, Any]], None]


def transcribe_audio_whisperx(
    audio_path: Path,
    *,
    model_size: str | None = None,
    on_progress: ProgressCb | None = None,
) -> list[dict[str, Any]]:
    try:
        import whisperx
    except ImportError as e:
        raise RuntimeError(
            "whisperx not installed. Run: pip install git+https://github.com/m-bain/whisperX.git"
        ) from e

    def prog(phase: str, **kw: Any) -> None:
        if on_progress:
            on_progress(phase, kw)

    model_size = model_size or settings.whisper_model
    device = settings.whisper_device
    compute = settings.whisper_compute
    if device == "cpu" and compute in {"float16", "float32"}:
        compute = "int8"

    prog("whisperx_load", detail="載入音訊")
    audio = whisperx.load_audio(str(audio_path))
    # whisperx loads 16k mono
    audio_sec = float(len(audio) / 16000.0) if hasattr(audio, "__len__") else 0.0
    prog("whisperx_load", detail="載入模型", audio_sec=audio_sec)

    model = whisperx.load_model(model_size, device, compute_type=compute, language="en")
    # CPU whisperx often ~0.8–1.5× realtime for small; align adds more
    rtf = 0.5 if str(device).startswith("cuda") else 1.2
    prog(
        "whisperx_transcribe",
        detail=f"轉寫中（model={model_size}）",
        audio_sec=audio_sec,
        expect_sec=max(60.0, audio_sec * rtf),
    )
    result = model.transcribe(audio, batch_size=8 if device != "cpu" else 4)

    lang = (result.get("language") or "en") if isinstance(result, dict) else "en"
    try:
        prog(
            "whisperx_align",
            detail="字級時間戳對齊",
            audio_sec=audio_sec,
            expect_sec=max(30.0, audio_sec * (0.15 if str(device).startswith("cuda") else 0.35)),
        )
        align_model, metadata = whisperx.load_align_model(language_code=lang, device=device)
        result = whisperx.align(
            result["segments"],
            align_model,
            metadata,
            audio,
            device,
            return_char_alignments=False,
        )
    except Exception:
        prog("whisperx_align", detail="對齊失敗，用未對齊 segments")

    segments = result.get("segments") if isinstance(result, dict) else result
    snippets: list[dict[str, Any]] = []
    for seg in segments or []:
        text = fix_asr((seg.get("text") or "").strip())
        if not text:
            continue
        start = float(seg.get("start") or 0)
        end = float(seg.get("end") or start)
        row: dict[str, Any] = {
            "start": start,
            "duration": max(0.01, end - start),
            "text": text,
        }
        words = seg.get("words") or []
        if words:
            row["words"] = [
                {
                    "word": w.get("word"),
                    "start": w.get("start"),
                    "end": w.get("end"),
                }
                for w in words
                if w.get("word")
            ]
        snippets.append(row)
    prog("whisperx_done", detail=f"完成 {len(snippets)} 段", audio_sec=audio_sec)
    return snippets


def fetch_via_whisperx(
    video_id: str,
    *,
    model_size: str | None = None,
    audio_path: Path | None = None,
    on_progress: ProgressCb | None = None,
) -> list[dict[str, Any]]:
    from .whisper_fallback import download_audio

    ensure_dirs()
    audio = audio_path or download_audio(video_id)
    model_size = model_size or settings.whisper_model
    snippets = transcribe_audio_whisperx(audio, model_size=model_size, on_progress=on_progress)
    tagged = DATA_DIR / "transcripts" / f"{video_id}.whisperx-{model_size}.json"
    legacy = DATA_DIR / "transcripts" / f"{video_id}.whisperx.json"
    payload = json.dumps(snippets, ensure_ascii=False, indent=2)
    tagged.write_text(payload, encoding="utf-8")
    legacy.write_text(payload, encoding="utf-8")
    return snippets
