"""Capture last visible frame from a YouTube VOD URL (high-res), for E_Main OCR."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DATA_DIR, ensure_dirs  # noqa: E402
from app.watchlist_extract import (  # noqa: E402
    detect_sidebar_from_image,
    video_duration_sec,
)
from app.video_check import VIDEO_DIR, download_video, extract_frame, ffmpeg_bin  # noqa: E402
from app.emain_eligibility import log_refuse, prepare_emain_outputs  # noqa: E402
from app.tradingview_export import format_emain_watchlist_txt  # noqa: E402
from app.tv_cdp_upload import maybe_upload_after_extract  # noqa: E402


def capture_end_frames(video_id: str, *, steps: int = 4, step_sec: float = 10.0) -> list[Path]:
    """Download once (prefer 720p+), grab last 1s then -10s frames."""
    ensure_dirs()
    # Prefer sharper than 360p for sidebar OCR
    video_path = download_video(video_id, max_height=720)
    dur = video_duration_sec(video_path)
    if dur <= 0:
        raise RuntimeError(f"no duration for {video_id}")
    out_dir = DATA_DIR / "frames" / video_id / "yt_end"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    t = max(0.0, dur - 1.0)
    for i in range(max(1, steps)):
        jpg = out_dir / f"end_{i}_{int(t)}.jpg"
        extract_frame(video_path, t, jpg)
        paths.append(jpg)
        t = max(0.0, t - step_sec)
    return paths


def best_sidebar(paths: list[Path]) -> dict:
    best = {"symbols": [], "headers": [], "buckets": {}, "path": None, "sidebar": False}
    for p in paths:
        d = detect_sidebar_from_image(p)
        n = len(d.get("symbols") or [])
        if d.get("sidebar") and n >= len(best.get("symbols") or []):
            best = {**d, "path": str(p)}
    return best


def main() -> None:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("video_id")
    p.add_argument("--date", required=True, help="YYYY-MM-DD for Martin_Luk_DATE_E_Main")
    p.add_argument("--upload", action="store_true")
    p.add_argument("--steps", type=int, default=4)
    args = p.parse_args()
    frames = capture_end_frames(args.video_id, steps=args.steps)
    print("frames:", ", ".join(str(f) for f in frames))
    side = best_sidebar(frames)
    print("sidebar", side.get("sidebar"), "hdr", side.get("headers"), "n", len(side.get("symbols") or []))
    print("symbols", side.get("symbols"))
    print("buckets", side.get("buckets"))
    buckets = side.get("buckets") or {}
    n = sum(len(v or []) for v in buckets.values())
    if n < 3:
        raise SystemExit("no E_Main list on end frames — open VOD end manually")
    # map to TV symbols if bare tickers
    from app.watchlist_extract import tv_symbol

    mapped = {
        k: [tv_symbol(x) if isinstance(x, str) and ":" not in x else x for x in (buckets.get(k) or [])]
        for k in ("INDEXES", "LONGS", "SHORTS", "FOCUS", "TRACKING")
    }
    body = format_emain_watchlist_txt(mapped)
    info = prepare_emain_outputs(
        ROOT / "outputs" / "watchlists",
        video_id=args.video_id,
        vod_date=args.date,
        body=body if isinstance(body, str) else str(body),
    )
    out = info["dated_path"] or info["debug_path"]
    print("WROTE", out)
    print(Path(out).read_text(encoding="utf-8"))
    if args.upload:
        if info["upload_path"] is None:
            log_refuse(out, info["problems"])
        else:
            print(maybe_upload_after_extract(info["upload_path"]))


if __name__ == "__main__":
    main()
