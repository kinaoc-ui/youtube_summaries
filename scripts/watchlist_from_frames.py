# -*- coding: utf-8 -*-
"""Re-run screener Symbol extract on already-captured frames (no YouTube download).

Use after a local screener job cached frames under data/frames/<id>/screener/,
especially to apply allowlist + vision without re-downloading the VOD.

Usage:
  python scripts/watchlist_from_frames.py iMBI3ZcQ6sU --vision
  python scripts/watchlist_from_frames.py iMBI3ZcQ6sU --frame data/frames/iMBI3ZcQ6sU/screener/1-18-32.jpg
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import SUMMARY_DIR, ensure_dirs, settings  # noqa: E402
from app.tradingview_export import format_watchlist_txt, write_tradingview_txt  # noqa: E402
from app.us_tickers import filter_symbols  # noqa: E402
from app.video_check import FRAMES_DIR  # noqa: E402
from app.watchlist_extract import (  # noqa: E402
    WATCHLIST_OUT_DIR,
    analyze_frame_ocr,
    crop_symbol_column,
)
from app.screener_vision import read_best_screener_frames, vision_available  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Extract watchlist from cached screener frames")
    p.add_argument("video_id")
    p.add_argument("--frame", action="append", default=[], help="Specific frame path (repeatable)")
    p.add_argument("--vision", action="store_true", help="Force vision read")
    p.add_argument("--no-vision", action="store_true")
    p.add_argument("--vision-frames", type=int, default=3)
    args = p.parse_args()
    ensure_dirs()

    video_id = args.video_id
    roots = [
        FRAMES_DIR / video_id / "screener",
        FRAMES_DIR / video_id / "tail",
    ]
    frames: list[Path] = []
    for f in args.frame:
        path = Path(f)
        if not path.is_absolute():
            path = ROOT / path
        if path.exists():
            frames.append(path)
    if not frames:
        for root in roots:
            if root.is_dir():
                frames.extend(sorted(root.glob("*.jpg")))
                frames.extend(sorted(root.glob("*.png")))
        # Prefer full frames over crops
        frames = [f for f in frames if "_symcol" not in f.name and "_wl" not in f.name and "_hdr" not in f.name]
    if not frames:
        print(f"No frames under data/frames/{video_id}/screener (or --frame)")
        return 1

    print(f"frames: {len(frames)}")
    ocr_hits: dict[str, int] = {}
    scored: list[tuple[float, Path, dict]] = []
    for path in frames:
        analysis = analyze_frame_ocr(path)
        col = path.with_name(path.stem + "_symcol.jpg")
        crop_symbol_column(path, col)
        if col.exists():
            col_a = analyze_frame_ocr(col)
            if len(col_a.get("table_symbols") or []) >= len(analysis.get("table_symbols") or []):
                analysis = col_a
        score = float(analysis.get("score") or 0) + len(analysis.get("table_symbols") or [])
        scored.append((score, path, analysis))
        for s in analysis.get("table_symbols") or []:
            ocr_hits[s] = ocr_hits.get(s, 0) + 1
        print(
            f"  {path.name}: layout={analysis.get('layout')} "
            f"allowlisted={analysis.get('table_symbols')} "
            f"raw={(analysis.get('raw_ocr_symbols') or [])[:12]}"
        )

    scored.sort(key=lambda x: -x[0])
    use_vision = False if args.no_vision else (True if args.vision else bool(settings.watchlist_vision))
    vision_syms: list[str] = []
    vision_meta: dict = {}
    if use_vision:
        avail = vision_available()
        paths = [s[1] for s in scored[: args.vision_frames]]
        if avail.get("ok"):
            vision_meta = read_best_screener_frames(paths, max_frames=args.vision_frames)
            vision_syms = filter_symbols(list(vision_meta.get("symbols") or []), allow_unknown_long=True)
            print(f"VISION {avail.get('backend')} → {vision_syms}")
        else:
            print("VISION unavailable — set TUBEON_OPENAI_API_KEY or TUBEON_VISION_OLLAMA_MODEL")
            print("Falling back to allowlisted OCR only.")

    if len(vision_syms) >= 5:
        symbols = vision_syms
        source = "vision"
    else:
        symbols = filter_symbols(sorted(ocr_hits, key=lambda s: (-ocr_hits[s], s)))
        source = "ocr_allowlist"

    section = f"Martin Luk {video_id}"
    tv_txt = format_watchlist_txt(symbols, section=section)
    WATCHLIST_OUT_DIR.mkdir(parents=True, exist_ok=True)
    tv_path = write_tradingview_txt(WATCHLIST_OUT_DIR / f"{video_id}.txt", symbols, section=section)
    summary = {
        "video_id": video_id,
        "mode": "from_frames",
        "symbol_source": source,
        "symbol_count": len(symbols),
        "symbols": symbols,
        "ocr_hits": ocr_hits,
        "vision": {"symbols": vision_syms, **{k: vision_meta.get(k) for k in ("backend", "model", "note")}},
        "tradingview_txt": tv_txt,
        "best_frame": str(scored[0][1]) if scored else None,
    }
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    (SUMMARY_DIR / f"{video_id}.watchlist.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (FRAMES_DIR / video_id / "watchlist.json").parent.mkdir(parents=True, exist_ok=True)
    (FRAMES_DIR / video_id / "watchlist.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = WATCHLIST_OUT_DIR / f"{video_id}.md"
    md.write_text(
        f"# Martin Luk on-screen list — `{video_id}` (from frames)\n\n"
        f"- Source: **{source}** | symbols: **{len(symbols)}**\n\n"
        + ", ".join(symbols)
        + "\n\n```\n"
        + tv_txt
        + "```\n",
        encoding="utf-8",
    )
    print(f"OK {video_id} [{source}]: {len(symbols)} → {tv_path}")
    for s in symbols:
        print(f"  {s}")
    return 0 if symbols else 2


if __name__ == "__main__":
    raise SystemExit(main())
