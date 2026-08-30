# -*- coding: utf-8 -*-
"""Download video (not just audio) and grab frames to check ASR tickers."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DATA_DIR, ensure_dirs  # noqa: E402
from app.video_check import check_video  # noqa: E402

STATUS_DIR = DATA_DIR / "vision_jobs"


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


def run(video_id: str) -> None:
    write_status(video_id, status="running", step="start")

    def cb(**kw):
        write_status(video_id, **kw)

    try:
        report = check_video(video_id, status_cb=cb)
        write_status(
            video_id,
            status="done",
            step="done",
            frame_count=report.get("frame_count"),
            mismatch_count=report.get("mismatch_count"),
            ocr_engine=report.get("ocr_engine"),
        )
        print(f"OK {video_id}: {report.get('frame_count')} frames, {report.get('mismatch_count')} mismatches")
    except Exception as e:
        write_status(video_id, status="error", error=str(e), traceback=traceback.format_exc())
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("video_id")
    run(p.parse_args().video_id)
