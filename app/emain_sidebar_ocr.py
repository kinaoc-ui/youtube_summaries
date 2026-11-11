# -*- coding: utf-8 -*-
"""Read a Martin E_Main sidebar screenshot by template-matching tickers.

Generic OCR (RapidOCR, Tesseract, Windows.Media.Ocr) cannot read TradingView's
small antialiased watchlist font. This module finds the symbol column, splits
rows, and scores each row against section headers plus a US-ticker universe
rendered in common Windows fonts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

SECTION_ORDER = ("INDEXES", "LONGS", "SHORTS", "FOCUS", "TRACKING")

# Always-on labels and names Martin uses even if a ticker file is short.
CORE_TICKERS = {
    "QQQ", "SPY", "IWM", "DIA", "TQQQ", "SQQQ", "SOXL", "SOXS",
    "USO", "SOXQ", "SOXX", "SMH", "UVXY", "VIXY", "SSPC", "SLV", "GLD",
    "AXTI", "GEV", "BMNR", "COIN", "CRWD", "TSLA", "NVDA", "AMD", "AAPL",
    "MSFT", "AMZN", "META", "GOOG", "GOOGL", "NFLX", "AVGO", "ARM",
    "DRAM", "SPCX", "SNY", "SKHY", "XYZ", "BE", "EWZ", "XLE", "XLF",
    "HYG", "TLT", "UNG", "BITO", "MSTR", "HOOD", "PLTR", "BABA",
}

FONT_FILES = (
    "bahnschrift.ttf",
    "segoeui.ttf",
    "segoeuisl.ttf",
    "segoeuib.ttf",
    "arial.ttf",
    "arialbd.ttf",
    "calibri.ttf",
    "calibrib.ttf",
    "trebuc.ttf",
    "trebucbd.ttf",
    "tahoma.ttf",
    "tahomabd.ttf",
    "verdana.ttf",
    "verdanab.ttf",
    "candara.ttf",
    "corbel.ttf",
    "consola.ttf",
    "cour.ttf",
    "framd.ttf",
    "gadugi.ttf",
    "malgun.ttf",
    "micross.ttf",
    "sserife.fon",  # may fail; ignored
)


def _ticker_universe() -> list[str]:
    ticks: set[str] = set(CORE_TICKERS)
    try:
        from app.video_check import KNOWN_TICKERS

        ticks.update(str(t).upper() for t in KNOWN_TICKERS)
    except Exception:
        pass
    try:
        from app.us_tickers import US_TICKERS  # type: ignore

        ticks.update(str(t).upper() for t in US_TICKERS)
    except Exception:
        pass
    try:
        from app.us_tickers import ALL_TICKERS  # type: ignore

        ticks.update(str(t).upper() for t in ALL_TICKERS)
    except Exception:
        pass
    try:
        from app.us_tickers import load_us_tickers

        loaded = load_us_tickers()
        if isinstance(loaded, dict):
            loaded = loaded.keys()
        ticks.update(str(t).upper() for t in loaded)
    except Exception:
        pass
    out = []
    for t in ticks:
        if t.isalpha() and 1 <= len(t) <= 5:
            out.append(t)
    return sorted(set(out))


def _font_paths() -> list[Path]:
    roots = [Path(r"C:\Windows\Fonts"), Path("/usr/share/fonts")]
    found: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for name in FONT_FILES:
            p = root / name
            if p.is_file() and p.name.lower() not in seen:
                found.append(p)
                seen.add(p.name.lower())
        for pat in ("*Inter*.ttf", "*inter*.ttf", "*PlexSans*.ttf", "*Roboto*.ttf", "*Din*.ttf"):
            for p in root.glob(pat):
                if p.is_file() and p.name.lower() not in seen:
                    found.append(p)
                    seen.add(p.name.lower())
    return found


def _luma(im: Image.Image) -> np.ndarray:
    return np.asarray(im.convert("RGB"), dtype=np.float32).mean(axis=2)


def _stretch(gray: np.ndarray, lo: float = 8.0, hi: float = 90.0) -> np.ndarray:
    """Boost dim gray-on-black watchlist text into a 0..255 range."""
    out = (gray.astype(np.float32) - lo) * (255.0 / max(1.0, hi - lo))
    return np.clip(out, 0, 255).astype(np.uint8)


def find_symbol_column(im: Image.Image) -> tuple[int, int, int, int]:
    """Locate the ticker-name column (after icons, before prices)."""
    rgb = np.asarray(im.convert("RGB"), dtype=np.int16)
    h, w, _ = rgb.shape
    y0b, y1b = int(h * 0.28), int(h * 0.62)
    band = rgb[y0b:y1b]
    luma = band.mean(axis=2)
    chroma = band.max(axis=2) - band.min(axis=2)

    def _smooth(v: np.ndarray, k: int = 7) -> np.ndarray:
        ker = np.ones(k, dtype=np.float64) / k
        return np.convolve(v.astype(np.float64), ker, mode="same")

    v_luma = _smooth(luma.mean(axis=0))
    v_chr = _smooth(chroma.mean(axis=0))

    a, b = int(w * 0.08), max(int(w * 0.72), int(w * 0.08) + 20)
    icon_x = a + int(np.argmax(v_chr[a:b]))
    peak_c = float(v_chr[icon_x])
    icon_r = icon_x
    while icon_r < b and v_chr[icon_r] > max(10.0, peak_c * 0.35):
        icon_r += 1
    # Skip residual icon halo: keep walking while chroma stays above text chroma.
    text_chr = float(np.median(v_chr[min(w - 1, icon_r + 8) : min(w, icon_r + 40)])) if icon_r + 8 < w else 6.0
    while icon_r < b and v_chr[icon_r] > text_chr + 4:
        icon_r += 1
    x0 = min(w - 8, icon_r + 4)

    # Luma peaks after x0: 1) symbols  2) prices  3) % change
    sl = v_luma.copy()
    peaks: list[int] = []
    for x in range(max(0, x0 + 3), w - 3):
        if sl[x] < 8:
            continue
        if sl[x] >= sl[x - 2] and sl[x] >= sl[x + 2] and sl[x] >= sl[x - 1] and sl[x] >= sl[x + 1]:
            if not peaks or x - peaks[-1] >= 18:
                peaks.append(x)
    if len(peaks) >= 2:
        p_price = peaks[1]
        floor = sl[p_price] * 0.40
        x1 = p_price
        while x1 > peaks[0] and sl[x1] > floor:
            x1 -= 1
        # x1 is now the left edge of the price column; the valley
        # to the left is kept so 8-letter headers like TRACKING fit.
    elif len(peaks) == 1:
        # No clear price peak: take a generous width for headers.
        x1 = min(w, peaks[0] + max(70, int(w * 0.18)))
    else:
        x1 = min(w, x0 + max(70, int(w * 0.22)))
    x1 = min(w, max(x0 + 48, x1))

    # Vertical extent: skip the details card in the lower third.
    full = rgb.mean(axis=2)
    hproj = full[:, x0:x1].mean(axis=1) if x1 > x0 else full.mean(axis=1)
    y_bottom = int(h * 0.78)
    mid_mean = float(hproj[int(h * 0.35) : int(h * 0.60)].mean()) if h > 10 else 0.0
    for y in range(int(h * 0.68), int(h * 0.95)):
        if y + 40 < h and hproj[y : y + 40].mean() > max(18.0, mid_mean * 1.8):
            y_bottom = y
            break
    y_top = int(h * 0.10)
    return max(0, x0), max(0, y_top), min(w, x1), min(h, y_bottom)


def iter_text_rows(col: np.ndarray) -> list[tuple[int, int]]:
    """Return (y0, y1) local to the column image for each text row."""
    if col.size == 0:
        return []
    stretched = _stretch(col)
    proj = stretched.mean(axis=1).astype(np.float32)
    kernel = np.ones(3, dtype=np.float32) / 3.0
    smooth = np.convolve(proj, kernel, mode="same")
    # Ticker rows are clearly brighter than the dark padding.
    floor = max(6.0, float(np.percentile(smooth, 35)) * 1.4)
    rows: list[tuple[int, int]] = []
    inside = False
    start = 0
    for y, v in enumerate(smooth):
        if not inside and v >= floor:
            start = y
            inside = True
        elif inside and v < floor:
            if y - start >= 6:
                rows.append((start, y))
            inside = False
    if inside and len(smooth) - start >= 6:
        rows.append((start, len(smooth)))
    if not rows:
        return []
    heights = [b - a for a, b in rows]
    med = float(np.median(heights))
    # Drop hairline separators; keep dim section headers (slightly shorter).
    kept: list[tuple[int, int]] = []
    for a, b in rows:
        hh = b - a
        if hh < max(6, med * 0.35):
            continue
        # merge with previous if the gap is tiny (split highlight boxes)
        if kept and a - kept[-1][1] <= 3 and hh + (kept[-1][1] - kept[-1][0]) < med * 2.4:
            kept[-1] = (kept[-1][0], b)
        else:
            kept.append((a, b))
    return kept


_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont | None:
    key = (str(path), size)
    if key in _font_cache:
        return _font_cache[key]
    try:
        font = ImageFont.truetype(str(path), size=size)
    except Exception:
        return None
    _font_cache[key] = font
    return font


def render_word(word: str, font_path: Path, target_h: int) -> np.ndarray | None:
    """Render white-on-black text whose glyph box is about target_h pixels tall."""
    if target_h < 6:
        return None
    # Trial size: cap-height is usually ~0.7 of nominal size.
    size = max(8, int(round(target_h / 0.72)))
    font = _load_font(font_path, size)
    if font is None:
        return None
    tmp = Image.new("L", (max(8, size * (len(word) + 2)), size * 3), 0)
    draw = ImageDraw.Draw(tmp)
    draw.text((2, 2), word, font=font, fill=255)
    arr = np.asarray(tmp)
    ys, xs = np.where(arr > 20)
    if len(xs) < 5:
        return None
    glyph = arr[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    gh, gw = glyph.shape
    if gh < 4 or gw < 3:
        return None
    if gh != target_h:
        new_w = max(3, int(round(gw * (target_h / gh))))
        glyph = cv2.resize(glyph, (new_w, target_h), interpolation=cv2.INTER_AREA)
    return glyph


def ncc(row: np.ndarray, tmpl: np.ndarray) -> float:
    if tmpl is None or tmpl.size == 0 or row.size == 0:
        return -1.0
    rh, rw = row.shape
    th, tw = tmpl.shape
    if th > rh or tw > rw:
        # Scale template down slightly to fit, but not below 80% width.
        scale = min(rh / th, rw / tw)
        if scale < 0.8:
            return -1.0
        tmpl = cv2.resize(
            tmpl,
            (max(3, int(tw * scale)), max(3, int(th * scale))),
            interpolation=cv2.INTER_AREA,
        )
        th, tw = tmpl.shape
        if th > rh or tw > rw:
            return -1.0
    # Pad the row a few pixels so the template can slide.
    pad_y = max(0, 2)
    pad_x = max(2, tw // 8)
    padded = cv2.copyMakeBorder(row, pad_y, pad_y, pad_x, pad_x, cv2.BORDER_CONSTANT, value=0)
    if padded.shape[0] < th or padded.shape[1] < tw:
        return -1.0
    try:
        res = cv2.matchTemplate(padded, tmpl, cv2.TM_CCOEFF_NORMED)
    except cv2.error:
        return -1.0
    return float(res.max())


def _ink_bbox(row: np.ndarray) -> tuple[int, int, int, int] | None:
    """Tight bbox of bright pixels in a row image (x0,y0,x1,y1)."""
    mask = row > 25
    ys, xs = np.where(mask)
    if len(xs) < 8:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def recognize_sidebar_image(
    im: Image.Image,
    *,
    debug_dir: Path | None = None,
) -> tuple[dict[str, list[str]], str]:
    """Return (section buckets, debug text) from an E_Main sidebar photo."""
    try:
        from app.watchlist_extract import tv_symbol
    except Exception:
        def tv_symbol(tok: str) -> str:  # type: ignore
            return tok

    gray = np.asarray(im.convert("L"))
    x0, y0, x1, y1 = find_symbol_column(im)
    col = _stretch(gray[y0:y1, x0:x1], lo=8, hi=95)
    rows = iter_text_rows(col)
    fonts = _font_paths()
    tickers = _ticker_universe()
    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        vis = im.convert("RGB").copy()
        from PIL import ImageDraw as _ID

        d = _ID.Draw(vis)
        d.rectangle([x0, y0, x1, y1], outline=(0, 255, 0))
        for a, b in rows:
            d.rectangle([x0, y0 + a, x1, y0 + b], outline=(255, 180, 0))
        vis.save(debug_dir / "symbol_column.png")
        Image.fromarray(col).save(debug_dir / "symbol_col_stretch.png")

    if not rows or not fonts:
        return {k: [] for k in SECTION_ORDER}, "no-rows-or-fonts"

    # Calibrate font + size on each row independently is expensive; first
    # estimate a global font from header words and very common tickers.
    probe_words = list(SECTION_ORDER) + ["QQQ", "SPY", "IWM", "USO", "GLD", "SLV", "COIN"]
    font_scores: list[tuple[float, Path]] = []
    # Collect a few high-ink rows for calibration.
    probe_rows: list[np.ndarray] = []
    ink_heights: list[int] = []
    for a, b in rows:
        row = col[max(0, a) : b]
        bbox = _ink_bbox(row)
        if not bbox:
            continue
        xa, ya, xb, yb = bbox
        ink_h = yb - ya
        if ink_h < 6 or (xb - xa) < 8:
            continue
        probe_rows.append(row)
        ink_heights.append(ink_h)
        if len(probe_rows) >= 14:
            break
    if not probe_rows:
        return {k: [] for k in SECTION_ORDER}, "no-ink-rows"
    target_h = int(round(float(np.median(ink_heights))))

    for fp in fonts:
        best = 0.0
        # Render probes once; score against every calibration row, keep max.
        renders = {w: render_word(w, fp, target_h) for w in probe_words}
        for row in probe_rows:
            for tmpl in renders.values():
                if tmpl is None:
                    continue
                best = max(best, ncc(row, tmpl))
        font_scores.append((best, fp))
    font_scores.sort(key=lambda t: t[0], reverse=True)
    best_font = font_scores[0][1] if font_scores else fonts[0]
    cal_note = ", ".join(f"{p.name}:{s:.3f}" for s, p in font_scores[:5])

    # Pre-render candidates at the calibrated height (and a nearby size).
    heights = sorted({max(6, target_h + d) for d in (-2, 0, 2)})
    header_tmpls: dict[str, list[np.ndarray]] = {h: [] for h in SECTION_ORDER}
    ticker_tmpls: dict[str, list[np.ndarray]] = {}
    for ht in heights:
        for hdr in SECTION_ORDER:
            g = render_word(hdr, best_font, ht)
            if g is not None:
                header_tmpls[hdr].append(g)
        for tok in tickers:
            g = render_word(tok, best_font, ht)
            if g is not None:
                ticker_tmpls.setdefault(tok, []).append(g)

    recognized: list[tuple[str, str, float]] = []  # kind, text, score
    lines_out: list[str] = []
    for a, b in rows:
        row = col[max(0, a) : b]
        bbox = _ink_bbox(row)
        if not bbox:
            continue
        xa, ya, xb, yb = bbox
        ink_w = xb - xa
        ink_h = yb - ya
        if ink_h < 5 or ink_w < 6:
            continue
        # Header first: headers are longer than most tickers.
        hdr_best = ("", -1.0)
        for hdr, tmpls in header_tmpls.items():
            for tmpl in tmpls:
                sc = ncc(row, tmpl)
                if sc > hdr_best[1]:
                    hdr_best = (hdr, sc)
        tok_best = ("", -1.0)
        # Width gate: only tickers whose template width is close to ink width.
        lo_w, hi_w = ink_w * 0.62, ink_w * 1.45
        for tok, tmpls in ticker_tmpls.items():
            for tmpl in tmpls:
                tw = tmpl.shape[1]
                if tw < lo_w or tw > hi_w:
                    continue
                sc = ncc(row, tmpl)
                if sc > tok_best[1]:
                    tok_best = (tok, sc)

        # Prefer a strong header; otherwise a ticker; ignore weak noise.
        if hdr_best[1] >= 0.62 and hdr_best[1] >= tok_best[1] - 0.05:
            recognized.append(("header", hdr_best[0], hdr_best[1]))
            lines_out.append(f"{hdr_best[0]}  [{hdr_best[1]:.3f} header]")
        elif tok_best[1] >= 0.62:
            recognized.append(("ticker", tok_best[0], tok_best[1]))
            lines_out.append(f"{tok_best[0]}  [{tok_best[1]:.3f}]")
        else:
            lines_out.append(
                f"? ink={ink_w}x{ink_h} hdr={hdr_best[0]}:{hdr_best[1]:.3f} "
                f"tok={tok_best[0]}:{tok_best[1]:.3f}"
            )

    buckets: dict[str, list[str]] = {k: [] for k in SECTION_ORDER}
    current: str | None = None
    for kind, text, _sc in recognized:
        if kind == "header":
            current = text
            continue
        if current is None:
            # Tickers before the first header are ignored (chrome / E_MAIN).
            continue
        sym = tv_symbol(text)
        if sym not in buckets[current]:
            buckets[current].append(sym)

    debug = (
        f"col=({x0},{y0})-({x1},{y1}) rows={len(rows)} font={best_font.name} "
        f"h={target_h} cal={cal_note}\n" + "\n".join(lines_out)
    )
    if debug_dir is not None:
        (debug_dir / "recognize.txt").write_text(debug, encoding="utf-8")
    return buckets, debug


def recognize_sidebar_path(path: Path, debug_dir: Path | None = None):
    im = Image.open(path).convert("RGB")
    return recognize_sidebar_image(im, debug_dir=debug_dir)


if __name__ == "__main__":
    import sys

    p = Path(sys.argv[1])
    dbg = Path(sys.argv[2]) if len(sys.argv) > 2 else p.parent / "ocr_debug"
    buckets, debug = recognize_sidebar_path(p, debug_dir=dbg)
    print(debug)
    print("BUCKETS", buckets)
