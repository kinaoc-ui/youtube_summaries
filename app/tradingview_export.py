# -*- coding: utf-8 -*-
"""TradingView watchlist file export (Upload list… .txt).

TradingView has no public API for programmatic watchlist updates.
Official import path (paid Essential+): Watchlist name → Upload list…
File must be .txt with EXCHANGE:SYMBOL entries, comma-separated.
Optional section headers: ###SectionName

Docs: https://www.tradingview.com/support/solutions/43000487233-how-to-import-or-export-a-watchlist/
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

# Martin Luk universe is mostly US growth / tech. Prefer NASDAQ; override when known.
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
    "IWM": "AMEX",
    "SOXX": "NASDAQ",
    "IGV": "AMEX",
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
    "SNDK": "NASDAQ",
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
    "AXTI": "NASDAQ",
    "OSK": "NYSE",
    "HIMS": "NYSE",
    "XYZ": "NYSE",
    "CRCL": "NYSE",
    # Non-US / special
    "SKHY": "KRX",  # SK Hynix — TV may expect 000660; keep ticker as spoken/OCR'd
    "DOGEUSD": "CRYPTO",
    "SPCX": "NASDAQ",  # SpaceX-related ticker Martin uses on chart (verify on TV)
}

DEFAULT_EXCHANGE = "NASDAQ"


def tv_symbol(ticker: str, exchange: str | None = None) -> str:
    """Return EXCHANGE:TICKER for TradingView upload."""
    t = (ticker or "").upper().strip()
    if not t:
        raise ValueError("empty ticker")
    if ":" in t:
        return t
    ex = (exchange or EXCHANGE_FOR_TICKER.get(t) or DEFAULT_EXCHANGE).upper()
    if t == "SKHY":
        # Prefer the exchange-listed code when available on TV
        return "KRX:000660"
    if t == "DOGEUSD":
        return "CRYPTO:DOGEUSD"
    return f"{ex}:{t}"


def format_watchlist_txt(
    symbols: Sequence[str],
    *,
    section: str | None = "Martin Luk",
    exchanges: dict[str, str] | None = None,
) -> str:
    """Build TradingView Upload-list TXT content.

    Symbols may be bare tickers or already EXCHANGE:TICKER.
    """
    exchanges = exchanges or {}
    seen: set[str] = set()
    tv_syms: list[str] = []
    for raw in symbols:
        s = (raw or "").strip()
        if not s:
            continue
        if ":" in s:
            key = s.upper()
            entry = key
        else:
            tick = s.upper()
            entry = tv_symbol(tick, exchanges.get(tick))
            key = entry
        if key in seen:
            continue
        seen.add(key)
        tv_syms.append(entry)
    parts: list[str] = []
    if section:
        parts.append(f"###{section}")
    parts.append(",".join(tv_syms))
    return "\n".join(parts) + ("\n" if parts else "")


def write_tradingview_txt(
    path: Path,
    symbols: Iterable[str],
    *,
    section: str | None = "Martin Luk",
    exchanges: dict[str, str] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = format_watchlist_txt(list(symbols), section=section, exchanges=exchanges)
    path.write_text(text, encoding="utf-8")
    return path
