# -*- coding: utf-8 -*-
"""YouTube VOD end → screenshot → E_Main list → optional TradingView upload.

Local-only path Luk asked for (no full-VOD download / 90-frame OCR):
  1) Open the VOD near the end in a real browser (Playwright)
  2) Hide YouTube live chat, screenshot the *player* at device_scale_factor=3
     (sharp native pixels; no later upscale). Martin's watchlist is on the
     right of the streamed TradingView layout — not the YouTube chat column.
  3) OCR → sectioned E_Main txt
  4) Optional CDP upload to TradingView

Usage (from repo root on DESKTOP-U9FBPC7):
  cd /d "C:\\Users\\kinao\\OneDrive\\桌面\\stock\\youtube"
  python scripts\\yt_browser_cap_emain.py NUT6d6Hvbmw --date 2026-11-04 --upload
  python scripts\\yt_browser_cap_emain.py enPWrvGoE60 --date 2026-11-03 --upload
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DATA_DIR, ensure_dirs  # noqa: E402
from app.emain_eligibility import log_refuse, prepare_emain_outputs  # noqa: E402
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
    "SHXQ": "SOXQ",
    "IWN": "IWM",
}
SKIP_TOKENS = {
    "E", "MAIN", "LAST", "EXT", "CHG", "SYMBOL", "USD", "OPEN",
    "HIGH", "LOW", "VOL", "AVG", "THE", "AND", "FOR", "YOU",
    "TOP", "CHAT", "TRADE", "ALERT", "REPLAY", "SAVE", "KEY",
}
# Bottom TradingView details card (Invesco QQQ Trust / Key facts…)
DETAIL_STOP = {
    "INVESCO", "TRUST", "SERIES", "MARKET", "VOLUME", "FACTS",
    "FUNDS", "MUTUAL", "MISC", "NASDA",
}


def _norm_header(tok: str) -> str | None:
    t = OCR_FIX.get(tok.upper(), tok.upper())
    return t if t in SECTION_ORDER else None


def parse_emain_from_ocr_text(text: str) -> dict[str, list[str]]:
    """Parse INDEXES/LONGS/SHORTS/FOCUS/TRACKING tickers out of messy OCR text."""
    buckets = {k: [] for k in SECTION_ORDER}
    if not text:
        return buckets
    raw = text.replace("\n", " ")
    for bad, good in OCR_FIX.items():
        raw = re.sub(rf"\b{bad}\b", good, raw, flags=re.I)
    parts = HEADER_RE.split(raw)
    earlier: set[str] = set()
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
                    break
                if tok in DETAIL_STOP:
                    break
                if tok in SKIP_TOKENS:
                    continue
                if len(tok) < 2:
                    continue
                if tok in earlier:
                    # Details card repeats an earlier ticker (e.g. QQQ under the list).
                    break
                if not is_valid_us_ticker(tok, allow_unknown_long=True):
                    continue
                if tok not in seen:
                    seen.add(tok)
                    buckets[hdr].append(tv_symbol(tok))
            earlier.update(seen)
            i += 2
            continue
        i += 1
    return buckets


def yt_dlp_cmd(*args: str) -> list[str]:
    """yt-dlp with a JS runtime when Node is installed, so dates/duration resolve."""
    cmd = ["yt-dlp"]
    node = os.environ.get("TUBEON_NODE", "").strip()
    node_path = Path(node) if node else Path(r"C:\Program Files\nodejs\node.exe")
    if not node_path.exists():
        found = shutil.which("node")
        node_path = Path(found) if found else node_path
    if node_path.exists():
        cmd += ["--js-runtimes", f"node:{node_path}"]
    cmd.extend(args)
    return cmd


def _hide_youtube_chat(page) -> None:
    """Close/hide the YouTube live-chat column so the player can use full width."""
    selectors = [
        "ytd-live-chat-frame #close-button button",
        "ytd-live-chat-frame #close-button",
        "#chat-container #close-button button",
        "button[aria-label*='Close' i]",
        "button[aria-label*='關閉']",
        "button[aria-label*='??']",
        "button[aria-label*='Hide chat' i]",
        "button[aria-label*='隱藏聊天']",
        "button[aria-label*='?藏聊天']",
        "button[aria-label*='隱藏傾偈']",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=800):
                loc.click(timeout=2000)
                page.wait_for_timeout(600)
                break
        except Exception:
            continue
    try:
        page.evaluate(
            """() => {
                const hide = (el) => {
                    if (el) el.style.setProperty('display', 'none', 'important');
                };
                hide(document.querySelector('#secondary'));
                hide(document.querySelector('ytd-live-chat-frame'));
                hide(document.querySelector('#chat'));
                hide(document.querySelector('#chat-container'));
            }"""
        )
        page.wait_for_timeout(400)
    except Exception:
        pass


def _screenshot_player(page, out_png: Path) -> None:
    try:
        player = page.locator("#movie_player").first
        if player.count() and player.is_visible(timeout=3000):
            player.screenshot(path=str(out_png))
            return
    except Exception:
        pass
    page.screenshot(path=str(out_png), full_page=False)


def browser_end_screenshot(video_id: str, out_png: Path, *, end_pad_sec: int = 20) -> Path:
    """Open YouTube VOD near the end and save a PNG of the player."""
    from playwright.sync_api import sync_playwright

    dur = 0.0
    try:
        dur = float(
            subprocess.check_output(
                yt_dlp_cmd("--print", "%(duration)s", f"https://www.youtube.com/watch?v={video_id}"),
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

    # Default headless so the 04:30 scheduled run does not pop a window.
    # Set TUBEON_YT_HEADLESS=0 only if a headed check is needed.
    raw_headless = os.environ.get("TUBEON_YT_HEADLESS", "1").strip().lower()
    headless = raw_headless not in {"0", "false", "no"}
    launch_args = ["--autoplay-policy=no-user-gesture-required"]
    if not headless:
        launch_args += ["--window-position=-2400,0", "--window-size=1920,1080"]

    with sync_playwright() as p:
        raw_scale = os.environ.get("TUBEON_YT_SCALE", "3").strip() or "3"
        try:
            scale = int(raw_scale)
        except ValueError:
            scale = 3
        scale = max(1, min(scale, 3))
        browser = p.chromium.launch(headless=headless, args=launch_args)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=scale,
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(4000)
        try:
            page.locator("#movie_player").first.click(timeout=3000)
        except Exception:
            pass
        _hide_youtube_chat(page)
        try:
            page.keyboard.press("m")  # mute
        except Exception:
            pass
        try:
            page.keyboard.press("k")  # play/pause — start playback if paused
        except Exception:
            pass
        page.wait_for_timeout(1500)
        try:
            page.keyboard.press("t")  # theater mode, player uses full width
            page.wait_for_timeout(800)
        except Exception:
            pass
        _hide_youtube_chat(page)
        page.wait_for_timeout(2500)
        _screenshot_player(page, out_png)
        browser.close()
    return out_png


def _column_brightness(im, x: int, y0: int, y1: int, step: int = 3) -> float:
    w, h = im.size
    x = max(0, min(w - 1, x))
    total = n = 0
    for y in range(y0, min(y1, h), step):
        r, g, b = im.getpixel((x, y))
        total += (r + g + b) / 3.0
        n += 1
    return total / n if n else 0.0


def find_youtube_chat_x(im) -> int | None:
    """Return x where a light YouTube live-chat column starts, else None."""
    w, h = im.size
    y0, y1 = int(h * 0.20), int(h * 0.70)
    for x in range(int(w * 0.40), w - 8):
        if _column_brightness(im, x, y0, y1) > 180:
            if _column_brightness(im, min(w - 1, x + 30), y0, y1) > 160:
                return x
    return None


def crop_right_sidebar(png: Path, out_jpg: Path) -> Path:
    """Crop Martin's E_Main panel: right side of the *video*, never YouTube chat."""
    from PIL import Image

    im = Image.open(png).convert("RGB")
    w, h = im.size
    chat_x = find_youtube_chat_x(im)
    if chat_x:
        right = chat_x
        left = int(right * 0.80)
        top = int(h * 0.10)
        bottom = int(h * 0.80)
    else:
        left = int(w * 0.78)
        right = int(w * 0.995)
        top = int(h * 0.08)
        bottom = int(h * 0.92)
    left = max(0, min(left, w - 2))
    right = max(left + 1, min(right, w))
    top = max(0, min(top, h - 2))
    bottom = max(top + 1, min(bottom, h))
    crop = im.crop((left, top, right, bottom))
    # Do not upscale: 3x device_scale_factor already gives sharp pixels.
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    suffix = out_jpg.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        crop.save(out_jpg, quality=95, subsampling=0, optimize=True)
    else:
        crop.save(out_jpg)
    return out_jpg


def run(video_id: str, *, vod_date: str, upload: bool, reuse_png: Path | None = None) -> Path:
    ensure_dirs()
    cap_dir = DATA_DIR / "frames" / video_id / "yt_browser"
    full = reuse_png if reuse_png and reuse_png.exists() else cap_dir / "end.png"
    if reuse_png is None or not Path(full).exists():
        full = browser_end_screenshot(video_id, cap_dir / "end.png")
    side = crop_right_sidebar(Path(full), cap_dir / "end_sidebar.png")
    raw = ocr_image(side)
    text = raw[0] if isinstance(raw, tuple) else (raw or "")
    (cap_dir / "end_sidebar.ocr.txt").write_text(str(text), encoding="utf-8")
    buckets = parse_emain_from_ocr_text(str(text))
    n = sum(len(v) for v in buckets.values())
    print("OCR buckets:", {k: buckets[k] for k in SECTION_ORDER})
    if n < 3:
        raise SystemExit("E_Main not readable from screenshot OCR — check end_sidebar.png")
    # include_empty keeps ###FOCUS even when that section has no tickers.
    body = format_emain_watchlist_txt(buckets, include_empty=True)
    info = prepare_emain_outputs(
        ROOT / "outputs" / "watchlists",
        video_id=video_id,
        vod_date=vod_date,
        body=body if isinstance(body, str) else str(body),
    )
    out = info["dated_path"] or info["debug_path"]
    print("WROTE", out)
    print(Path(out).read_text(encoding="utf-8"))
    if upload:
        if info["upload_path"] is None:
            log_refuse(out, info["problems"])
        else:
            print(maybe_upload_after_extract(info["upload_path"]))
    elif info["problems"]:
        log_refuse(out, info["problems"])
    return Path(out)


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
