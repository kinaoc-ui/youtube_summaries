# -*- coding: utf-8 -*-
"""TradingView watchlist file export (Upload list… .txt).

TradingView has no public API for programmatic watchlist updates.
Official import path (paid Essential+): Watchlist name → Upload list…
File must be .txt with EXCHANGE:SYMBOL entries, comma-separated.
Optional section headers: ###SectionName

Martin's primary list is the right sidebar **E_Main**.
One watchlist file with short ### section headers:

  ###INDEXES
  NASDAQ:QQQ,...
  ###LONGS
  ...

The dated watchlist *name* is metadata / filename, e.g.
  Martin Luk 2026-10-28 E_Main
  → outputs/watchlists/Martin_Luk_2026-10-28_E_Main.txt
It is NOT repeated inside every ### header.

Potent/Leader screener is optional secondary only.

Docs: https://www.tradingview.com/support/solutions/43000487233-how-to-import-or-export-a-watchlist/
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .emain_eligibility import canonical_list_date

EXCHANGE_FOR_TICKER: dict[str, str] = {
    "AAPL": "NASDAQ",
    "MSFT": "NASDAQ",
    "AMZN": "NASDAQ",
    "GOOGL": "NASDAQ",
    "GOOG": "NASDAQ",
    "META": "NASDAQ",
    "NVDA": "NASDAQ",
    "AMD": "NASDAQ",
    "TSLA": "NASDAQ",
    "AVGO": "NASDAQ",
    "ARM": "NASDAQ",
    "CRWD": "NASDAQ",
    "DDOG": "NASDAQ",
    "PATH": "NYSE",
    "OKTA": "NASDAQ",
    "CRM": "NYSE",
    "TWLO": "NYSE",
    "PLTR": "NASDAQ",
    "COIN": "NASDAQ",
    "HOOD": "NASDAQ",
    "MDB": "NASDAQ",
    "SNOW": "NYSE",
    "NET": "NYSE",
    "ZS": "NASDAQ",
    "PANW": "NASDAQ",
    "FTNT": "NASDAQ",
    "IBM": "NYSE",
    "ORCL": "NYSE",
    "HPQ": "NYSE",
    "GLW": "NYSE",
    "WDC": "NASDAQ",
    "MU": "NASDAQ",
    "TSM": "NYSE",
    "BABA": "NYSE",
    "QQQ": "NASDAQ",
    "SPY": "AMEX",
    "DIA": "AMEX",
    "IWM": "AMEX",
    "VIX": "CBOE",
    "SOXX": "NASDAQ",
    "SOXL": "AMEX",
    "SOXS": "AMEX",
    "USD": "AMEX",  # ProShares Ultra Semiconductors
    "USO": "AMEX",
    "SSPC": "CBOE",
    "SLV": "AMEX",
    "GLD": "AMEX",
    "BMNR": "NYSE",
    "DRAM": "CBOE",
    "UVXY": "AMEX",
    "SNDK": "NASDAQ",
    "SPCX": "NASDAQ",
    "GEV": "NYSE",
    "VRT": "NYSE",
    "AXTI": "NASDAQ",
    "SKHY": "NASDAQ",
    "SQQQ": "NASDAQ",
    "TQQQ": "NASDAQ",
    "IGV": "AMEX",
    "GDX": "AMEX",
    "SMCI": "NASDAQ",
    "MSTR": "NASDAQ",
    "MARA": "NASDAQ",
    "RIOT": "NASDAQ",
    "RKLB": "NASDAQ",
    "ASTS": "NASDAQ",
    "SMR": "NYSE",
    "OKLO": "NYSE",
    "BE": "NYSE",
    "CLS": "NYSE",
    "ALAB": "NASDAQ",
    "CRWV": "NASDAQ",
    "FIG": "NYSE",
    "FROG": "NASDAQ",
    "TEM": "NASDAQ",
    "RBRK": "NYSE",
    "APLD": "NASDAQ",
    "IREN": "NASDAQ",
    "QBTS": "NYSE",
    "RGTI": "NASDAQ",
    "IONQ": "NYSE",
    "QUBT": "NASDAQ",
    "NVTS": "NASDAQ",
    "ONDS": "NASDAQ",
    "USAR": "NASDAQ",
    "AOI": "NASDAQ",
    "OSK": "NYSE",
    "HIMS": "NYSE",
    "XYZ": "NYSE",
    "CRCL": "NYSE",
    "SHOP": "NYSE",
    "SE": "NYSE",
    "ARRY": "NASDAQ",
    "GILD": "NASDAQ",
    "AXSM": "NASDAQ",
    "GNS": "NYSE",
    "ICLR": "NASDAQ",
    "EVR": "NYSE",
    "WMG": "NASDAQ",
    "TXG": "NASDAQ",
    "BYON": "NYSE",
    "TWST": "NASDAQ",
    "PPG": "NYSE",
    "CRL": "NYSE",
    "FRO": "NYSE",
    "ACN": "NYSE",
    "PNT": "NASDAQ",
    "REVV": "NASDAQ",
    "MRNA": "NASDAQ",
    "NTRA": "NASDAQ",
    "HCA": "NYSE",
    "ETSY": "NASDAQ",
    "IQV": "NYSE",
    "SOFI": "NASDAQ",
    "GH": "NASDAQ",
    "EXAS": "NASDAQ",
    "AKAM": "NASDAQ",
    "Z": "NASDAQ",
    "MNSO": "NYSE",
    "BRZE": "NASDAQ",
    "DOGEUSD": "CRYPTO",
}

DEFAULT_EXCHANGE = "NASDAQ"

EMAIN_SECTION_ORDER = ("INDEXES", "LONGS", "SHORTS", "FOCUS", "TRACKING")

SECTION_ALIASES: dict[str, str] = {
    "INDEXES": "INDEXES",
    "INDICES": "INDEXES",
    "INDEX": "INDEXES",
    "LONGS": "LONGS",
    "LONG": "LONGS",
    "L": "LONGS",
    "SHORTS": "SHORTS",
    "SHORT": "SHORTS",
    "S": "SHORTS",
    "FOCUS": "FOCUS",
    "HIGHLIGHT": "FOCUS",
    "TRACKING": "TRACKING",
    "TRACK": "TRACKING",
}


def tv_symbol(ticker: str, exchange: str | None = None) -> str:
    """Return EXCHANGE:TICKER for TradingView upload."""
    t = (ticker or "").upper().strip()
    if not t:
        raise ValueError("empty ticker")
    if ":" in t:
        return t
    if t == "DOGEUSD":
        return "CRYPTO:DOGEUSD"
    # Optional Samsung alias — E_Main TRACKING uses NASDAQ:SKHY per Luk
    if t == "SKHY" and exchange and exchange.upper() == "KRX":
        return "KRX:000660"
    ex = (exchange or EXCHANGE_FOR_TICKER.get(t) or DEFAULT_EXCHANGE).upper()
    return f"{ex}:{t}"


def list_display_name(
    *,
    date_iso: str,
    list_name: str = "E_Main",
    prefix: str = "Martin Luk",
) -> str:
    """Watchlist name shown in TV / used as filename stem."""
    d = (date_iso or "").strip() or "unknown-date"
    lst = (list_name or "").strip() or "E_Main"
    return f"{prefix} {d} {lst}"


def list_filename(date_iso: str, list_name: str = "E_Main", prefix: str = "Martin Luk") -> str:
    """Safe filename for dated E_Main export."""
    raw = list_display_name(date_iso=date_iso, list_name=list_name, prefix=prefix)
    return raw.replace(" ", "_") + ".txt"


def normalize_section_key(raw: str) -> str | None:
    key = (raw or "").strip().upper().replace(" ", "")
    return SECTION_ALIASES.get(key)


def section_name(
    *,
    date_iso: str | None = None,
    list_name: str = "E_Main",
    section: str,
    prefix: str = "Martin Luk",
    video_id: str | None = None,
    short: bool = True,
) -> str:
    """Section header body (without ###). Default: short INDEXES / LONGS / …"""
    sec = normalize_section_key(section) or (section or "LIST").strip().upper()
    if short:
        return sec
    # Legacy long form (avoid for E_Main body)
    d = (date_iso or "").strip() or "unknown-date"
    lst = (list_name or "").strip() or "E_Main"
    _ = video_id
    return f"{prefix} {d} {lst} {sec}"


def _dedupe_tv_symbols(
    symbols: Sequence[str],
    *,
    exchanges: dict[str, str] | None = None,
    global_seen: set[str] | None = None,
) -> list[str]:
    exchanges = exchanges or {}
    seen = global_seen if global_seen is not None else set()
    tv_syms: list[str] = []
    for raw in symbols:
        s = (raw or "").strip()
        if not s:
            continue
        if ":" in s:
            entry = s.upper()
        else:
            tick = s.upper()
            entry = tv_symbol(tick, exchanges.get(tick))
        if entry in seen:
            continue
        seen.add(entry)
        tv_syms.append(entry)
    return tv_syms


def format_watchlist_txt(
    symbols: Sequence[str] | None = None,
    *,
    section: str | None = None,
    exchanges: dict[str, str] | None = None,
    sections: Mapping[str, Sequence[str]] | None = None,
) -> str:
    """Build TradingView Upload-list TXT.

    - ``sections`` dict → multi ``###SECTION`` blocks in one file (E_Main)
    - else single optional ``###section`` + comma-separated symbols
    """
    if sections is not None:
        return format_emain_watchlist_txt(sections, exchanges=exchanges)

    parts: list[str] = []
    if section:
        parts.append(f"###{section}")
    parts.append(",".join(_dedupe_tv_symbols(list(symbols or []), exchanges=exchanges)))
    return "\n".join(parts) + ("\n" if parts else "")


def format_emain_watchlist_txt(
    buckets: Mapping[str, Sequence[str]],
    *,
    exchanges: dict[str, str] | None = None,
    include_empty: bool = False,
    date_iso: str | None = None,
    list_name: str = "E_Main",
    prefix: str = "Martin Luk",
    **_ignored: object,
) -> str:
    """Multi-section body with short ###INDEXES / ###LONGS / … headers.

    ``date_iso`` / ``list_name`` accepted for API compat but not written into
    section headers (dated name lives on the watchlist / filename).
    """
    _ = (date_iso, list_name, prefix)
    by_norm: dict[str, list[str]] = {s: [] for s in EMAIN_SECTION_ORDER}
    extra: list[tuple[str, list[str]]] = []
    for raw_key, syms in (buckets or {}).items():
        norm = normalize_section_key(str(raw_key))
        if norm:
            by_norm[norm] = list(syms or [])
        else:
            key = (str(raw_key) or "Other").strip()
            if key:
                extra.append((key.upper(), list(syms or [])))

    parts: list[str] = []
    global_seen: set[str] = set()
    for sec in EMAIN_SECTION_ORDER:
        syms = by_norm.get(sec) or []
        tv_syms = _dedupe_tv_symbols(syms, exchanges=exchanges, global_seen=global_seen)
        if not tv_syms and not include_empty:
            continue
        parts.append(f"###{sec}")
        parts.append(",".join(tv_syms))
    for key, syms in extra:
        tv_syms = _dedupe_tv_symbols(syms, exchanges=exchanges, global_seen=global_seen)
        if not tv_syms and not include_empty:
            continue
        parts.append(f"###{key}")
        parts.append(",".join(tv_syms))
    return ("\n".join(parts) + "\n") if parts else ""


def format_dated_watchlist_txt(
    symbols: Sequence[str],
    *,
    date_iso: str,
    video_id: str,
    view_name: str = "Potent",
    exchanges: dict[str, str] | None = None,
    prefix: str = "Martin Luk",
) -> str:
    """Secondary flat Potent/Leader export (not default Martin list)."""
    title = f"{prefix} {date_iso or 'unknown-date'} {video_id or 'video'} {view_name or 'List'}"
    tv_syms = _dedupe_tv_symbols(symbols, exchanges=exchanges)
    if not tv_syms:
        return f"###{title}\n"
    return f"###{title}\n{','.join(tv_syms)}\n"


# Back-compat
format_sidebar_watchlist_txt = format_emain_watchlist_txt
format_classified_watchlist_txt = format_emain_watchlist_txt
SIDEBAR_BUCKET_ORDER = EMAIN_SECTION_ORDER


def write_tradingview_txt(
    path: Path,
    symbols: Iterable[str] | None = None,
    *,
    section: str | None = None,
    exchanges: dict[str, str] | None = None,
    buckets: Mapping[str, Sequence[str]] | None = None,
    date_iso: str | None = None,
    video_id: str | None = None,
    list_name: str = "E_Main",
    view_name: str = "Potent",
    emain: bool = True,
    also_dated_filename: bool = True,
) -> Path:
    """Write Upload-list .txt. E_Main buckets → short ###SECTION body."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    date = date_iso or "unknown-date"

    if emain and buckets is not None:
        text = format_emain_watchlist_txt(buckets, exchanges=exchanges)
        if not text.strip() and symbols:
            text = format_dated_watchlist_txt(
                list(symbols),
                date_iso=date,
                video_id=video_id or "video",
                view_name=view_name,
                exchanges=exchanges,
            )
    elif not emain:
        text = format_dated_watchlist_txt(
            list(symbols or []),
            date_iso=date,
            video_id=video_id or "video",
            view_name=view_name,
            exchanges=exchanges,
        )
    else:
        text = format_watchlist_txt(
            list(symbols or []), section=section, exchanges=exchanges
        )

    path.write_text(text, encoding="utf-8")

    dated_path: Path | None = None
    # Only a real YYYY-MM-DD becomes Martin_Luk_<date>_E_Main.txt.
    # NA / unknown-date must not land in the reassert candidate set.
    iso = canonical_list_date(date_iso) if date_iso else None
    if also_dated_filename and emain and buckets and iso:
        dated_path = path.parent / list_filename(iso, list_name=list_name)
        if dated_path.resolve() != path.resolve():
            dated_path.write_text(text, encoding="utf-8")
        else:
            dated_path = path

    # Prefer dated Martin_Luk_YYYY-MM-DD_E_Main.txt for CDP listStem
    return dated_path or path


# Canonical iMBI3ZcQ6sU E_Main (Luk/Grok MCP — USD = Ultra Semis)
IMBI_EMAIN_DATE = "2026-10-28"
IMBI_EMAIN_LIST_NAME = "Martin Luk 2026-10-28 E_Main"
IMBI_EMAIN_BUCKETS: dict[str, list[str]] = {
    "INDEXES": ["QQQ", "SPY", "IWM"],
    "LONGS": ["USD", "SSPC", "SOXS"],
    "SHORTS": ["SLV", "GLD", "BMNR", "COIN"],
    "FOCUS": ["DRAM", "UVXY"],
    "TRACKING": ["SOXX", "SPCX", "SNDK", "SKHY", "GEV", "VRT", "AXTI"],
}

IMBI_EMAIN_TXT = (
    "###INDEXES\n"
    "NASDAQ:QQQ,AMEX:SPY,AMEX:IWM\n"
    "###LONGS\n"
    "AMEX:USD,CBOE:SSPC,AMEX:SOXS\n"
    "###SHORTS\n"
    "AMEX:SLV,AMEX:GLD,NYSE:BMNR,NASDAQ:COIN\n"
    "###FOCUS\n"
    "CBOE:DRAM,AMEX:UVXY\n"
    "###TRACKING\n"
    "NASDAQ:SOXX,NASDAQ:SPCX,NASDAQ:SNDK,NASDAQ:SKHY,NYSE:GEV,NYSE:VRT,NASDAQ:AXTI\n"
)
