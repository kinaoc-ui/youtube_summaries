# -*- coding: utf-8 -*-
"""Re-run E_Main sidebar extract on already-captured frames (no YouTube download).

Usage:
  python scripts/watchlist_from_frames.py iMBI3ZcQ6sU --vision
  python scripts/watchlist_from_frames.py iMBI3ZcQ6sU --frame watchlist-frames/e_main_sidebar.png --vision
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import SUMMARY_DIR, ensure_dirs, settings  # noqa: E402
from app.screener_vision import read_sidebar_sections, vision_available  # noqa: E402
from app.tradingview_export import (  # noqa: E402
    format_emain_watchlist_txt,
    write_tradingview_txt,
)
from app.video_check import FRAMES_DIR  # noqa: E402
from app.vod_date import resolve_vod_date  # noqa: E402
from app.watchlist_extract import (  # noqa: E402
    WATCHLIST_OUT_DIR,
    _empty_emain_buckets,
    detect_sidebar_from_image,
    merge_emain_buckets,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Extract E_Main sidebar from cached frames")
    p.add_argument("video_id")
    p.add_argument("--frame", action="append", default=[], help="Specific frame path (repeatable)")
    p.add_argument("--vision", action="store_true")
    p.add_argument("--no-vision", action="store_true")
    p.add_argument("--vision-frames", type=int, default=3)
    p.add_argument("--upload-date", default=None)
    args = p.parse_args()
    ensure_dirs()

    video_id = args.video_id
    frames: list[Path] = []
    for f in args.frame:
        path = Path(f)
        if not path.is_absolute():
            path = ROOT / path
        if path.exists():
            frames.append(path)
    if not frames:
        for root in (FRAMES_DIR / video_id / "tail", FRAMES_DIR / video_id / "screener"):
            if root.is_dir():
                frames.extend(sorted(root.glob("*.jpg")))
                frames.extend(sorted(root.glob("*.png")))
        frames = [f for f in frames if "_symcol" not in f.name and "_hdr" not in f.name]
    if not frames:
        print(f"No frames under data/frames/{video_id}/ (or --frame)")
        return 1

    print(f"frames: {len(frames)}")
    buckets = _empty_emain_buckets()
    scored: list[tuple[int, Path, dict]] = []
    for path in frames:
        side = detect_sidebar_from_image(path)
        n = len(side.get("symbols") or [])
        scored.append((n, path, side))
        print(
            f"  {path.name}: sidebar={side.get('sidebar')} "
            f"headers={side.get('headers')} syms={side.get('symbols')}"
        )
        if side.get("sidebar"):
            buckets = merge_emain_buckets(buckets, side.get("buckets") or {})

    scored.sort(key=lambda x: -x[0])
    use_vision = False if args.no_vision else (True if args.vision else bool(settings.watchlist_vision))
    source = "sidebar_ocr" if sum(len(v) for v in buckets.values()) >= 3 else "none"
    vision_meta: dict = {}
    if use_vision:
        avail = vision_available()
        paths = [s[1] for s in scored[: args.vision_frames]]
        if avail.get("ok"):
            vis = _empty_emain_buckets()
            for path in paths:
                result = read_sidebar_sections(path)
                if result.get("sidebar"):
                    vis = merge_emain_buckets(vis, result.get("buckets") or {})
            vision_meta = {"backend": avail.get("backend"), "buckets": vis}
            if sum(len(v) for v in vis.values()) >= sum(len(v) for v in buckets.values()):
                buckets = vis
                source = "sidebar_vision"
            print(
                f"VISION → INDEXES={len(buckets['INDEXES'])} LONGS={len(buckets['LONGS'])} "
                f"SHORTS={len(buckets['SHORTS'])} FOCUS={len(buckets['FOCUS'])} "
                f"TRACKING={len(buckets['TRACKING'])}"
            )
        else:
            print("VISION unavailable — set TUBEON_OPENAI_API_KEY")

    vod_date = resolve_vod_date(video_id, hint=args.upload_date)
    symbols = (
        buckets["INDEXES"]
        + buckets["LONGS"]
        + buckets["SHORTS"]
        + buckets["FOCUS"]
        + buckets["TRACKING"]
    )
    tv_txt = format_emain_watchlist_txt(buckets)
    WATCHLIST_OUT_DIR.mkdir(parents=True, exist_ok=True)
    tv_path = write_tradingview_txt(
        WATCHLIST_OUT_DIR / f"{video_id}.txt",
        buckets=buckets,
        date_iso=vod_date,
        video_id=video_id,
        list_name="E_Main",
        emain=True,
        also_dated_filename=True,
    )
    summary = {
        "video_id": video_id,
        "vod_date": vod_date,
        "list_name": f"Martin Luk {vod_date} E_Main",
        "mode": "from_frames",
        "symbol_source": source,
        "symbol_count": len(symbols),
        "symbols": symbols,
        "buckets": buckets,
        "vision": vision_meta,
        "tradingview_txt": tv_txt,
    }
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    (SUMMARY_DIR / f"{video_id}.watchlist.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"OK {video_id} [{source}] name=Martin Luk {vod_date} E_Main → {tv_path}")
    print(tv_txt)
    return 0 if symbols else 2


if __name__ == "__main__":
    raise SystemExit(main())
