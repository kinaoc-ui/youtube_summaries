# -*- coding: utf-8 -*-
"""Extract Martin's E_Main right-sidebar watchlist → TradingView Upload .txt.

Default mode ``auto`` / ``sidebar`` prefers the chart right watchlist
(INDEXES/LONGS/SHORTS/FOCUS/TRACKING). Potent/Leader screener is optional
secondary (``--mode screener``) and must not overwrite E_Main as the default.

Usage (from repo root — Windows checkout example):
  cd /d "C:\\Users\\kinao\\OneDrive\\桌面\\stock\\youtube"
  set TUBEON_OPENAI_API_KEY=sk-...
  python scripts\\watchlist_job.py iMBI3ZcQ6sU --mode auto --force --vision
  python scripts\\watchlist_job.py iMBI3ZcQ6sU --upload-date 20261028

Optional Potent secondary:
  python scripts/watchlist_job.py iMBI3ZcQ6sU --mode screener

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
from app.tv_cdp_upload import maybe_upload_after_extract, tv_upload_enabled  # noqa: E402
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
    mode: str = "auto",
    last_minutes: float = 8.0,
    interval_sec: float = 45.0,
    coarse_interval: float = 45.0,
    dense_interval: float = 12.0,
    max_frames: int = 3,
    min_hits: int = 2,
    use_vision: bool | None = None,
    vision_frames: int = 3,
    upload_date: str | None = None,
    force: bool = False,
) -> None:
    write_status(
        video_id,
        status="running",
        step="start",
        mode=mode,
        last_minutes=last_minutes,
        interval_sec=interval_sec,
        upload_date=upload_date,
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
            use_vision=use_vision,
            vision_frames=vision_frames,
            upload_date=upload_date,
            status_cb=cb,
            force=force,
        )
        buckets = report.get("buckets") or {}
        paths = report.get("paths") or {}
        # Prefer dated Martin_Luk_YYYY-MM-DD_E_Main.txt for CDP listStem
        tv_txt_path = (
            paths.get("tradingview_txt_dated")
            or paths.get("tradingview_txt")
        )
        tv_upload: dict = {"skipped": True, "reason": "not attempted"}
        _syms = [s for s in (report.get("symbols") or []) if str(s).strip()]
        _bn = sum(len(v or []) for v in (report.get("buckets") or {}).values())
        if tv_txt_path and (_syms or _bn >= 3):
            if tv_upload_enabled():
                write_status(video_id, step="tv_cdp_upload", status="running")
                print(f"TV CDP upload → {tv_txt_path}")
                tv_upload = maybe_upload_after_extract(tv_txt_path)
            else:
                tv_upload = {
                    "ok": False,
                    "skipped": True,
                    "reason": "TUBEON_TV_UPLOAD not enabled",
                    "txt": tv_txt_path,
                    "listStem": Path(str(tv_txt_path)).stem,
                }

        write_status(
            video_id,
            status="done",
            step="done",
            mode=mode,
            vod_date=report.get("vod_date"),
            list_name=report.get("list_name"),
            symbol_source=report.get("symbol_source"),
            frame_count=report.get("frame_count"),
            sidebar_frame_count=report.get("sidebar_frame_count"),
            symbol_count=report.get("symbol_count"),
            indexes=len(buckets.get("INDEXES") or []),
            longs=len(buckets.get("LONGS") or []),
            shorts=len(buckets.get("SHORTS") or []),
            focus=len(buckets.get("FOCUS") or []),
            tracking=len(buckets.get("TRACKING") or []),
            ocr_engine=report.get("ocr_engine"),
            symbols=report.get("symbols") or [],
            buckets=buckets,
            vision_symbols=((report.get("vision") or {}).get("symbols") or []),
            tradingview_txt=tv_txt_path,
            tv_upload_ok=bool(tv_upload.get("ok")),
            tv_upload=tv_upload,
            listStem=tv_upload.get("listStem") or paths.get("list_stem"),
        )
        print(
            f"OK {video_id} [{mode}/{report.get('symbol_source')}] "
            f"name={report.get('list_name')}: "
            f"INDEXES={len(buckets.get('INDEXES') or [])} "
            f"LONGS={len(buckets.get('LONGS') or [])} "
            f"SHORTS={len(buckets.get('SHORTS') or [])} "
            f"FOCUS={len(buckets.get('FOCUS') or [])} "
            f"TRACKING={len(buckets.get('TRACKING') or [])} "
            f"→ {tv_txt_path}"
        )
        if tv_upload.get("skipped"):
            if tv_upload_enabled():
                print(f"TV UPLOAD skipped: {tv_upload.get('reason')}")
        elif tv_upload.get("ok"):
            print(
                f"TV UPLOAD ok listStem={tv_upload.get('listStem')} "
                f"importResult={tv_upload.get('importResult')}"
            )
        else:
            print(
                f"TV UPLOAD failed: {tv_upload.get('error') or tv_upload} "
                f"(CDP 9222 + launch_tv_debug.bat required)"
            )
        vis = report.get("vision") or {}
        if vis.get("note"):
            print(f"VISION: {vis.get('note')}")
        elif vis.get("backend"):
            print(f"VISION: {vis.get('backend')} {vis.get('model')} → {vis.get('symbol_count')} syms")
        print((report.get("tradingview_txt") or "").strip())
        if not (report.get("symbols") or []):
            print("WARN: no symbols — check best_frame OCR in watchlist.json")
            bf = report.get("best_frame") or {}
            print(f"  best_frame={bf.get('t')} layout={bf.get('layout')} score={bf.get('score')}")
            print(f"  raw_ocr_sample={(bf.get('raw_ocr_symbols') or [])[:20]}")
    except Exception as e:
        write_status(video_id, status="error", error=str(e), traceback=traceback.format_exc())
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="OCR/vision Martin E_Main sidebar → TradingView Upload .txt"
    )
    p.add_argument("video_id")
    p.add_argument(
        "--mode",
        choices=["auto", "sidebar", "emain", "tail", "screener"],
        default="auto",
        help="auto/sidebar=E_Main right watchlist (default); screener=Potent secondary only",
    )
    p.add_argument("--last-minutes", type=float, default=8.0, help="Tail window for E_Main snaps")
    p.add_argument("--interval", type=float, default=45.0, help="Seconds between tail snaps")
    p.add_argument("--coarse-interval", type=float, default=45.0, help="Screener coarse grid")
    p.add_argument("--dense-interval", type=float, default=12.0, help="Screener densify step")
    p.add_argument("--max-frames", type=int, default=3)
    p.add_argument("--min-hits", type=int, default=2, help="Min table hits for unknown tickers")
    p.add_argument(
        "--vision",
        action="store_true",
        help="Force vision/LLM E_Main sidebar read (needs TUBEON_OPENAI_API_KEY)",
    )
    p.add_argument("--no-vision", action="store_true", help="Disable vision even if configured")
    p.add_argument("--vision-frames", type=int, default=3)
    p.add_argument(
        "--upload-date",
        default=None,
        help="VOD calendar date YYYY-MM-DD or yt-dlp upload_date (watchlist name date)",
    )
    p.add_argument("--force", action="store_true", help="Re-extract frames even if cached")
    args = p.parse_args()
    use_vision: bool | None
    if args.no_vision:
        use_vision = False
    elif args.vision:
        use_vision = True
    else:
        use_vision = None
    # Prefer CLI date; else status file from martin_daily
    upload_date = args.upload_date
    if not upload_date:
        st = status_path(args.video_id)
        if st.exists():
            try:
                upload_date = json.loads(st.read_text(encoding="utf-8")).get("upload_date")
            except json.JSONDecodeError:
                upload_date = None
    run(
        args.video_id,
        mode=args.mode,
        last_minutes=args.last_minutes,
        interval_sec=args.interval,
        coarse_interval=args.coarse_interval,
        dense_interval=args.dense_interval,
        max_frames=args.max_frames,
        min_hits=args.min_hits,
        use_vision=use_vision,
        vision_frames=args.vision_frames,
        upload_date=upload_date,
        force=args.force,
    )
