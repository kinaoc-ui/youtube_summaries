# -*- coding: utf-8 -*-
"""Download video (not just audio) and grab frames to check ASR tickers.

Optional: also OCR the last ~10 minutes for Martin's on-screen watchlist
and write a TradingView Upload-list .txt (see scripts/watchlist_job.py).
"""
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


def run(
    video_id: str,
    *,
    with_watchlist: bool = False,
    last_minutes: float = 10.0,
    interval_sec: float = 20.0,
    watchlist_mode: str = "screener",
) -> None:
    write_status(video_id, status="running", step="start")

    def cb(**kw):
        write_status(video_id, **kw)

    try:
        report = check_video(video_id, status_cb=cb)
        wl_meta: dict = {}
        if with_watchlist:
            from app.watchlist_extract import extract_watchlist

            write_status(video_id, step="watchlist_tail", status="running")
            wl = extract_watchlist(
                video_id,
                mode=watchlist_mode,
                last_minutes=last_minutes,
                interval_sec=interval_sec,
                status_cb=cb,
            )
            wl_meta = {
                "watchlist_symbols": wl.get("symbol_count"),
                "watchlist_txt": (wl.get("paths") or {}).get("tradingview_txt"),
            }
            print(
                f"watchlist {video_id}: {wl.get('symbol_count')} symbols → "
                f"{wl_meta.get('watchlist_txt')}"
            )
        write_status(
            video_id,
            status="done",
            step="done",
            frame_count=report.get("frame_count"),
            mismatch_count=report.get("mismatch_count"),
            ocr_engine=report.get("ocr_engine"),
            **wl_meta,
        )
        print(f"OK {video_id}: {report.get('frame_count')} frames, {report.get('mismatch_count')} mismatches")
    except Exception as e:
        write_status(video_id, status="error", error=str(e), traceback=traceback.format_exc())
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("video_id")
    p.add_argument(
        "--watchlist",
        action="store_true",
        help="Also OCR on-screen Leader/screener → TradingView .txt",
    )
    p.add_argument(
        "--watchlist-mode",
        choices=["screener", "tail", "auto"],
        default="screener",
    )
    p.add_argument("--last-minutes", type=float, default=10.0)
    p.add_argument("--interval", type=float, default=20.0)
    args = p.parse_args()
    run(
        args.video_id,
        with_watchlist=args.watchlist,
        last_minutes=args.last_minutes,
        interval_sec=args.interval,
        watchlist_mode=args.watchlist_mode,
    )
