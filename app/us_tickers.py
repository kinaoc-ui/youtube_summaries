# -*- coding: utf-8 -*-
"""US equity ticker allowlist used to reject RapidOCR gibberish.

Martin's Leader screener is almost always listed US names. We keep a curated
allowlist (plus app.video_check.KNOWN_TICKERS) and require membership for
OCR-derived symbols. Vision/LLM reads may add well-formed 3–5 letter tokens
that are not yet listed, but never dotted junk (A.M) or random 1–2 letters.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .config import ROOT
from .video_check import ASR_ALIASES, KNOWN_TICKERS

# Explicit extras seen on Martin streams / iMBI3ZcQ6sU Leader frame (vision-read)
STREAM_EXTRAS = {
    "AXSM", "GNS", "ICLR", "EVR", "WMG", "TXG", "BYON", "TWST", "TEM", "PPG",
    "CRL", "FRO", "ACN", "PNT", "REVV", "MRNA", "NTRA", "HCA", "ETSY", "IQV",
    "SOFI", "GH", "EXAS", "RBRK", "AKAM", "Z", "MNSO", "BRZE",
    # common neighbors / frequent Martin names
    "SMTC", "ISRG", "DXCM", "VEEV", "TMO", "DHR", "UNH", "LLY", "JNJ", "ABBV",
    "PFE", "BMY", "GILD", "REGN", "VRTX", "BIIB", "ILMN", "TECH", "WAT", "A",
    "BAX", "BDX", "BSX", "SYK", "MDT", "ZBH", "HOLX", "IDXX", "LH", "DGX",
    "CNC", "HUM", "CI", "ELV", "MOH", "OSCR", "CLOV", "TDOC", "AMGN", "BMRN",
    "ALNY", "SGEN", "INCY", "EXEL", "NBIX", "UTHR", "RGEN", "CRL", "IQV",
    "CNC", "GEHC", "PODD", "PEN", "EW", "ABT", "CVS", "WBA", "MCK", "CAH",
    "COR", "ABC", "HSIC", "PDCO",
}

# Valid share-class dots only (reject OCR "A.M" / "I.NE" / "T.X")
ALLOWED_DOTTED = {"BRK.B", "BF.B", "CWEN.A"}

TICKER_BARE_RE = re.compile(r"^[A-Z]{1,5}$")
OCR_JUNK_DOT_RE = re.compile(r"^[A-Z]\.[A-Z]{1,3}$")  # A.M, I.NE, T.X


@lru_cache(maxsize=1)
def us_ticker_set() -> frozenset[str]:
    tickers: set[str] = set(KNOWN_TICKERS) | set(STREAM_EXTRAS) | set(ALLOWED_DOTTED)
    path = ROOT / "data" / "us_tickers.txt"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip().upper()
            if not line or line.startswith("#"):
                continue
            tickers.add(ASR_ALIASES.get(line, line))
    return frozenset(tickers)


def normalize_symbol(raw: str) -> str:
    text = (raw or "").strip().upper()
    text = re.sub(r"^[^A-Z]+|[^A-Z.]+$", "", text)
    if not text:
        return ""
    return ASR_ALIASES.get(text, text)


def is_valid_us_ticker(symbol: str, *, allow_unknown_long: bool = False) -> bool:
    """Return True if symbol is safe to ship (not RapidOCR noise).

    - Reject dotted OCR garbage (A.M) except known share classes
    - 1–2 letters only if on allowlist (Z, GH, …)
    - 3–5 letters: allowlist required unless allow_unknown_long (vision path)
    """
    s = normalize_symbol(symbol)
    if not s:
        return False
    if OCR_JUNK_DOT_RE.match(s) and s not in ALLOWED_DOTTED:
        return False
    if "." in s:
        return s in ALLOWED_DOTTED
    if not TICKER_BARE_RE.match(s):
        return False
    known = us_ticker_set()
    if len(s) <= 2:
        return s in known
    if s in known:
        return True
    return bool(allow_unknown_long)


def filter_symbols(
    symbols: list[str],
    *,
    allow_unknown_long: bool = False,
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        s = normalize_symbol(raw)
        if not s or s in seen:
            continue
        if not is_valid_us_ticker(s, allow_unknown_long=allow_unknown_long):
            continue
        seen.add(s)
        out.append(s)
    return out
