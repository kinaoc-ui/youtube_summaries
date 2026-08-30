"""Triple-check screen tickers: screenshot price vs Yahoo quote vs speech window.

Screen labels (Cursor/OCR) still misread FIG vs FROG. A quote that does not
match the number on the chart is treated as a hard fail, even if the name
looks plausible. Speech is a third source: it may disagree with the chart
(that is a split, not a ticker typo).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from .config import DATA_DIR, SUMMARY_DIR
from .transcript import load_transcript
from .video_check import ASR_ALIASES, KNOWN_TICKERS, TICKER_RE, parse_ts

# Two-letter codes that are also English words — do not treat as spoken tickers
# unless the company name is nearby (Bloom Energy).
SPEECH_STOP = {
    "BE", "OR", "ON", "IT", "SO", "UP", "AT", "AM", "IS", "WE", "ME", "US",
    "GO", "NO", "TO", "IF", "AN", "AS", "BY", "DO", "HE", "MY", "OK",
}

YAHOO_SYMBOL = {
    "SKHY": "000660.KS",
    "DOGEUSD": "DOGE-USD",
}

# Company-name fragments that pin a ticker (case-insensitive).
NAME_TO_TICKER = {
    "figma": "FIG",
    "jfrog": "FROG",
    "spacex": "SPCX",
    "space exploration": "SPCX",
    "hynix": "SKHY",
    "d-wave": "QBTS",
    "dwave": "QBTS",
    "coreweave": "CRWV",
    "sandisk": "SNDK",
    "tempus": "TEM",
    "bloom energy": "BE",
    "astera": "ALAB",
    "uipath": "PATH",
    "crowdstrike": "CRWD",
    "celestica": "CLS",
    "oklo": "OKLO",
    "rigetti": "RGTI",
    "ionq": "IONQ",
}

DATE_IN_TITLE = re.compile(
    r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(20\d{2})",
    re.I,
)
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _yahoo_sym(ticker: str) -> str:
    t = (ticker or "").upper().strip()
    return YAHOO_SYMBOL.get(t, t)


def parse_stream_date(video_id: str) -> date | None:
    path = SUMMARY_DIR / f"{video_id}.json"
    title = ""
    if path.exists():
        title = (json.loads(path.read_text(encoding="utf-8")).get("title") or "")
    m = DATE_IN_TITLE.search(title)
    if not m:
        return None
    day, mon, year = int(m.group(1)), MONTHS[m.group(2)[:3].lower()], int(m.group(3))
    return date(year, mon, day)


def fetch_yahoo_close(ticker: str, asof: date, client: httpx.Client) -> dict[str, Any]:
    """Daily close on/near asof. Cached by caller via dict."""
    ysym = _yahoo_sym(ticker)
    start = datetime.combine(asof - timedelta(days=5), datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(asof + timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ysym}"
    params = {
        "period1": int(start.timestamp()),
        "period2": int(end.timestamp()),
        "interval": "1d",
        "events": "div,splits",
    }
    headers = {"User-Agent": "Mozilla/5.0 (compatible; tubeon-verify/1.0)"}
    r = client.get(url, params=params, headers=headers, timeout=20.0)
    if r.status_code != 200:
        return {"ok": False, "yahoo": ysym, "error": f"http {r.status_code}"}
    chart = (r.json().get("chart") or {}).get("result") or []
    if not chart:
        return {"ok": False, "yahoo": ysym, "error": "no chart"}
    result = chart[0]
    ts = result.get("timestamp") or []
    closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    rows = [(datetime.fromtimestamp(t, tz=timezone.utc).date(), c) for t, c in zip(ts, closes) if c is not None]
    if not rows:
        return {"ok": False, "yahoo": ysym, "error": "no closes"}
    # Prefer same calendar day, else nearest earlier, else nearest.
    same = [x for x in rows if x[0] == asof]
    if same:
        close, d = same[-1][1], same[-1][0]
    else:
        earlier = [x for x in rows if x[0] <= asof]
        pick = earlier[-1] if earlier else min(rows, key=lambda x: abs((x[0] - asof).days))
        close, d = pick[1], pick[0]
    return {"ok": True, "yahoo": ysym, "close": float(close), "quote_date": d.isoformat()}


def price_matches(screen: float, quote: float) -> bool:
    if quote <= 0:
        return False
    abs_err = abs(screen - quote)
    rel = abs_err / quote
    if quote < 1:
        return rel <= 0.25
    return abs_err <= max(2.0, quote * 0.12)


def name_ticker(name: str | None) -> str | None:
    if not name:
        return None
    low = name.lower()
    for frag, tick in NAME_TO_TICKER.items():
        if frag in low:
            return tick
    return None


def spoken_tickers(video_id: str, t: str, window: float = 50.0) -> list[str]:
    tr = load_transcript(video_id)
    if not tr:
        return []
    center = parse_ts(t)
    texts: list[str] = []
    for s in tr.get("snippets") or []:
        try:
            start = float(s.get("start") or 0)
        except (TypeError, ValueError):
            continue
        if abs(start - center) <= window:
            texts.append(str(s.get("text") or ""))
    blob = " ".join(texts).upper()
    found: list[str] = []
    low = " ".join(texts).lower()
    for raw in TICKER_RE.findall(blob):
        canon = ASR_ALIASES.get(raw, raw)
        if canon not in KNOWN_TICKERS or canon in found:
            continue
        if canon in SPEECH_STOP:
            if canon == "BE" and "bloom" in low:
                found.append(canon)
            continue
        found.append(canon)
    if re.search(r"\bfake\b|\bfigma\b", low) and "FIG" not in found:
        found.append("FIG")
    if re.search(r"\bfrog\b|\bjfrog\b", low) and "FROG" not in found:
        found.append("FROG")
    return found


def verify_labels(video_id: str, asof: date | None = None) -> dict[str, Any]:
    labels_path = DATA_DIR / "frames" / video_id / "labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    asof = asof or parse_stream_date(video_id) or date.today()
    by_t = labels.get("by_t") or {}
    quote_cache: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    unique = sorted({(lab.get("symbol") or "").upper() for lab in by_t.values() if lab.get("symbol")})
    # Always quote lookalikes so FIG@$102 can be remapped to FROG even if FROG
    # never appears elsewhere in this video.
    unique = sorted(set(unique) | {"FIG", "FROG", "AMD", "SPCX"})

    with httpx.Client() as client:
        for tick in unique:
            quote_cache[tick] = fetch_yahoo_close(tick, asof, client)

    for t, lab in by_t.items():
        sym = (lab.get("symbol") or "") or None
        price = lab.get("price")
        name = lab.get("name")
        q = quote_cache.get((sym or "").upper()) if sym else None
        expected_from_name = name_ticker(name)
        speech = spoken_tickers(video_id, t)
        name_ok = True
        name_note = None
        if expected_from_name and sym and expected_from_name != sym.upper():
            name_ok = False
            name_note = f"name looks like {expected_from_name}, label is {sym}"

        price_ok: bool | None = None
        price_note = None
        if not sym:
            verdict = "skip"
            price_note = "no symbol"
        elif q is None or not q.get("ok"):
            verdict = "no_quote"
            price_note = (q or {}).get("error") or "no yahoo"
        elif price is None:
            verdict = "no_screen_price"
            price_note = "screenshot has no last price"
        else:
            close = float(q["close"])
            screen = float(price)
            ratio = max(screen, close) / max(min(screen, close), 1e-9)
            price_note = (
                f"screen {price} vs yahoo {q['yahoo']} {close:.4g} on {q['quote_date']}"
            )
            if ratio >= 50:
                verdict = "no_quote"
                price_ok = None
                price_note += " (likely FX/unit mismatch)"
            else:
                price_ok = price_matches(screen, close)
                if not price_ok:
                    verdict = "fail"
                elif not name_ok:
                    verdict = "fail"
                elif speech and sym.upper() not in speech:
                    verdict = "split"
                else:
                    verdict = "pass"

        suggest = None
        if verdict == "fail" and price is not None:
            best = None
            best_err = None
            for cand, cq in quote_cache.items():
                if not cq.get("ok"):
                    continue
                err = abs(float(price) - float(cq["close"])) / max(float(cq["close"]), 1e-9)
                if best_err is None or err < best_err:
                    best, best_err = cand, err
            if best and best != (sym or "").upper() and best_err is not None and best_err <= 0.12:
                suggest = best

        items.append(
            {
                "t": t,
                "symbol": sym,
                "name": name,
                "screen_price": price,
                "yahoo": q,
                "price_ok": price_ok,
                "name_ok": name_ok,
                "name_note": name_note,
                "speech": speech,
                "verdict": verdict,
                "note": price_note,
                "suggest": suggest,
            }
        )

    counts: dict[str, int] = {}
    for x in items:
        counts[x["verdict"]] = counts.get(x["verdict"], 0) + 1
    out = {
        "video_id": video_id,
        "asof": asof.isoformat(),
        "counts": counts,
        "items": items,
    }
    out_path = DATA_DIR / "frames" / video_id / "verify.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
