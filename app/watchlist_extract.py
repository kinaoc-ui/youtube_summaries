# -*- coding: utf-8 -*-
"""OCR/vision Martin Luk on-screen TradingView lists.

Primary path = right sidebar **E_Main** (INDEXES / LONGS / SHORTS / FOCUS /
TRACKING). Sample chart frames + ``*_wl.jpg`` right crops; export dated
multi-section TradingView Upload ``.txt``.

Potent/Leader screener (``--mode screener``) is optional secondary only and
must never overwrite E_Main as the default Martin list.

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
from typing import Any, Callable, Iterable, Mapping, Sequence

from .config import DATA_DIR, OUTPUT_DIR, SUMMARY_DIR, ensure_dirs, settings
from .parse_md import parse_summary_markdown
from .tradingview_export import (
    IMBI_EMAIN_BUCKETS,
    IMBI_EMAIN_DATE,
    IMBI_EMAIN_TXT,
    format_dated_watchlist_txt,
    format_emain_watchlist_txt,
    list_filename,
    normalize_section_key,
    tv_symbol,
    write_tradingview_txt,
)
from .transcript import format_ts, load_transcript
from .us_tickers import filter_symbols, is_valid_us_ticker, normalize_symbol
from .vod_date import resolve_vod_date
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

# UI / chart chrome that looks like a ticker but is not one.
# NOTE: USD is ProShares Ultra Semiconductors on E_Main — NOT stop-listed.
OCR_STOP = {
    "EMA", "SMA", "RSI", "MACD", "ATR", "VWAP", "VOL", "USDT", "DAY", "DAYS",
    "HIGH", "LOW", "OPEN", "CLOSE", "LONG", "LONGS", "SHORT", "SHORTS", "BUY", "SELL",
    "WATCH", "LIST", "FOCUS", "TRACKING", "INDEXES", "INDICES",
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
    "CERA", "E_MAIN", "MAIN", "EXT", "CHG",
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

# Canonical E_Main for iMBI3ZcQ6sU (Luk/Grok MCP) — primary Martin list
IMBI_VOD_DATE = IMBI_EMAIN_DATE
IMBI_EMAIN = IMBI_EMAIN_BUCKETS
IMBI_EMAIN_CANONICAL_TXT = IMBI_EMAIN_TXT
# Optional Potent secondary (never default)
IMBI_POTENT_SYMBOLS = [
    "AXSM", "GNS", "ICLR", "EVR", "WMG", "TXG", "BYON", "TWST", "TEM", "PPG",
    "CRL", "FRO", "ACN", "PNT", "REVV", "MRNA", "NTRA", "HCA", "ETSY", "IQV",
    "SOFI", "GH", "EXAS", "RBRK", "AKAM", "Z", "MNSO",
]
IMBI_LEADER_SYMBOLS = IMBI_POTENT_SYMBOLS  # back-compat alias for Potent tests

# Sidebar section headers on E_Main
SIDEBAR_HEADER_RE = re.compile(
    r"^\s*(INDEXES|INDICES|LONGS?|SHORTS?|FOCUS|TRACKING)\s*$",
    re.I,
)
SIDEBAR_HEADER_IN_TEXT_RE = re.compile(
    r"\b(INDEXES|INDICES|LONGS|LONG|SHORTS|SHORT|FOCUS|TRACKING)\b",
    re.I,
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


def _empty_emain_buckets() -> dict[str, list[str]]:
    return {"INDEXES": [], "LONGS": [], "SHORTS": [], "FOCUS": [], "TRACKING": []}


def _norm_sidebar_header(text: str) -> str | None:
    return normalize_section_key(text or "")


def parse_sidebar_sections_from_boxes(boxes: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse right-watchlist E_Main INDEXES/LONGS/SHORTS/FOCUS/TRACKING from OCR boxes."""
    empty = {
        "sidebar": False,
        "buckets": _empty_emain_buckets(),
        "headers": [],
        "symbols": [],
        "list_name": None,
    }
    if not boxes:
        return empty

    max_x = max((float(b.get("x1") or b.get("cx") or 0) for b in boxes), default=1.0) or 1.0
    right_cut = max_x * 0.55
    right_boxes = [b for b in boxes if float(b.get("cx") or 0) >= right_cut]
    use = right_boxes if len(right_boxes) >= 3 else boxes

    list_name = None
    for b in use:
        raw = str(b.get("text") or "").strip()
        if re.search(r"E[_\s-]?Main", raw, re.I):
            list_name = "E_Main"
            break

    headers: list[tuple[float, str]] = []
    for b in use:
        label = _norm_sidebar_header(str(b.get("text") or ""))
        if label:
            headers.append((float(b.get("cy") or 0), label))
    if not headers:
        blob = " ".join(str(b.get("text") or "") for b in use)
        if not SIDEBAR_HEADER_IN_TEXT_RE.search(blob):
            return empty
        found = {m.group(1).upper() for m in SIDEBAR_HEADER_IN_TEXT_RE.finditer(blob)}
        norms = {normalize_section_key(h) for h in found}
        norms.discard(None)
        if not norms:
            return empty
        return {
            "sidebar": True,
            "buckets": _empty_emain_buckets(),
            "headers": sorted(norms),  # type: ignore[arg-type]
            "symbols": [],
            "list_name": list_name or "E_Main",
            "weak": True,
        }

    headers.sort(key=lambda x: x[0])
    dedup_h: list[tuple[float, str]] = []
    for cy, lab in headers:
        if dedup_h and dedup_h[-1][1] == lab:
            continue
        dedup_h.append((cy, lab))
    headers = dedup_h

    buckets = _empty_emain_buckets()
    ticker_boxes = []
    for b in use:
        tok = _normalize_token(str(b.get("text") or ""))
        if not tok or _norm_sidebar_header(tok):
            continue
        if not _is_ticker_token(tok, allow_unknown_long=True):
            continue
        ticker_boxes.append((float(b.get("cy") or 0), tok))
    ticker_boxes.sort(key=lambda x: x[0])

    for i, (h_y, lab) in enumerate(headers):
        y_lo = h_y
        y_hi = headers[i + 1][0] if i + 1 < len(headers) else 1e12
        for cy, tok in ticker_boxes:
            if y_lo < cy < y_hi and tok not in buckets[lab]:
                buckets[lab].append(tok)

    for k in list(buckets):
        buckets[k] = filter_symbols(buckets[k], allow_unknown_long=True)

    symbols = (
        buckets["INDEXES"]
        + buckets["LONGS"]
        + buckets["SHORTS"]
        + buckets["FOCUS"]
        + buckets["TRACKING"]
    )
    return {
        "sidebar": True,
        "buckets": buckets,
        "headers": [h for _, h in headers],
        "symbols": symbols,
        "list_name": list_name or "E_Main",
        "weak": False,
    }


def detect_sidebar_from_image(image_path: Path) -> dict[str, Any]:
    """OCR full frame + right ``*_wl`` / sidebar crop for E_Main section headers."""
    boxes, engine = ocr_boxes(image_path)
    parsed = parse_sidebar_sections_from_boxes(boxes)
    parsed["engine"] = engine
    if parsed.get("sidebar") and (parsed.get("symbols") or not parsed.get("weak")):
        return parsed
    try:
        from PIL import Image
    except ImportError:
        return parsed
    im = Image.open(image_path)
    w, h = im.size
    crop = im.crop((int(w * 0.68), int(h * 0.02), w, int(h * 0.98)))
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.LANCZOS)
    tmp = image_path.with_name(image_path.stem + "_wl.jpg")
    crop.save(tmp, quality=95)
    boxes2, engine2 = ocr_boxes(tmp)
    parsed2 = parse_sidebar_sections_from_boxes(boxes2)
    parsed2["engine"] = engine2
    parsed2["crop"] = str(tmp)
    if parsed2.get("sidebar"):
        return parsed2
    return parsed if parsed.get("sidebar") else parsed2


def merge_emain_buckets(*bucket_maps: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    """First-seen merge of E_Main section maps."""
    out = _empty_emain_buckets()
    seen: set[str] = set()
    for bm in bucket_maps:
        if not bm:
            continue
        for raw_key, syms in bm.items():
            key = normalize_section_key(str(raw_key)) or str(raw_key).upper()
            if key not in out:
                out[key] = []
            for s in syms or []:
                u = (s or "").upper().strip()
                if not u or u in seen:
                    continue
                if not is_valid_us_ticker(u, allow_unknown_long=True):
                    continue
                seen.add(u)
                out[key].append(u)
    return out


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
    mode: str = "auto",
    last_minutes: float = 10.0,
    interval_sec: float = 20.0,
    coarse_interval: float = 45.0,
    dense_interval: float = 12.0,
    max_frames: int = 90,
    min_hits: int = 2,
    use_vision: bool | None = None,
    vision_frames: int | None = None,
    upload_date: str | None = None,
    status_cb: Callable[..., None] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Primary: E_Main sidebar sections. Potent screener is optional secondary."""

    def note(**kw: Any) -> None:
        if status_cb:
            status_cb(**kw)

    ensure_dirs()
    mode = (mode or "auto").lower().strip()
    # auto / sidebar → chart+right-watchlist path; screener = Potent secondary only
    prefer_sidebar = mode in {"auto", "sidebar", "emain", "tail"}
    if mode == "auto":
        mode = "sidebar"
    if use_vision is None:
        use_vision = bool(getattr(settings, "watchlist_vision", True))
    if vision_frames is None:
        vision_frames = int(getattr(settings, "watchlist_vision_frames", 3) or 3)

    frames_subdir = "screener" if mode == "screener" else "tail"
    frames_root = FRAMES_DIR / video_id / frames_subdir
    frames_root.mkdir(parents=True, exist_ok=True)

    note(step="download_video", status="running", mode=mode)
    video_path = download_video(video_id)

    duration = video_duration_sec(video_path)
    if duration <= 0:
        duration = duration_from_transcript(video_id)
    if duration <= 0:
        raise RuntimeError(f"Cannot determine duration for {video_id}")

    if prefer_sidebar:
        # Dense tail + modest whole-VOD sample — E_Main lives on chart frames
        times = sample_screener_seconds(
            duration,
            video_id=video_id,
            coarse_interval=max(coarse_interval, 60.0),
            dense_interval=dense_interval,
            tail_minutes=max(last_minutes, 15.0),
            max_frames=max_frames,
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
    )

    engine = "none"
    frame_rows: list[dict[str, Any]] = []
    sidebar_candidates: list[dict[str, Any]] = []
    table_hits: Counter[str] = Counter()

    for i, sec in enumerate(times):
        stamp = stamp_name(sec)
        jpg = frames_root / f"{stamp}.jpg"
        try:
            if force or not jpg.exists() or jpg.stat().st_size < 2000:
                extract_frame(video_path, sec, jpg)
            # Always produce right-panel *_wl crop for sidebar OCR
            wl = frames_root / f"{stamp}_wl.jpg"
            if force and wl.exists():
                wl.unlink()
            crop_watchlist_panel(jpg, wl)

            side = detect_sidebar_from_image(jpg)
            if wl.exists() and (not side.get("symbols") or side.get("weak")):
                side2 = detect_sidebar_from_image(wl)
                if len(side2.get("symbols") or []) >= len(side.get("symbols") or []):
                    side = side2
            engine = str(side.get("engine") or engine)

            analysis = analyze_frame_ocr(jpg)
            if mode == "screener":
                col = frames_root / f"{stamp}_symcol.jpg"
                crop_symbol_column(jpg, col)
                if col.exists():
                    col_a = analyze_frame_ocr(col)
                    if len(col_a.get("table_symbols") or []) >= len(analysis.get("table_symbols") or []):
                        analysis = col_a
            for t in analysis.get("table_symbols") or []:
                table_hits[t] += 1

            row = {
                "t": format_ts(sec),
                "seconds": sec,
                "frame": f"/frames/{video_id}/{frames_root.name}/{jpg.name}",
                "local_path": str(jpg),
                "wl_crop": str(wl) if wl.exists() else None,
                "layout": analysis.get("layout"),
                "score": analysis.get("score"),
                "table_symbols": list(analysis.get("table_symbols") or []),
                "sidebar": bool(side.get("sidebar")),
                "sidebar_headers": list(side.get("headers") or []),
                "sidebar_buckets": side.get("buckets") or _empty_emain_buckets(),
                "sidebar_symbols": list(side.get("symbols") or []),
                "list_name": side.get("list_name"),
            }
            frame_rows.append(row)
            if side.get("sidebar") and (side.get("symbols") or side.get("headers")):
                sidebar_candidates.append(row)
        except Exception as e:
            frame_rows.append({"t": format_ts(sec), "seconds": sec, "error": str(e)})
        if i % 3 == 0:
            note(step="extract_frames", status="running", done=i + 1, total=len(times), mode=mode)

    vod_date = resolve_vod_date(video_id, hint=upload_date)
    buckets = _empty_emain_buckets()
    source_tag = "none"
    list_name = "E_Main"
    vision_meta: dict[str, Any] = {"available": False, "symbols": [], "buckets": {}, "reads": []}

    # --- Primary: merge OCR sidebar hits ---
    if prefer_sidebar and sidebar_candidates:
        note(step="sidebar_emain", status="running", candidates=len(sidebar_candidates))
        ranked = sorted(
            sidebar_candidates,
            key=lambda r: (
                len(r.get("sidebar_symbols") or []),
                len(r.get("sidebar_headers") or []),
            ),
            reverse=True,
        )
        merged = merge_emain_buckets(*[r.get("sidebar_buckets") or {} for r in ranked[:8]])
        if sum(len(v) for v in merged.values()) >= 3:
            buckets = merged
            source_tag = "sidebar_ocr"
            list_name = next(
                (r.get("list_name") for r in ranked if r.get("list_name")),
                "E_Main",
            ) or "E_Main"

    # --- Vision sidebar assist ---
    if use_vision and prefer_sidebar:
        note(step="vision_sidebar", status="running")
        from .screener_vision import read_sidebar_sections, vision_available

        avail = vision_available()
        ranked_paths = [
            Path(r["wl_crop"] or r["local_path"])
            for r in sorted(
                [x for x in frame_rows if x.get("local_path") and not x.get("error")],
                key=lambda r: len(r.get("sidebar_symbols") or []),
                reverse=True,
            )[: max(vision_frames, 3)]
        ]
        if avail.get("ok") and ranked_paths:
            reads = []
            vis_buckets = _empty_emain_buckets()
            for p in ranked_paths[:vision_frames]:
                if not p.exists():
                    continue
                result = read_sidebar_sections(p)
                reads.append({"path": str(p), **result})
                if result.get("sidebar"):
                    vis_buckets = merge_emain_buckets(vis_buckets, result.get("buckets") or {})
            vision_meta = {
                "available": True,
                "backend": avail.get("backend"),
                "model": avail.get("model"),
                "buckets": vis_buckets,
                "symbols": (
                    vis_buckets["INDEXES"]
                    + vis_buckets["LONGS"]
                    + vis_buckets["SHORTS"]
                    + vis_buckets["FOCUS"]
                    + vis_buckets["TRACKING"]
                ),
                "reads": reads,
            }
            # Prefer vision when it recovered a fuller E_Main than OCR
            if sum(len(v) for v in vis_buckets.values()) > sum(len(v) for v in buckets.values()):
                buckets = vis_buckets
                source_tag = "sidebar_vision"
            elif source_tag == "none" and sum(len(v) for v in vis_buckets.values()) >= 3:
                buckets = vis_buckets
                source_tag = "sidebar_vision"
        else:
            vision_meta = {
                "available": bool(avail.get("ok")),
                "backend": avail.get("backend"),
                "model": avail.get("model"),
                "symbols": [],
                "buckets": _empty_emain_buckets(),
                "reads": [],
                "note": (
                    "Vision skipped — set TUBEON_OPENAI_API_KEY for E_Main sidebar read"
                ),
            }
        note(
            step="vision_sidebar",
            status="done",
            vision_symbols=len(vision_meta.get("symbols") or []),
            source=source_tag,
        )

    # --- Secondary Potent path (explicit screener mode OR sidebar empty) ---
    potent_symbols: list[str] = []
    if mode == "screener" or (
        prefer_sidebar and sum(len(v) for v in buckets.values()) < 3 and use_vision
    ):
        from .screener_vision import read_best_screener_frames, vision_available

        avail = vision_available()
        paths = [
            Path(r["local_path"])
            for r in frame_rows
            if r.get("local_path") and r.get("layout") == "screener_table"
        ][:vision_frames]
        if not paths:
            paths = [Path(r["local_path"]) for r in frame_rows if r.get("local_path")][:vision_frames]
        if mode == "screener" and avail.get("ok") and paths:
            pot = read_best_screener_frames(paths, max_frames=vision_frames)
            potent_symbols = list(pot.get("symbols") or [])
            vision_meta = {**vision_meta, "potent": pot}
            if prefer_sidebar is False:
                source_tag = "potent_vision"
        elif mode == "screener":
            potent_symbols = [s for s, _ in table_hits.most_common() if is_valid_us_ticker(s)]
            source_tag = "potent_ocr"

    symbols = (
        buckets["INDEXES"]
        + buckets["LONGS"]
        + buckets["SHORTS"]
        + buckets["FOCUS"]
        + buckets["TRACKING"]
    )
    emain_ok = sum(len(v) for v in buckets.values()) >= 3 and prefer_sidebar

    items: list[dict[str, Any]] = []
    for sec, syms in buckets.items():
        for sym in syms:
            items.append(
                {
                    "symbol": sym,
                    "section": sec,
                    "tv": tv_symbol(sym),
                    "known": is_valid_us_ticker(sym),
                    "source": source_tag,
                }
            )

    if emain_ok:
        tv_txt = format_emain_watchlist_txt(buckets)
        strategy = (
            "E_Main sidebar primary: INDEXES/LONGS/SHORTS/FOCUS/TRACKING → "
            "one TV Upload file with short ###SECTION headers; "
            f"watchlist name = Martin Luk {vod_date} E_Main"
        )
    elif mode == "screener" and potent_symbols:
        tv_txt = format_dated_watchlist_txt(
            potent_symbols, date_iso=vod_date, video_id=video_id, view_name="Potent"
        )
        symbols = potent_symbols
        strategy = "Potent/Leader secondary only (explicit screener mode)"
        source_tag = source_tag or "potent"
    else:
        tv_txt = format_emain_watchlist_txt(buckets) if any(buckets.values()) else ""
        strategy = (
            "E_Main sidebar preferred but no sections found — "
            "check frames / set TUBEON_OPENAI_API_KEY"
        )

    best_side = max(
        sidebar_candidates,
        key=lambda r: len(r.get("sidebar_symbols") or []),
        default=None,
    )

    report: dict[str, Any] = {
        "video_id": video_id,
        "vod_date": vod_date,
        "list_name": f"Martin Luk {vod_date} {list_name}",
        "mode": mode,
        "strategy": strategy,
        "symbol_source": source_tag,
        "duration_sec": round(duration, 1),
        "ocr_engine": engine,
        "frame_count": len(frame_rows),
        "sidebar_frame_count": len(sidebar_candidates),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "buckets": buckets,
        "indexes": buckets["INDEXES"],
        "longs": buckets["LONGS"],
        "shorts": buckets["SHORTS"],
        "focus": buckets["FOCUS"],
        "tracking": buckets["TRACKING"],
        "potent_secondary": potent_symbols,
        "items": items,
        "vision": vision_meta,
        "best_sidebar_frame": {
            "t": (best_side or {}).get("t"),
            "seconds": (best_side or {}).get("seconds"),
            "frame": (best_side or {}).get("frame"),
            "headers": (best_side or {}).get("sidebar_headers"),
            "symbols": (best_side or {}).get("sidebar_symbols"),
        }
        if best_side
        else None,
        "frames": frame_rows,
        "tradingview_txt": tv_txt,
        "tradingview_note": (
            f"Upload into watchlist named «Martin Luk {vod_date} E_Main». "
            "File body uses short ###INDEXES/###LONGS/… sections. Essential+; no TV API."
        ),
    }

    local_json = FRAMES_DIR / video_id / "watchlist.json"
    local_json.parent.mkdir(parents=True, exist_ok=True)
    local_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_json = SUMMARY_DIR / f"{video_id}.watchlist.json"
    slim_keys = (
        "video_id",
        "vod_date",
        "list_name",
        "mode",
        "strategy",
        "symbol_source",
        "duration_sec",
        "ocr_engine",
        "frame_count",
        "sidebar_frame_count",
        "symbol_count",
        "symbols",
        "buckets",
        "indexes",
        "longs",
        "shorts",
        "focus",
        "tracking",
        "items",
        "vision",
        "best_sidebar_frame",
        "tradingview_txt",
        "tradingview_note",
    )
    slim = {k: report[k] for k in slim_keys if k in report}
    summary_json.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")

    WATCHLIST_OUT_DIR.mkdir(parents=True, exist_ok=True)
    dated_name = list_filename(vod_date, list_name="E_Main")
    video_txt_path = WATCHLIST_OUT_DIR / f"{video_id}.txt"
    dated_txt_path: Path | None = None
    if emain_ok or any(buckets.values()):
        tv_path = write_tradingview_txt(
            video_txt_path,
            buckets=buckets,
            date_iso=vod_date,
            video_id=video_id,
            list_name="E_Main",
            emain=True,
            also_dated_filename=True,
        )
        # CDP upload listStem = dated filename stem (Martin_Luk_YYYY-MM-DD_E_Main)
        dated_txt_path = WATCHLIST_OUT_DIR / dated_name
        if not dated_txt_path.exists():
            dated_txt_path.write_text(tv_txt, encoding="utf-8")
        tv_path = dated_txt_path
    else:
        tv_path = write_tradingview_txt(
            video_txt_path,
            symbols=potent_symbols or symbols,
            date_iso=vod_date,
            video_id=video_id,
            view_name="Potent",
            emain=False,
            also_dated_filename=False,
        )

    md_path = WATCHLIST_OUT_DIR / f"{video_id}.md"
    md_lines = [
        f"# Martin Luk E_Main — `{video_id}`",
        "",
        f"- Watchlist name: **Martin Luk {vod_date} E_Main**",
        f"- Mode: **{mode}** | Source: **{source_tag}** | OCR: {engine}",
        f"- INDEXES {len(buckets['INDEXES'])} | LONGS {len(buckets['LONGS'])} | "
        f"SHORTS {len(buckets['SHORTS'])} | FOCUS {len(buckets['FOCUS'])} | "
        f"TRACKING {len(buckets['TRACKING'])}",
        "",
        "## Sections",
        "",
    ]
    for sec in ("INDEXES", "LONGS", "SHORTS", "FOCUS", "TRACKING"):
        md_lines += [f"### {sec}", "", ", ".join(buckets[sec]) or "—", ""]
    md_lines += ["## TradingView import", "", "```", tv_txt.strip(), "```", ""]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    report["paths"] = {
        "watchlist_json": str(local_json),
        "summary_json": str(summary_json),
        "tradingview_txt": str(tv_path),
        "tradingview_txt_video": str(video_txt_path),
        "tradingview_txt_dated": str(dated_txt_path) if dated_txt_path else None,
        "list_stem": Path(tv_path).stem,
        "markdown": str(md_path),
    }
    note(
        step="done",
        status="done",
        mode=mode,
        symbol_count=len(symbols),
        source=source_tag,
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
