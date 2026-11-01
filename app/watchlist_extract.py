# -*- coding: utf-8 -*-
"""Sample the last N minutes of a Martin Luk VOD and OCR on-screen ticker lists.

Martin often scrolls leading / mediocre / lagging watchlists near the end of
the stream. Captions alone miss those symbols; this module downloads the VOD
(via video_check.download_video), grabs evenly spaced frames from the tail,
crops the right-hand TradingView-style panel, OCRs it, and aggregates tickers.

Outputs:
  data/frames/{id}/watchlist.json          — full report (+ local frame paths)
  data/summaries/{id}.watchlist.json       — copy for git / phone UI
  outputs/watchlists/{id}.txt              — TradingView Upload list
  outputs/watchlists/{id}.md               — human-readable list
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from .config import DATA_DIR, OUTPUT_DIR, SUMMARY_DIR, ensure_dirs
from .tradingview_export import format_watchlist_txt, tv_symbol, write_tradingview_txt
from .transcript import format_ts, load_transcript
from .video_check import (
    ASR_ALIASES,
    FRAMES_DIR,
    KNOWN_TICKERS,
    TICKER_RE,
    download_video,
    extract_frame,
    ffmpeg_bin,
    ocr_image,
    stamp_name,
    tickers_from_text,
)

WATCHLIST_OUT_DIR = OUTPUT_DIR / "watchlists"
WATCHLIST_JOB_DIR = DATA_DIR / "watchlist_jobs"

# UI / chart chrome that looks like a ticker but is not one
OCR_STOP = {
    "EMA", "SMA", "RSI", "MACD", "ATR", "VWAP", "VOL", "USD", "USDT", "DAY", "DAYS",
    "HIGH", "LOW", "OPEN", "CLOSE", "LONG", "SHORT", "BUY", "SELL", "WATCH", "LIST",
    "LEAD", "LEADING", "LAGGING", "LAG", "MEDIOCRE", "SESSION", "CHART", "TIME",
    "PRICE", "LAST", "BID", "ASK", "CHANGE", "VOLUME", "MARKET", "STOCK", "STOCKS",
    "SHARE", "SHARES", "INDEX", "FUTURE", "OPTION", "PUTS", "CALL", "CALLS",
    "PRE", "POST", "AH", "PM", "ET", "EST", "UTC", "GMT", "MIN", "MAX", "AVG",
    "THE", "AND", "FOR", "FROM", "WITH", "THIS", "THAT", "INTO", "OVER", "UNDER",
    "NEXT", "PREV", "WEEK", "MONTH", "YEAR", "TODAY", "YESTERDAY", "TOMORROW",
    "LIVE", "CHAT", "VIEW", "VIEWS", "LIKE", "LIKES", "SUB", "SUBS", "MARTIN",
    "LUK", "EP", "EPS", "PE", "PB", "ROI", "ROE", "CEO", "CFO", "IPO", "ETF",
    "ETFS", "NYSE", "AMEX", "OTC", "SEC", "FED", "CPI", "GDP", "ATH", "ATL",
    "GAP", "GAPS", "PIN", "BAR", "BARS", "CANDLE", "RANGE", "BREAK", "FADE",
    "TRIM", "HOLD", "HELD", "WAIT", "SIDE", "AREA", "ZONE", "LEVEL", "LEVELS",
    "LINE", "LINES", "CROSS", "ABOVE", "BELOW", "NEAR", "AROUND", "ABOUT",
    "JUST", "LIKE", "ALSO", "ONLY", "VERY", "MUCH", "MORE", "LESS", "GOOD",
    "BAD", "FINE", "OKAY", "YES", "NO", "NOT", "NOW", "THEN", "WHEN", "WHAT",
    "HOW", "WHY", "WHO", "ALL", "ANY", "SOME", "EACH", "BOTH", "SAME", "OTHER",
    "NEW", "OLD", "BIG", "TOP", "BOT", "MID", "LEFT", "RIGHT", "FULL", "HALF",
    "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN",
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
    "MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN",
    "HTTP", "HTTPS", "WWW", "COM", "HTML", "JSON", "API",
    "RGB", "PNG", "JPG", "JPEG", "MP", "FPS", "HD", "UHD", "SDR", "HDR",
}

SECTION_HINTS = (
    ("leading", re.compile(r"\bleading\b", re.I)),
    ("mediocre", re.compile(r"\bmediocre\b", re.I)),
    ("lagging", re.compile(r"\blagg?ing\b", re.I)),
)

# Optional price after a ticker: NVDA 142.5 / NVDA $142
PRICE_NEAR = re.compile(
    r"\b([A-Z]{2,5})\b(?:\s*[|:/\-]\s*|\s+)\$?(\d{1,5}(?:\.\d{1,4})?)",
)


def video_duration_sec(video_path: Path) -> float:
    """Duration in seconds via ffprobe; 0 if unknown."""
    probe = shutil.which("ffprobe") or "ffprobe"
    cmd = [
        probe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode == 0 and (r.stdout or "").strip():
            return float(r.stdout.strip())
    except (OSError, ValueError):
        pass
    # Fallback: ffmpeg -i stderr
    try:
        r = subprocess.run(
            [ffmpeg_bin(), "-i", str(video_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr or "")
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return h * 3600 + mi * 60 + s
    except (OSError, ValueError):
        pass
    return 0.0


def duration_from_transcript(video_id: str) -> float:
    tr = load_transcript(video_id) or {}
    snippets = tr.get("snippets") or []
    if not snippets:
        return 0.0
    last = snippets[-1]
    try:
        return float(last.get("start") or 0) + float(last.get("duration") or 0)
    except (TypeError, ValueError):
        return 0.0


def sample_tail_seconds(
    duration: float,
    *,
    last_minutes: float = 10.0,
    interval_sec: float = 20.0,
    end_pad_sec: float = 5.0,
) -> list[float]:
    """Evenly spaced timestamps covering the last ``last_minutes`` of the VOD."""
    if duration <= 0:
        return []
    window = max(30.0, float(last_minutes) * 60.0)
    start = max(0.0, duration - window)
    end = max(start, duration - max(0.0, end_pad_sec))
    if end <= start:
        return [start]
    interval = max(5.0, float(interval_sec))
    times: list[float] = []
    t = start
    while t <= end + 1e-6:
        times.append(round(t, 2))
        t += interval
    if not times or times[-1] < end - 1.0:
        times.append(round(end, 2))
    # de-dupe while preserving order
    out: list[float] = []
    seen: set[float] = set()
    for x in times:
        key = round(x, 1)
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out


def crop_watchlist_panel(frame_path: Path, crop_path: Path) -> Path | None:
    """Crop the right-hand watchlist / symbol panel Martin usually shows on TV."""
    try:
        from PIL import Image
    except ImportError:
        return None
    im = Image.open(frame_path)
    w, h = im.size
    # Right panel (watchlist) — slightly wider than video_check ticker strip
    right = im.crop((int(w * 0.62), int(h * 0.04), w, int(h * 0.96)))
    # Also grab a thin top symbol header strip in case he is on a single chart
    top = im.crop((0, 0, int(w * 0.55), int(h * 0.14)))
    pad = 10
    out_w = max(right.width, top.width)
    out_h = top.height + pad + right.height
    canvas = Image.new("RGB", (out_w, out_h), (16, 16, 16))
    canvas.paste(top, (0, 0))
    canvas.paste(right, (0, top.height + pad))
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    # Upscale 2x for OCR on small text
    canvas = canvas.resize((canvas.width * 2, canvas.height * 2), Image.Resampling.LANCZOS)
    canvas.save(crop_path, quality=95)
    return crop_path


def _candidate_tickers(text: str) -> list[str]:
    """Broader than tickers_from_text: keep frequent OCR tokens that look like tickers."""
    found: list[str] = []
    upper = (text or "").upper()
    for raw, canon in ASR_ALIASES.items():
        if re.search(rf"\b{re.escape(raw)}\b", upper) and canon not in found:
            found.append(canon)
    if "SPACE EXPLORATION" in upper or "SPACEX" in upper.replace(" ", ""):
        if "SPCX" not in found:
            found.append("SPCX")
    for m in TICKER_RE.findall(upper):
        canon = ASR_ALIASES.get(m, m)
        if canon in OCR_STOP:
            continue
        if canon not in found:
            found.append(canon)
    return found


def _prices_from_ocr(text: str, tickers: set[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    upper = (text or "").upper()
    for m in PRICE_NEAR.finditer(upper):
        sym = ASR_ALIASES.get(m.group(1), m.group(1))
        if sym not in tickers and sym not in KNOWN_TICKERS:
            continue
        if sym in OCR_STOP:
            continue
        try:
            price = float(m.group(2))
        except ValueError:
            continue
        # Skip obvious non-prices (years, EMAs)
        if price > 50000 or (1000 <= price <= 2100 and price == int(price)):
            continue
        out[sym] = price
    return out


def _section_hits(text: str) -> list[str]:
    return [name for name, rx in SECTION_HINTS if rx.search(text or "")]


def extract_watchlist(
    video_id: str,
    *,
    last_minutes: float = 10.0,
    interval_sec: float = 20.0,
    min_hits: int = 2,
    status_cb: Callable[..., None] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Download VOD if needed, sample tail frames, OCR, aggregate ticker list."""

    def note(**kw: Any) -> None:
        if status_cb:
            status_cb(**kw)

    ensure_dirs()
    frames_root = FRAMES_DIR / video_id / "tail"
    frames_root.mkdir(parents=True, exist_ok=True)

    note(step="download_video", status="running")
    video_path = download_video(video_id)

    duration = video_duration_sec(video_path)
    if duration <= 0:
        duration = duration_from_transcript(video_id)
    if duration <= 0:
        raise RuntimeError(f"Cannot determine duration for {video_id}")

    times = sample_tail_seconds(
        duration,
        last_minutes=last_minutes,
        interval_sec=interval_sec,
    )
    note(
        step="extract_frames",
        status="running",
        duration_sec=round(duration, 1),
        frame_targets=len(times),
        last_minutes=last_minutes,
        interval_sec=interval_sec,
    )

    engine = "none"
    frame_rows: list[dict[str, Any]] = []
    hit_counter: Counter[str] = Counter()
    price_votes: dict[str, list[float]] = defaultdict(list)
    section_by_ticker: dict[str, Counter[str]] = defaultdict(Counter)
    ocr_examples: dict[str, str] = {}

    for i, sec in enumerate(times):
        stamp = stamp_name(sec)
        jpg = frames_root / f"{stamp}.jpg"
        crop = frames_root / f"{stamp}_wl.jpg"
        try:
            if force or not jpg.exists() or jpg.stat().st_size < 2000:
                extract_frame(video_path, sec, jpg)
            if force and crop.exists():
                crop.unlink()
            crop_watchlist_panel(jpg, crop)
            ocr_src = crop if crop.exists() else jpg
            ocr_text, engine = ocr_image(ocr_src)
            known = tickers_from_text(ocr_text)
            candidates = _candidate_tickers(ocr_text)
            # Prefer known set; keep other candidates for aggregation
            tickers = list(dict.fromkeys(known + [c for c in candidates if c in KNOWN_TICKERS or c not in OCR_STOP]))
            sections = _section_hits(ocr_text)
            prices = _prices_from_ocr(ocr_text, set(tickers) | set(known))
            for t in tickers:
                hit_counter[t] += 1
                if t not in ocr_examples and ocr_text.strip():
                    ocr_examples[t] = ocr_text.strip()[:180]
                for sec_name in sections:
                    section_by_ticker[t][sec_name] += 1
            for t, p in prices.items():
                price_votes[t].append(p)
            frame_rows.append(
                {
                    "t": format_ts(sec),
                    "seconds": sec,
                    "frame": f"/frames/{video_id}/tail/{jpg.name}",
                    "crop": f"/frames/{video_id}/tail/{crop.name}" if crop.exists() else None,
                    "ocr": ocr_text.strip()[:400],
                    "tickers": tickers,
                    "sections": sections,
                    "prices": prices,
                }
            )
        except Exception as e:
            frame_rows.append({"t": format_ts(sec), "seconds": sec, "error": str(e)})
        if i % 3 == 0:
            note(step="extract_frames", status="running", done=i + 1, total=len(times))

    # Score frames by unique known tickers — the densest frame is likely the list
    def _score(row: dict[str, Any]) -> int:
        ticks = row.get("tickers") or []
        return sum(1 for t in ticks if t in KNOWN_TICKERS)

    best = max(frame_rows, key=_score, default=None)
    best_set = set((best or {}).get("tickers") or [])

    items: list[dict[str, Any]] = []
    for sym, hits in hit_counter.most_common():
        known = sym in KNOWN_TICKERS
        # Keep: known with >=1 hit, or unknown with enough repeats / in densest frame
        if known:
            if hits < 1:
                continue
        elif hits < max(min_hits, 2) and sym not in best_set:
            continue
        elif sym in OCR_STOP:
            continue
        sections = [s for s, _ in section_by_ticker[sym].most_common()]
        prices = price_votes[sym]
        price = None
        if prices:
            prices_sorted = sorted(prices)
            price = prices_sorted[len(prices_sorted) // 2]
        items.append(
            {
                "symbol": sym,
                "hits": hits,
                "known": known,
                "sections": sections,
                "price": price,
                "tv": tv_symbol(sym),
                "ocr_sample": ocr_examples.get(sym),
                "in_best_frame": sym in best_set,
            }
        )

    # Prefer densest-frame symbols first, then by hits
    items.sort(key=lambda x: (-int(x.get("in_best_frame") or 0), -int(x.get("hits") or 0), x["symbol"]))
    symbols = [x["symbol"] for x in items]

    section_name = f"Martin Luk {video_id}"
    tv_txt = format_watchlist_txt(symbols, section=section_name)

    report: dict[str, Any] = {
        "video_id": video_id,
        "duration_sec": round(duration, 1),
        "last_minutes": last_minutes,
        "interval_sec": interval_sec,
        "ocr_engine": engine,
        "frame_count": len(frame_rows),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "items": items,
        "best_frame": {
            "t": (best or {}).get("t"),
            "seconds": (best or {}).get("seconds"),
            "frame": (best or {}).get("frame"),
            "crop": (best or {}).get("crop"),
            "tickers": (best or {}).get("tickers") or [],
        }
        if best
        else None,
        "frames": frame_rows,
        "tradingview_txt": tv_txt,
        "tradingview_note": (
            "TradingView has no public watchlist API. Import via Watchlist name menu → "
            "Upload list… (Essential+). File is comma-separated EXCHANGE:SYMBOL .txt."
        ),
    }

    # Persist
    local_json = FRAMES_DIR / video_id / "watchlist.json"
    local_json.parent.mkdir(parents=True, exist_ok=True)
    local_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_json = SUMMARY_DIR / f"{video_id}.watchlist.json"
    # Slim copy for git / phone (drop bulky per-frame OCR)
    slim = {
        k: report[k]
        for k in (
            "video_id",
            "duration_sec",
            "last_minutes",
            "interval_sec",
            "ocr_engine",
            "frame_count",
            "symbol_count",
            "symbols",
            "items",
            "best_frame",
            "tradingview_txt",
            "tradingview_note",
        )
        if k in report
    }
    summary_json.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")

    WATCHLIST_OUT_DIR.mkdir(parents=True, exist_ok=True)
    tv_path = write_tradingview_txt(
        WATCHLIST_OUT_DIR / f"{video_id}.txt",
        symbols,
        section=section_name,
    )
    md_path = WATCHLIST_OUT_DIR / f"{video_id}.md"
    md_lines = [
        f"# Martin Luk on-screen list — `{video_id}`",
        "",
        f"- Window: last **{last_minutes:g}** min (every {interval_sec:g}s)",
        f"- Duration: {format_ts(duration)} | frames: {len(frame_rows)} | OCR: {engine}",
        f"- Symbols: **{len(symbols)}**",
        "",
        "## Tickers",
        "",
        "| Symbol | Hits | Section | Price (OCR) | TradingView |",
        "|---|---:|---|---:|---|",
    ]
    for it in items:
        secs = ", ".join(it.get("sections") or []) or "—"
        price = it.get("price")
        price_s = f"{price:g}" if isinstance(price, (int, float)) else "—"
        md_lines.append(
            f"| {it['symbol']} | {it['hits']} | {secs} | {price_s} | `{it['tv']}` |"
        )
    md_lines += [
        "",
        "## TradingView import",
        "",
        "1. Open TradingView → Watchlist panel → click the list name → **Upload list…**",
        "2. Select the `.txt` file next to this markdown (same stem).",
        "3. Requires Essential+; there is **no** public API to push watchlists.",
        "",
        "```",
        tv_txt.strip(),
        "```",
        "",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    report["paths"] = {
        "watchlist_json": str(local_json),
        "summary_json": str(summary_json),
        "tradingview_txt": str(tv_path),
        "markdown": str(md_path),
    }
    note(
        step="done",
        status="done",
        symbol_count=len(symbols),
        frame_count=len(frame_rows),
        ocr_engine=engine,
        tradingview_txt=str(tv_path),
    )
    return report


def load_watchlist(video_id: str) -> dict[str, Any] | None:
    for path in (
        SUMMARY_DIR / f"{video_id}.watchlist.json",
        FRAMES_DIR / video_id / "watchlist.json",
    ):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
    return None
