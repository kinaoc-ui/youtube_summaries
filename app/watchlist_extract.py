# -*- coding: utf-8 -*-
"""OCR Martin Luk on-screen ticker lists (TradingView screener / Leader tables).

History: the first pass assumed a right-column watchlist in the last ~10 minutes.
On VODs like iMBI3ZcQ6sU Martin instead opens a full **Leader** screener table
(many symbols in a Symbol column) and may also open a single-name detail panel
(e.g. BRZE @ 45.85). Detail panels must not wipe the table list.

Strategy (mode=screener / auto):
  1. Sample across the whole VOD (coarse) + denser windows around speech/summary
     hints (leader / screener / watch list / leading / mediocre / lagging) + a
     modest tail densify. Not hard-locked to last 10 minutes.
  2. OCR full frames with RapidOCR **bounding boxes**.
  3. Detect layout: screener_table vs detail_panel vs chart_chrome.
  4. For tables, take the leftmost vertically-aligned symbol column — ignore
     detail-panel-only frames as list sources (they only add weak single-symbol
     evidence).
  5. Aggregate by table-weighted hits; export TradingView Upload-list .txt.

Outputs:
  data/frames/{id}/watchlist.json
  data/summaries/{id}.watchlist.json
  outputs/watchlists/{id}.txt
  outputs/watchlists/{id}.md
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

from .config import DATA_DIR, OUTPUT_DIR, SUMMARY_DIR, ensure_dirs, settings
from .parse_md import parse_summary_markdown
from .tradingview_export import format_watchlist_txt, tv_symbol, write_tradingview_txt
from .transcript import format_ts, load_transcript
from .us_tickers import filter_symbols, is_valid_us_ticker, normalize_symbol
from .video_check import (
    ASR_ALIASES,
    FRAMES_DIR,
    KNOWN_TICKERS,
    TICKER_RE,
    download_video,
    extract_frame,
    ffmpeg_bin,
    ocr_boxes,
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
    "SYMBOL", "TICKER", "NAME", "DESC", "DESCRIPTION", "SECTOR", "INDUSTRY",
    "SCREENER", "FILTER", "FILTERS", "COLUMN", "COLUMNS", "SORT", "SORTED",
    "LEADER", "LEADERS", "FOLLOWER", "FOLLOWERS", "UNIVERSE", "CANDIDATE",
    "CANDIDATES", "POTENT", "POTENTIAL", "BIOTECH", "BIOTEEX", "MERGER", "BUYOUT",
    "CERA",  # known OCR junk seen on iMBI3ZcQ6sU misread; still allow if in KNOWN
}

SECTION_HINTS = (
    ("leader", re.compile(r"\bleaders?\b", re.I)),
    ("leading", re.compile(r"\bleading\b", re.I)),
    ("mediocre", re.compile(r"\bmediocre\b", re.I)),
    ("lagging", re.compile(r"\blagg?ing\b", re.I)),
    ("screener", re.compile(r"\bscreeners?\b", re.I)),
)

SPEECH_HINT_RE = re.compile(
    r"\b(leader|leaders|leading|mediocre|lagging|laging|screener|screeners|"
    r"watch\s*list|watchlist|symbol column|potent watch)\b",
    re.I,
)

TABLE_HEADER_RE = re.compile(
    r"\b(symbol|ticker|change\s*%?|vol(?:ume)?|price|leader|leaders|screener)\b",
    re.I,
)

PRICE_NEAR = re.compile(
    r"\b([A-Z]{2,5})\b(?:\s*[|:/\-]\s*|\s+)\$?(\d{1,5}(?:\.\d{1,4})?)",
)

TICKER_TOKEN_RE = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$")

# Ground-truth Symbol column from iMBI3ZcQ6sU best frame (vision); used in tests only docs
IMBI_LEADER_SYMBOLS = [
    "AXSM", "GNS", "ICLR", "EVR", "WMG", "TXG", "BYON", "TWST", "TEM", "PPG",
    "CRL", "FRO", "ACN", "PNT", "REVV", "MRNA", "NTRA", "HCA", "ETSY", "IQV",
    "SOFI", "GH", "EXAS", "RBRK", "AKAM", "Z", "MNSO",
]


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


def _dedupe_times(times: Iterable[float]) -> list[float]:
    out: list[float] = []
    seen: set[float] = set()
    for x in sorted(float(t) for t in times):
        key = round(x, 1)
        if key in seen:
            continue
        seen.add(key)
        out.append(round(x, 2))
    return out


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
        times.append(t)
        t += interval
    if not times or times[-1] < end - 1.0:
        times.append(end)
    return _dedupe_times(times)


def speech_hint_seconds(video_id: str) -> list[float]:
    """Timestamps where captions/summary mention screener / leader / watchlist."""
    hits: list[float] = []
    tr = load_transcript(video_id) or {}
    for s in tr.get("snippets") or []:
        text = str(s.get("text") or "")
        if SPEECH_HINT_RE.search(text):
            try:
                hits.append(float(s.get("start") or 0))
            except (TypeError, ValueError):
                continue
    md_path = SUMMARY_DIR / f"{video_id}.md"
    if md_path.exists():
        try:
            parsed = parse_summary_markdown(md_path.read_text(encoding="utf-8"))
        except Exception:
            parsed = {}
        for bucket in (
            parsed.get("exec_zh") or [],
            parsed.get("bullets_zh") or [],
            parsed.get("bullets_en") or [],
        ):
            for b in bucket:
                text = str(b.get("text") or "")
                if not SPEECH_HINT_RE.search(text):
                    continue
                t = str(b.get("t") or "").strip()
                if not t:
                    continue
                from .video_check import parse_ts

                hits.append(parse_ts(t))
    return _dedupe_times(hits)


def sample_screener_seconds(
    duration: float,
    *,
    video_id: str | None = None,
    coarse_interval: float = 45.0,
    dense_interval: float = 12.0,
    dense_radius: float = 90.0,
    tail_minutes: float = 12.0,
    max_frames: int = 90,
) -> list[float]:
    """Whole-VOD coarse grid + densify around speech hints + modest tail densify."""
    if duration <= 0:
        return []
    times: list[float] = []
    # Coarse full scan
    t = 0.0
    while t < duration - 2:
        times.append(t)
        t += max(15.0, coarse_interval)
    times.append(max(0.0, duration - 5.0))
    # Speech / summary densify
    centers = speech_hint_seconds(video_id) if video_id else []
    for c in centers:
        a = max(0.0, c - dense_radius)
        b = min(duration - 2.0, c + dense_radius)
        u = a
        while u <= b + 1e-6:
            times.append(u)
            u += max(5.0, dense_interval)
    # Tail densify (still useful; not exclusive)
    times.extend(
        sample_tail_seconds(
            duration,
            last_minutes=tail_minutes,
            interval_sec=max(8.0, dense_interval),
        )
    )
    times = _dedupe_times(times)
    if len(times) > max_frames:
        # Prefer speech-near + tail; keep evenly spaced subset of the rest
        prefer = set()
        for c in centers:
            for x in times:
                if abs(x - c) <= dense_radius:
                    prefer.add(round(x, 1))
        tail_start = duration - tail_minutes * 60
        for x in times:
            if x >= tail_start:
                prefer.add(round(x, 1))
        kept = [x for x in times if round(x, 1) in prefer]
        rest = [x for x in times if round(x, 1) not in prefer]
        need = max(0, max_frames - len(kept))
        if need and rest:
            step = max(1, len(rest) // need)
            kept.extend(rest[::step][:need])
        times = _dedupe_times(kept)[:max_frames]
    return times


def crop_watchlist_panel(frame_path: Path, crop_path: Path) -> Path | None:
    """Legacy right+top crop (tail mode). Screener mode OCRs the full frame."""
    try:
        from PIL import Image
    except ImportError:
        return None
    im = Image.open(frame_path)
    w, h = im.size
    right = im.crop((int(w * 0.62), int(h * 0.04), w, int(h * 0.96)))
    top = im.crop((0, 0, int(w * 0.55), int(h * 0.14)))
    pad = 10
    out_w = max(right.width, top.width)
    out_h = top.height + pad + right.height
    canvas = Image.new("RGB", (out_w, out_h), (16, 16, 16))
    canvas.paste(top, (0, 0))
    canvas.paste(right, (0, top.height + pad))
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = canvas.resize((canvas.width * 2, canvas.height * 2), Image.Resampling.LANCZOS)
    canvas.save(crop_path, quality=95)
    return crop_path


def crop_symbol_column(frame_path: Path, crop_path: Path) -> Path | None:
    """Crop left ~30% (TradingView Symbol column) and upscale for OCR."""
    try:
        from PIL import Image
    except ImportError:
        return None
    im = Image.open(frame_path)
    w, h = im.size
    # Symbol column is usually far left under "Symbol" header
    col = im.crop((int(w * 0.02), int(h * 0.08), int(w * 0.30), int(h * 0.96)))
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    col = col.resize((col.width * 3, col.height * 3), Image.Resampling.LANCZOS)
    col.save(crop_path, quality=95)
    return crop_path


def _normalize_token(text: str) -> str:
    return normalize_symbol(text)


def _is_ticker_token(token: str, *, allow_unknown_long: bool = False) -> bool:
    """Strict: reject 1–2 letter noise + dotted OCR junk unless allowlisted."""
    s = normalize_symbol(token)
    if not s:
        return False
    if s in OCR_STOP and not is_valid_us_ticker(s):
        return False
    return is_valid_us_ticker(s, allow_unknown_long=allow_unknown_long)


def _candidate_tickers(text: str) -> list[str]:
    found: list[str] = []
    upper = (text or "").upper()
    for raw, canon in ASR_ALIASES.items():
        if re.search(rf"\b{re.escape(raw)}\b", upper) and _is_ticker_token(canon):
            if canon not in found:
                found.append(canon)
    if "SPACE EXPLORATION" in upper or "SPACEX" in upper.replace(" ", ""):
        if "SPCX" not in found and _is_ticker_token("SPCX"):
            found.append("SPCX")
    for m in TICKER_RE.findall(upper):
        canon = ASR_ALIASES.get(m, m)
        if not _is_ticker_token(canon):
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
        if not _is_ticker_token(sym):
            continue
        try:
            price = float(m.group(2))
        except ValueError:
            continue
        if price > 50000 or (1000 <= price <= 2100 and price == int(price)):
            continue
        out[sym] = price
    return out


def _section_hits(text: str) -> list[str]:
    return [name for name, rx in SECTION_HINTS if rx.search(text or "")]


def symbols_from_boxes(boxes: list[dict[str, Any]]) -> dict[str, Any]:
    """Detect screener vs detail panel; extract leftmost symbol column when table."""
    blob = " ".join(str(b.get("text") or "") for b in boxes)
    header_hits = len(TABLE_HEADER_RE.findall(blob))
    ticker_boxes: list[dict[str, Any]] = []
    for b in boxes:
        tok = _normalize_token(str(b.get("text") or ""))
        # Sometimes OCR glues "NVDA 142" — take first allowlisted token
        if not _is_ticker_token(tok):
            parts = re.findall(r"[A-Z]{1,5}", tok)
            tok = next((p for p in parts if _is_ticker_token(p)), "")
        if not tok:
            continue
        ticker_boxes.append({**b, "symbol": tok})

    if not ticker_boxes:
        return {
            "layout": "empty",
            "score": 0.0,
            "symbols": [],
            "header_hits": header_hits,
            "column_count": 0,
            "raw_column_symbols": [],
        }

    # Cluster by x center into columns (narrower bins → tighter Symbol column)
    max_x = max(float(b["x1"]) for b in boxes) or 1.0
    bin_w = max(28.0, max_x * 0.05)
    cols: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for b in ticker_boxes:
        cols[int(float(b["cx"]) // bin_w)].append(b)

    # Rank columns by unique symbols + vertical span (table rows)
    ranked: list[tuple[float, int, list[str]]] = []
    for key, items in cols.items():
        # Sort by y so order matches the table
        items_sorted = sorted(items, key=lambda x: float(x["cy"]))
        syms = list(dict.fromkeys(x["symbol"] for x in items_sorted))
        ys = [float(x["cy"]) for x in items_sorted]
        vspan = (max(ys) - min(ys)) if len(ys) > 1 else 0.0
        # Prefer left columns with many vertically stacked allowlisted tickers
        score = len(syms) * 3.0 + (4.0 if vspan > max_x * 0.20 else 0.0)
        score += max(0.0, 6.0 - key * 0.8)
        ranked.append((score, key, syms))
    ranked.sort(reverse=True)
    best_score, best_key, best_syms = ranked[0]
    # Prefer leftmost among top candidates if similar density
    left_key = min(r[1] for r in ranked[:4]) if ranked else best_key
    for score, key, syms in ranked[:4]:
        if key == left_key and len(syms) >= max(3, len(best_syms) - 3):
            best_key, best_syms, best_score = key, syms, score
            break

    raw_column = list(best_syms)
    # Hard filter: only allowlisted symbols ship from OCR
    best_syms = filter_symbols(best_syms, allow_unknown_long=False)

    n = len(best_syms)
    n_raw = len(raw_column)
    rightish = best_key >= max(2, int((max_x * 0.55) // bin_w))
    if n <= 2 and (rightish or header_hits == 0):
        layout = "detail_panel"
        score = float(n) * 0.25
    elif n >= 4 or (n >= 3 and header_hits) or (n_raw >= 6 and n >= 2):
        layout = "screener_table"
        score = float(n) + header_hits * 1.5 + (2.0 if re.search(r"\bleaders?\b", blob, re.I) else 0.0)
    elif n >= 3:
        layout = "screener_table"
        score = float(n) * 0.8
    else:
        layout = "chart_chrome"
        score = float(n) * 0.3

    return {
        "layout": layout,
        "score": round(score, 2),
        "symbols": best_syms if layout == "screener_table" else (
            best_syms if layout != "empty" else []
        ),
        "detail_symbols": best_syms if layout == "detail_panel" else [],
        "table_symbols": best_syms if layout == "screener_table" else [],
        "raw_column_symbols": raw_column,
        "header_hits": header_hits,
        "column_count": len(cols),
        "column_key": best_key,
    }


def analyze_frame_ocr(image_path: Path) -> dict[str, Any]:
    """OCR one image; prefer box-based screener parse, fall back to text scrape."""
    boxes, engine = ocr_boxes(image_path)
    text = " ".join(str(b.get("text") or "") for b in boxes).strip()
    if not text:
        text, engine = ocr_image(image_path)
        boxes = []
    parsed = symbols_from_boxes(boxes) if boxes else {
        "layout": "text_only",
        "score": 0.0,
        "symbols": [],
        "detail_symbols": [],
        "table_symbols": [],
        "raw_column_symbols": [],
        "header_hits": len(TABLE_HEADER_RE.findall(text or "")),
        "column_count": 0,
    }
    # Text fallback — still allowlist-filtered (drops KK/LM/SX…)
    text_syms = filter_symbols(
        list(dict.fromkeys(tickers_from_text(text) + _candidate_tickers(text))),
        allow_unknown_long=False,
    )
    table_syms = filter_symbols(list(parsed.get("table_symbols") or []), allow_unknown_long=False)
    detail_syms = filter_symbols(list(parsed.get("detail_symbols") or []), allow_unknown_long=False)
    if parsed.get("layout") == "screener_table" and len(table_syms) >= 3:
        symbols = table_syms
    elif parsed.get("layout") == "detail_panel":
        symbols = detail_syms
    else:
        symbols = table_syms or text_syms
        if len(text_syms) >= 5 and parsed.get("layout") in {"text_only", "chart_chrome", "empty"}:
            parsed["layout"] = "screener_table"
            parsed["table_symbols"] = text_syms
            parsed["score"] = max(float(parsed.get("score") or 0), float(len(text_syms)))
            symbols = text_syms
            table_syms = text_syms
    return {
        "engine": engine,
        "ocr": text[:500],
        "layout": parsed.get("layout"),
        "score": float(parsed.get("score") or 0),
        "symbols": symbols,
        "table_symbols": table_syms,
        "detail_symbols": detail_syms,
        "raw_ocr_symbols": list(parsed.get("raw_column_symbols") or []),
        "sections": _section_hits(text),
        "prices": _prices_from_ocr(text, set(symbols) | set(text_syms)),
        "header_hits": parsed.get("header_hits") or 0,
    }


def extract_watchlist(
    video_id: str,
    *,
    mode: str = "screener",
    last_minutes: float = 10.0,
    interval_sec: float = 20.0,
    coarse_interval: float = 45.0,
    dense_interval: float = 12.0,
    max_frames: int = 90,
    min_hits: int = 2,
    use_vision: bool | None = None,
    vision_frames: int | None = None,
    status_cb: Callable[..., None] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Download VOD if needed, sample frames, OCR+vision screener tables, aggregate."""

    def note(**kw: Any) -> None:
        if status_cb:
            status_cb(**kw)

    ensure_dirs()
    mode = (mode or "screener").lower().strip()
    if mode == "auto":
        mode = "screener"
    if use_vision is None:
        use_vision = bool(getattr(settings, "watchlist_vision", True))
    if vision_frames is None:
        vision_frames = int(getattr(settings, "watchlist_vision_frames", 3) or 3)
    frames_root = FRAMES_DIR / video_id / ("screener" if mode == "screener" else "tail")
    frames_root.mkdir(parents=True, exist_ok=True)

    note(step="download_video", status="running", mode=mode)
    video_path = download_video(video_id)

    duration = video_duration_sec(video_path)
    if duration <= 0:
        duration = duration_from_transcript(video_id)
    if duration <= 0:
        raise RuntimeError(f"Cannot determine duration for {video_id}")

    if mode == "tail":
        times = sample_tail_seconds(
            duration,
            last_minutes=last_minutes,
            interval_sec=interval_sec,
        )
    else:
        times = sample_screener_seconds(
            duration,
            video_id=video_id,
            coarse_interval=coarse_interval,
            dense_interval=dense_interval,
            tail_minutes=max(last_minutes, 12.0),
            max_frames=max_frames,
        )

    note(
        step="extract_frames",
        status="running",
        mode=mode,
        duration_sec=round(duration, 1),
        frame_targets=len(times),
        last_minutes=last_minutes,
        interval_sec=interval_sec,
    )

    engine = "none"
    frame_rows: list[dict[str, Any]] = []
    table_hits: Counter[str] = Counter()
    weak_hits: Counter[str] = Counter()
    price_votes: dict[str, list[float]] = defaultdict(list)
    section_by_ticker: dict[str, Counter[str]] = defaultdict(Counter)
    ocr_examples: dict[str, str] = {}
    path_by_stamp: dict[str, Path] = {}

    for i, sec in enumerate(times):
        stamp = stamp_name(sec)
        jpg = frames_root / f"{stamp}.jpg"
        try:
            if force or not jpg.exists() or jpg.stat().st_size < 2000:
                extract_frame(video_path, sec, jpg)
            path_by_stamp[stamp] = jpg
            # Screener: OCR full frame + left Symbol-column crop (stricter geometry)
            analysis = analyze_frame_ocr(jpg)
            if mode == "screener":
                col = frames_root / f"{stamp}_symcol.jpg"
                if force and col.exists():
                    col.unlink()
                crop_symbol_column(jpg, col)
                if col.exists():
                    col_analysis = analyze_frame_ocr(col)
                    # Prefer column crop when it yields more allowlisted symbols
                    if len(col_analysis.get("table_symbols") or []) >= len(
                        analysis.get("table_symbols") or []
                    ) and float(col_analysis.get("score") or 0) >= float(analysis.get("score") or 0) * 0.8:
                        analysis = col_analysis
                        analysis["crop"] = f"/frames/{video_id}/screener/{col.name}"
            if mode == "tail":
                crop = frames_root / f"{stamp}_wl.jpg"
                if force and crop.exists():
                    crop.unlink()
                crop_watchlist_panel(jpg, crop)
                if crop.exists():
                    crop_analysis = analyze_frame_ocr(crop)
                    if float(crop_analysis.get("score") or 0) >= float(analysis.get("score") or 0):
                        analysis = crop_analysis
                        analysis["crop"] = f"/frames/{video_id}/tail/{crop.name}"
            engine = str(analysis.get("engine") or engine)
            layout = str(analysis.get("layout") or "empty")
            table_syms = filter_symbols(list(analysis.get("table_symbols") or []))
            detail_syms = filter_symbols(list(analysis.get("detail_symbols") or []))
            syms = filter_symbols(list(analysis.get("symbols") or []))
            sections = list(analysis.get("sections") or [])
            prices = dict(analysis.get("prices") or {})
            ocr_text = str(analysis.get("ocr") or "")

            if layout == "screener_table" and table_syms:
                for t in table_syms:
                    table_hits[t] += 1
                    if t not in ocr_examples and ocr_text:
                        ocr_examples[t] = ocr_text[:180]
                    for sec_name in sections:
                        section_by_ticker[t][sec_name] += 1
            else:
                for t in detail_syms or syms:
                    weak_hits[t] += 1
                    if t not in ocr_examples and ocr_text:
                        ocr_examples[t] = ocr_text[:180]
            for t, p in prices.items():
                if is_valid_us_ticker(t):
                    price_votes[t].append(p)

            frame_rows.append(
                {
                    "t": format_ts(sec),
                    "seconds": sec,
                    "frame": f"/frames/{video_id}/{frames_root.name}/{jpg.name}",
                    "local_path": str(jpg),
                    "crop": analysis.get("crop"),
                    "ocr": ocr_text[:400],
                    "layout": layout,
                    "score": analysis.get("score"),
                    "tickers": syms,
                    "table_symbols": table_syms,
                    "detail_symbols": detail_syms,
                    "raw_ocr_symbols": list(analysis.get("raw_ocr_symbols") or [])[:40],
                    "sections": sections,
                    "prices": prices,
                }
            )
        except Exception as e:
            frame_rows.append({"t": format_ts(sec), "seconds": sec, "error": str(e)})
        if i % 3 == 0:
            note(step="extract_frames", status="running", done=i + 1, total=len(times), mode=mode)

    def _row_score(row: dict[str, Any]) -> float:
        if row.get("layout") != "screener_table":
            return float(row.get("score") or 0) * 0.1
        return float(row.get("score") or 0) + len(row.get("table_symbols") or [])

    best = max(frame_rows, key=_row_score, default=None)
    best_set = set((best or {}).get("table_symbols") or (best or {}).get("tickers") or [])

    # --- Vision pass on top screener frames (preferred over RapidOCR junk) ---
    vision_meta: dict[str, Any] = {"available": False, "symbols": [], "reads": []}
    vision_syms: list[str] = []
    if use_vision:
        note(step="vision_screener", status="running")
        from .screener_vision import read_best_screener_frames, vision_available

        avail = vision_available()
        ranked_frames = sorted(
            [r for r in frame_rows if r.get("local_path") and not r.get("error")],
            key=_row_score,
            reverse=True,
        )
        # Prefer frames that look like tables even if OCR allowlist was sparse
        paths = [Path(r["local_path"]) for r in ranked_frames[: max(vision_frames, 5)]]
        # Always include highest-score path first
        if best and best.get("local_path"):
            bp = Path(best["local_path"])
            paths = [bp] + [p for p in paths if p != bp]
        paths = paths[:vision_frames]
        if avail.get("ok") and paths:
            vision_meta = read_best_screener_frames(paths, max_frames=vision_frames)
            vision_syms = filter_symbols(
                list(vision_meta.get("symbols") or []),
                allow_unknown_long=True,
            )
            vision_meta["symbols"] = vision_syms
        else:
            vision_meta = {
                "available": bool(avail.get("ok")),
                "backend": avail.get("backend"),
                "model": avail.get("model"),
                "symbols": [],
                "reads": [],
                "note": (
                    "Vision skipped — set TUBEON_OPENAI_API_KEY (or "
                    "TUBEON_VISION_OLLAMA_MODEL) for Symbol-column vision read"
                ),
            }
        note(
            step="vision_screener",
            status="done",
            vision_symbols=len(vision_syms),
            vision_backend=vision_meta.get("backend"),
        )

    items: list[dict[str, Any]] = []
    # Prefer vision list when it found a real table (>=5). Else allowlisted OCR only.
    if len(vision_syms) >= 5:
        primary = list(vision_syms)
        source_tag = "vision"
        # Merge allowlisted OCR hits that also appear on table frames (extra confirmation)
        for s in table_hits:
            if s not in primary and is_valid_us_ticker(s):
                primary.append(s)
        all_syms = primary
    else:
        source_tag = "ocr_allowlist"
        all_syms = [
            s
            for s in (set(table_hits) | {s for s, n in weak_hits.items() if n >= max(min_hits + 1, 3)})
            if is_valid_us_ticker(s)
        ]
        if not all_syms and best_set:
            all_syms = [s for s in best_set if is_valid_us_ticker(s)]
        # Drop OCR-only junk that somehow slipped: require allowlist membership
        all_syms = filter_symbols(list(all_syms), allow_unknown_long=False)

    vision_set = set(vision_syms)
    for sym in all_syms:
        th = table_hits[sym]
        wh = weak_hits[sym]
        if source_tag != "vision":
            if th <= 0 and (wh < max(min_hits, 3) or sym not in best_set):
                # weak-only without vision: skip unless allowlisted short ticker in best
                if not (is_valid_us_ticker(sym) and sym in best_set and wh >= 1):
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
                "hits": th,
                "weak_hits": wh,
                "known": is_valid_us_ticker(sym),
                "sections": sections,
                "price": price,
                "tv": tv_symbol(sym),
                "ocr_sample": ocr_examples.get(sym),
                "in_best_frame": sym in best_set,
                "in_vision": sym in vision_set,
                "source": (
                    "vision"
                    if sym in vision_set
                    else ("screener_table" if th else "detail_or_chrome")
                ),
            }
        )

    if source_tag == "vision":
        # Preserve vision Symbol-column order
        order = {s: i for i, s in enumerate(vision_syms)}
        items.sort(key=lambda x: (order.get(x["symbol"], 10_000), x["symbol"]))
    else:
        items.sort(
            key=lambda x: (
                -int(x.get("in_best_frame") or 0),
                -int(x.get("hits") or 0),
                -int(x.get("weak_hits") or 0),
                x["symbol"],
            )
        )
    symbols = [x["symbol"] for x in items]

    section_name = f"Martin Luk {video_id}"
    tv_txt = format_watchlist_txt(symbols, section=section_name)

    table_frames = sum(1 for r in frame_rows if r.get("layout") == "screener_table")
    detail_frames = sum(1 for r in frame_rows if r.get("layout") == "detail_panel")

    report: dict[str, Any] = {
        "video_id": video_id,
        "mode": mode,
        "strategy": (
            "screener-aware: whole-VOD sample + left Symbol-column OCR filtered by "
            "US allowlist (drops KK/A.M junk); prefer vision/LLM read of top "
            "screener frames when configured; detail panels do not replace table"
        ),
        "symbol_source": source_tag,
        "duration_sec": round(duration, 1),
        "last_minutes": last_minutes,
        "interval_sec": interval_sec,
        "ocr_engine": engine,
        "frame_count": len(frame_rows),
        "table_frame_count": table_frames,
        "detail_frame_count": detail_frames,
        "symbol_count": len(symbols),
        "symbols": symbols,
        "items": items,
        "vision": {
            "available": vision_meta.get("available"),
            "backend": vision_meta.get("backend"),
            "model": vision_meta.get("model"),
            "symbols": vision_syms,
            "symbol_count": len(vision_syms),
            "note": vision_meta.get("note"),
            "reads": [
                {
                    "path": r.get("path"),
                    "symbols": r.get("symbols"),
                    "error": r.get("error"),
                    "backend": r.get("backend"),
                }
                for r in (vision_meta.get("reads") or [])
            ],
        },
        "best_frame": {
            "t": (best or {}).get("t"),
            "seconds": (best or {}).get("seconds"),
            "frame": (best or {}).get("frame"),
            "layout": (best or {}).get("layout"),
            "score": (best or {}).get("score"),
            "tickers": (best or {}).get("table_symbols") or (best or {}).get("tickers") or [],
            "raw_ocr_symbols": (best or {}).get("raw_ocr_symbols") or [],
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

    local_json = FRAMES_DIR / video_id / "watchlist.json"
    local_json.parent.mkdir(parents=True, exist_ok=True)
    local_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_json = SUMMARY_DIR / f"{video_id}.watchlist.json"
    slim = {
        k: report[k]
        for k in (
            "video_id",
            "mode",
            "strategy",
            "symbol_source",
            "duration_sec",
            "last_minutes",
            "interval_sec",
            "ocr_engine",
            "frame_count",
            "table_frame_count",
            "detail_frame_count",
            "symbol_count",
            "symbols",
            "items",
            "vision",
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
        f"- Mode: **{mode}** ({report['strategy']})",
        f"- Duration: {format_ts(duration)} | frames: {len(frame_rows)} "
        f"(table={table_frames}, detail={detail_frames}) | OCR: {engine}",
        f"- Symbols: **{len(symbols)}**",
        "",
        "## Tickers",
        "",
        "| Symbol | Table hits | Weak hits | Section | Price (OCR) | TradingView |",
        "|---|---:|---:|---|---:|---|",
    ]
    for it in items:
        secs = ", ".join(it.get("sections") or []) or "—"
        price = it.get("price")
        price_s = f"{price:g}" if isinstance(price, (int, float)) else "—"
        md_lines.append(
            f"| {it['symbol']} | {it['hits']} | {it.get('weak_hits') or 0} | "
            f"{secs} | {price_s} | `{it['tv']}` |"
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
        mode=mode,
        symbol_count=len(symbols),
        frame_count=len(frame_rows),
        table_frame_count=table_frames,
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
