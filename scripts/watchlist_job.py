# -*- coding: utf-8 -*-
"""OCR Martin's on-screen Leader/screener table → TradingView Upload-list TXT.

Default mode ``screener`` samples the whole VOD (not only last 10 minutes),
densifies around speech/summary hints, uses RapidOCR boxes to read the Symbol
column, and ignores detail-panel-only frames as the list source.

Usage (from repo root — Windows checkout example):
  cd /d "C:\\Users\\kinao\\OneDrive\\桌面\\stock\\youtube"
  python scripts\\watchlist_job.py iMBI3ZcQ6sU --mode screener --force

  python scripts/watchlist_job.py iMBI3ZcQ6sU
  python scripts/watchlist_job.py iMBI3ZcQ6sU --mode tail --last-minutes 12
  python scripts/watchlist_job.py iMBI3ZcQ6sU --force

Optional if YouTube bot-checks:
  set TUBEON_YT_COOKIES=C:\\path\\to\\cookies.txt
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
    mode: str = "screener",
    last_minutes: float = 10.0,
    interval_sec: float = 20.0,
    coarse_interval: float = 45.0,
    dense_interval: float = 12.0,
    max_frames: int = 90,
    min_hits: int = 2,
    force: bool = False,
) -> None:
    write_status(
        video_id,
        status="running",
        step="start",
        mode=mode,
        last_minutes=last_minutes,
        interval_sec=interval_sec,
    )

    def cb(**kw):
        write_status(video_id, **kw)

    try:
        report = extract_watchlist(
            video_id,
            mode=mode,
            last_minutes=last_minutes,
            interval_sec=interval_sec,
            coarse_interval=coarse_interval,
            dense_interval=dense_interval,
            max_frames=max_frames,
            min_hits=min_hits,
            status_cb=cb,
            force=force,
        )
        write_status(
            video_id,
            status="done",
            step="done",
            mode=mode,
            frame_count=report.get("frame_count"),
            table_frame_count=report.get("table_frame_count"),
            symbol_count=report.get("symbol_count"),
            ocr_engine=report.get("ocr_engine"),
            symbols=report.get("symbols") or [],
            tradingview_txt=(report.get("paths") or {}).get("tradingview_txt"),
        )
        print(
            f"OK {video_id} [{mode}]: {report.get('symbol_count')} symbols from "
            f"{report.get('frame_count')} frames "
            f"(table_frames={report.get('table_frame_count')}) → "
            f"{(report.get('paths') or {}).get('tradingview_txt')}"
        )
        for sym in (report.get("symbols") or [])[:60]:
            print(f"  {sym}")
        if not (report.get("symbols") or []):
            print("WARN: no symbols — check best_frame OCR in watchlist.json")
            bf = report.get("best_frame") or {}
            print(f"  best_frame={bf.get('t')} layout={bf.get('layout')} score={bf.get('score')}")
    except Exception as e:
        write_status(video_id, status="error", error=str(e), traceback=traceback.format_exc())
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="OCR Martin on-screen Leader/screener → TradingView .txt"
    )
    p.add_argument("video_id")
    p.add_argument(
        "--mode",
        choices=["screener", "tail", "auto"],
        default="screener",
        help="screener=whole VOD + Symbol column (default); tail=legacy last-N-min right crop",
    )
    p.add_argument("--last-minutes", type=float, default=10.0, help="Tail densify window")
    p.add_argument("--interval", type=float, default=20.0, help="Tail-mode interval seconds")
    p.add_argument("--coarse-interval", type=float, default=45.0, help="Screener coarse grid")
    p.add_argument("--dense-interval", type=float, default=12.0, help="Screener densify step")
    p.add_argument("--max-frames", type=int, default=90)
    p.add_argument("--min-hits", type=int, default=2, help="Min table hits for unknown tickers")
    p.add_argument("--force", action="store_true", help="Re-extract frames even if cached")
    args = p.parse_args()
    run(
        args.video_id,
        mode=args.mode,
        last_minutes=args.last_minutes,
        interval_sec=args.interval,
        coarse_interval=args.coarse_interval,
        dense_interval=args.dense_interval,
        max_frames=args.max_frames,
        min_hits=args.min_hits,
        force=args.force,
    )
