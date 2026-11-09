# -*- coding: utf-8 -*-
"""YouTube VOD end → screenshot → E_Main list → optional TradingView upload.

Local-only path Luk asked for (no full-VOD download / 90-frame OCR):
  1) Open the VOD near the end in a real browser (Playwright)
  2) Screenshot the player (watchlist on the right)
  3) OCR → sectioned E_Main txt
  4) Optional CDP upload to TradingView

Usage (from repo root on DESKTOP-U9FBPC7):
  cd /d "C:\\Users\\kinao\\OneDrive\\桌面\\stock\\youtube"
  python scripts\\yt_browser_cap_emain.py NUT6d6Hvbmw --date 2026-11-04 --upload
  python scripts\\yt_browser_cap_emain.py enPWrvGoE60 --date 2026-11-03 --upload
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DATA_DIR, ensure_dirs  # noqa: E402
from app.tradingview_export import format_emain_watchlist_txt  # noqa: E402
from app.tv_cdp_upload import maybe_upload_after_extract  # noqa: E402
from app.watchlist_extract import is_valid_us_ticker, ocr_image, tv_symbol  # noqa: E402

SECTION_ORDER = ("INDEXES", "LONGS", "SHORTS", "FOCUS", "TRACKING")
HEADER_RE = re.compile(
    r"\b(INDEXES|INOCIES|INOEXES|LONGS|LDNGS|SHORTS|FOCUS|TRACKING|TRADING)\b",
    re.I,
)
TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")
# OCR common misreads → canonical
OCR_FIX = {
    "INOCIES": "INDEXES",
    "INOEXES": "INDEXES",
    "LDNGS": "LONGS",
    "TRADING": "TRACKING",
    "AHXS": "SKHY",
    "DRAH": "DRAM",
    "BMRN": "BMNR",
}


def _norm_header(tok: str) -> str | None:
    t = OCR_FIX.get(tok.upper(), tok.upper())
    return t if t in SECTION_ORDER else None


def parse_emain_from_ocr_text(text: str) -> dict[str, list[str]]:
    """Parse INDEXES/LONGS/SHORTS/FOCUS/TRACKING tickers out of messy OCR text."""
    buckets = {k: [] for k in SECTION_ORDER}
    if not text:
        return buckets
    # Normalize
    raw = text.replace("\n", " ")
    for bad, good in OCR_FIX.items():
        raw = re.sub(rf"\b{bad}\b", good, raw, flags=re.I)
    # Split by section headers keeping delimiters
    parts = HEADER_RE.split(raw)
    # parts like [pre, HEADER, body, HEADER, body, ...]
    i = 0
    while i < len(parts):
        piece = parts[i].strip()
        hdr = _norm_header(piece) if piece else None
        if hdr and i + 1 < len(parts):
            body = parts[i + 1]
            seen: set[str] = set()
            for m in TICKER_RE.finditer(body.upper()):
                tok = OCR_FIX.get(m.group(1), m.group(1))
                if _norm_header(tok):
                    break  # next header leaked
                if tok in {
                    "E", "MAIN", "LAST", "EXT", "CHG", "SYMBOL", "USD", "OPEN",
                    "HIGH", "LOW", "VOL", "AVG", "THE", "AND", "FOR", "YOU",
                    "TOP", "CHAT", "TRADE", "ALERT", "REPLAY",
                }:
                    continue
                if len(tok) < 2:
                    continue
                if not is_valid_us_ticker(tok):
                    continue
                if tok not in seen:
                    seen.add(tok)
                    buckets[hdr].append(tv_symbol(tok))
            i += 2
            continue
        i += 1
    return buckets


def browser_end_screenshot(video_id: str, out_png: Path, *, end_pad_sec: int = 20) -> Path:
    """Open YouTube VOD near the end and save a PNG screenshot."""
    from playwright.sync_api import sync_playwright

    # duration via yt-dlp when possible
    import subprocess

    dur = 0.0
    try:
        dur = float(
            subprocess.check_output(
                ["yt-dlp", "--print", "%(duration)s", f"https://www.youtube.com/watch?v={video_id}"],
                text=True,
                encoding="utf-8",
                errors="replace",
            ).strip()
            or "0"
        )
    except Exception:
        dur = 0.0
    t = int(max(0, dur - end_pad_sec)) if dur > 0 else 0
    url = f"https://www.youtube.com/watch?v={video_id}&t={t}s"
    out_png.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(4000)
        # dismiss cookie / try play
        try:
            page.keyboard.press("k")  # play/pause
        except Exception:
            pass
        page.wait_for_timeout(2000)
        # bump quality if settings available — best-effort
        try:
            page.keyboard.press("f")  # fullscreen
            page.wait_for_timeout(1500)
        except Exception:
            pass
        page.screenshot(path=str(out_png), full_page=False)
        browser.close()
    return out_png


def crop_right_sidebar(png: Path, out_jpg: Path) -> Path:
    from PIL import Image

    im = Image.open(png).convert("RGB")
    w, h = im.size
    crop = im.crop((int(w * 0.78), int(h * 0.05), int(w * 0.995), int(h * 0.95)))
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    crop.save(out_jpg, quality=95)
    return out_jpg


def run(video_id: str, *, vod_date: str, upload: bool, reuse_png: Path | None = None) -> Path:
    ensure_dirs()
    cap_dir = DATA_DIR / "frames" / video_id / "yt_browser"
    full = reuse_png if reuse_png and reuse_png.exists() else cap_dir / "end.png"
    if reuse_png is None or not Path(full).exists():
        full = browser_end_screenshot(video_id, cap_dir / "end.png")
    side = crop_right_sidebar(Path(full), cap_dir / "end_sidebar.jpg")
    raw = ocr_image(side)
    text = raw[0] if isinstance(raw, tuple) else (raw or "")
    (cap_dir / "end_sidebar.ocr.txt").write_text(str(text), encoding="utf-8")
    buckets = parse_emain_from_ocr_text(str(text))
    n = sum(len(v) for v in buckets.values())
    print("OCR buckets:", {k: buckets[k] for k in SECTION_ORDER})
    if n < 3:
        raise SystemExit("E_Main not readable from screenshot OCR — check end_sidebar.jpg")
    stem = f"Martin_Luk_{vod_date}_E_Main"
    out = ROOT / "outputs" / "watchlists" / f"{stem}.txt"
    body = format_emain_watchlist_txt(buckets)
    out.write_text(body if isinstance(body, str) else str(body), encoding="utf-8")
    (ROOT / "outputs" / "watchlists" / f"{video_id}.E_Main.txt").write_text(
        out.read_text(encoding="utf-8"), encoding="utf-8"
    )
    print("WROTE", out)
    print(out.read_text(encoding="utf-8"))
    if upload:
        print(maybe_upload_after_extract(out))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="YouTube end screenshot → E_Main → TV")
    ap.add_argument("video_id")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--png", default=None, help="Reuse an existing screenshot PNG")
    args = ap.parse_args()
    run(
        args.video_id,
        vod_date=args.date,
        upload=args.upload,
        reuse_png=Path(args.png) if args.png else None,
    )


if __name__ == "__main__":
    main()
