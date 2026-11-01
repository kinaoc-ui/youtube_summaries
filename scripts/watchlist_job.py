# -*- coding: utf-8 -*-
"""Sample last ~10 minutes of a VOD, OCR Martin's on-screen list, export TradingView TXT.

Usage:
  python scripts/watchlist_job.py E5h9Cam51OU
  python scripts/watchlist_job.py E5h9Cam51OU --last-minutes 12 --interval 15
  python scripts/watchlist_job.py E5h9Cam51OU --force
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
from app.watchlist_extract import extract_watchlist  # noqa: E402

STATUS_DIR = DATA_DIR / "watchlist_jobs"


def status_path(video_id: str) -> Path:
    return STATUS_DIR / f"{video_id}.json"


def write_status(video_id: str, **kwargs) -> None:
    ensure_dirs()
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    path = status_path(video_id)
    cur: dict = {}
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
    last_minutes: float = 10.0,
    interval_sec: float = 20.0,
    min_hits: int = 2,
    force: bool = False,
) -> None:
    write_status(
        video_id,
        status="running",
        step="start",
        last_minutes=last_minutes,
        interval_sec=interval_sec,
    )

    def cb(**kw):
        write_status(video_id, **kw)

    try:
        report = extract_watchlist(
            video_id,
            last_minutes=last_minutes,
            interval_sec=interval_sec,
            min_hits=min_hits,
            status_cb=cb,
            force=force,
        )
        write_status(
            video_id,
            status="done",
            step="done",
            frame_count=report.get("frame_count"),
            symbol_count=report.get("symbol_count"),
            ocr_engine=report.get("ocr_engine"),
            symbols=report.get("symbols") or [],
            tradingview_txt=(report.get("paths") or {}).get("tradingview_txt"),
        )
        print(
            f"OK {video_id}: {report.get('symbol_count')} symbols from "
            f"{report.get('frame_count')} frames → "
            f"{(report.get('paths') or {}).get('tradingview_txt')}"
        )
        for sym in (report.get("symbols") or [])[:40]:
            print(f"  {sym}")
    except Exception as e:
        write_status(video_id, status="error", error=str(e), traceback=traceback.format_exc())
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="OCR Martin on-screen watchlist from VOD tail")
    p.add_argument("video_id")
    p.add_argument("--last-minutes", type=float, default=10.0)
    p.add_argument("--interval", type=float, default=20.0, help="Seconds between frames")
    p.add_argument("--min-hits", type=int, default=2, help="Min OCR hits for unknown tickers")
    p.add_argument("--force", action="store_true", help="Re-extract frames even if cached")
    args = p.parse_args()
    run(
        args.video_id,
        last_minutes=args.last_minutes,
        interval_sec=args.interval,
        min_hits=args.min_hits,
        force=args.force,
    )
