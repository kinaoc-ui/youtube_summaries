# -*- coding: utf-8 -*-
"""Background: optional WhisperX + faster-whisper sync + screen compare."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DATA_DIR, ensure_dirs, settings  # noqa: E402
from app.job_progress import JobProgress, audio_duration_sec  # noqa: E402
from app.triple_check import build_full_report  # noqa: E402
from app.whisper_fallback import AUDIO_DIR, download_audio  # noqa: E402

STATUS_DIR = DATA_DIR / "asr_compare_jobs"


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


def _ensure_audio(video_id: str) -> Path:
    for ext in ("mp3", "m4a", "webm", "wav", "opus"):
        p = AUDIO_DIR / f"{video_id}.{ext}"
        if p.exists():
            return p
    return download_audio(video_id)


def run(video_id: str, *, model: str | None = None, run_whisperx: bool = True) -> None:
    model = model or settings.whisper_model or "small"
    if model == "small" and (settings.whisper_device or "").lower().startswith("cuda"):
        model = "large-v3-turbo"

    ensure_dirs()
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    audio = _ensure_audio(video_id)
    audio_sec = audio_duration_sec(audio)
    prog = JobProgress(status_path(video_id), video_id=video_id, audio_sec=audio_sec)
    prog.extra["model"] = model
    prog.set_phase("prepare", lo=0, hi=3, expect_sec=15, detail="準備音訊")
    prog.start()

    try:
        x_path = DATA_DIR / "transcripts" / f"{video_id}.whisperx-{model}.json"
        if run_whisperx and not x_path.exists():

            def on_wx(phase: str, kw: dict) -> None:
                if "audio_sec" in kw and kw["audio_sec"]:
                    prog.audio_sec = float(kw["audio_sec"])
                detail = str(kw.get("detail") or phase)
                expect = kw.get("expect_sec")
                if phase == "whisperx_load":
                    prog.set_phase(phase, lo=3, hi=10, expect_sec=expect or 45, detail=detail)
                elif phase == "whisperx_transcribe":
                    prog.set_phase(
                        phase,
                        lo=10,
                        hi=78,
                        expect_sec=expect or max(90.0, prog.audio_sec * 1.2),
                        detail=detail,
                    )
                elif phase == "whisperx_align":
                    prog.set_phase(
                        phase,
                        lo=78,
                        hi=92,
                        expect_sec=expect or max(40.0, prog.audio_sec * 0.35),
                        detail=detail,
                    )
                elif phase == "whisperx_done":
                    prog.set_phase(phase, lo=92, hi=94, expect_sec=5, detail=detail)

            try:
                from app.asr_whisperx import fetch_via_whisperx

                fetch_via_whisperx(
                    video_id,
                    model_size=model,
                    audio_path=audio,
                    on_progress=on_wx,
                )
            except Exception as e:
                prog.extra["whisperx_error"] = str(e)[:500]
                prog.set_phase("whisperx_skipped", lo=10, hi=12, expect_sec=5, detail=str(e)[:120])

        w_path = DATA_DIR / "transcripts" / f"{video_id}.whisper-{model}.json"
        legacy_w = DATA_DIR / "transcripts" / f"{video_id}.whisper.json"
        if not w_path.exists() and not legacy_w.exists():
            prog.set_phase("faster_whisper", lo=12, hi=70, expect_sec=max(90.0, audio_sec * 0.8), detail="faster-whisper")
            try:
                from app.whisper_fallback import fetch_via_whisper

                fetch_via_whisper(video_id, model_size=model, audio_path=audio)
            except Exception as e:
                prog.extra["whisper_error"] = str(e)[:500]
                prog.set_phase("whisper_skipped", lo=70, hi=72, expect_sec=5, detail=str(e)[:120])

        prog.set_phase("triple_check", lo=94, hi=97, expect_sec=20, detail="語音↔WhisperX↔畫面對比")
        report = build_full_report(video_id, model=model)
        prog.set_phase("reconcile", lo=97, hi=99, expect_sec=15, detail="雙ASR核實＋改摘要")
        from app.summary_reconcile import reconcile_summary_from_compare

        patch = reconcile_summary_from_compare(video_id, report, model=model)
        prog.extra.update(
            {
                "asr_desync": (report.get("summary") or {}).get("asr_desync"),
                "screen_mismatch": (report.get("summary") or {}).get("screen_mismatch"),
                "hint": (patch.get("hint") or (report.get("summary") or {}).get("hint")),
                "report_path": report.get("report_path"),
                "summary_patched": bool(patch.get("changed")),
                "exec_drop": patch.get("drop"),
                "exec_single": patch.get("single_asr"),
                "timing_snapped": patch.get("timing_snapped"),
            }
        )
        prog.set_phase("done", lo=100, hi=100, expect_sec=1, detail="完成（已改摘要）")
        prog.stop(final_pct=100)
        write_status(
            video_id,
            status="done",
            step="done",
            model=model,
            progress_pct=100,
            elapsed_sec=prog.snapshot().get("elapsed_sec"),
            heartbeat_ts=prog.snapshot().get("heartbeat_ts"),
            asr_desync=prog.extra.get("asr_desync"),
            screen_mismatch=prog.extra.get("screen_mismatch"),
            hint=prog.extra.get("hint"),
            report_path=prog.extra.get("report_path"),
            summary_patched=prog.extra.get("summary_patched"),
            exec_drop=prog.extra.get("exec_drop"),
            exec_single=prog.extra.get("exec_single"),
            timing_snapped=prog.extra.get("timing_snapped"),
        )
        print("OK", video_id, report.get("summary"), "patch", patch.get("hint"))
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "push_summaries_git.py"),
                    f"ASR patch {video_id}",
                ],
                cwd=str(ROOT),
                check=False,
            )
        except Exception as push_err:
            print("WARN git push skipped:", push_err)
    except Exception as e:
        prog.extra["error"] = str(e)
        prog.set_phase("error", lo=0, hi=0, expect_sec=1, detail=str(e)[:160])
        prog.stop()
        write_status(video_id, status="error", error=str(e), traceback=traceback.format_exc())
        raise


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("video_id")
    p.add_argument("--model", default=None)
    p.add_argument("--no-whisperx", action="store_true")
    args = p.parse_args()
    run(args.video_id, model=args.model, run_whisperx=not args.no_whisperx)


if __name__ == "__main__":
    main()
