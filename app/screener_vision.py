# -*- coding: utf-8 -*-
"""Vision/LLM read of TradingView screener + watchlist sidebar frames.

Uses OpenAI-compatible chat.completions with image_url when
``TUBEON_OPENAI_API_KEY`` is set (model default gpt-4o-mini / override via
``TUBEON_VISION_MODEL``). Falls back to Ollama vision model if configured.

Potent / Leader screener: read Symbol column as a FLAT list.
Never invent Long/Short splits — Potent has no L/S row icons.

Sidebar watchlist: only when INDEXES / LONG / FOCUS / SHORT headers are
visible, return those sections. Otherwise return empty buckets.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

import httpx

from .config import settings
from .us_tickers import filter_symbols

# Potent / Leader: flat Symbol column only
VISION_PROMPT_POTENT = (
    "This is a screenshot from a TradingView Potent / Leader screener table.\n"
    "Read ONLY the Symbol column (ticker symbols in the leftmost data column).\n"
    "Ignore prices, % change, volume, company names, chat, and any detail panel.\n"
    "Do NOT invent Long/Short/Focus labels — this screener has no L/S row icons.\n"
    "Return ONLY a JSON array of uppercase tickers, e.g. "
    '["AXSM","GNS","ICLR"]. No commentary.'
)

# Legacy alias
VISION_PROMPT_FLAT = VISION_PROMPT_POTENT
VISION_PROMPT = VISION_PROMPT_POTENT

VISION_PROMPT_SIDEBAR = (
    "This is a TradingView chart with a right-hand watchlist named E_Main "
    "(or similar). Read section headers INDEXES, LONGS, SHORTS, FOCUS, TRACKING "
    "(aliases: LONG/SHORT/INDICES) and the tickers under each.\n"
    "Return ONLY JSON of the form:\n"
    '{"indexes":["QQQ","SPY","IWM"],"longs":["USD","SSPC","SOXS"],'
    '"shorts":["SLV","GLD","BMNR","COIN"],"focus":["DRAM","UVXY"],'
    '"tracking":["SOXX","SPCX","SNDK"]}\n'
    "Use empty arrays for missing sections. If NO such section headers are "
    "visible, return all empty arrays. No commentary. Uppercase tickers."
)


def _image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _extract_json_blob(raw: str) -> Any | None:
    text = (raw or "").strip()
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _parse_symbol_json(raw: str) -> list[str]:
    data = _extract_json_blob(raw)
    if data is None:
        return re.findall(r"\b[A-Z]{1,5}\b", (raw or "").upper())
    if isinstance(data, dict):
        out: list[str] = []
        for key in (
            "symbols",
            "tickers",
            "flat",
            "potent",
            "long",
            "short",
            "focus",
            "indexes",
            "indices",
        ):
            val = data.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        out.append(item.strip().upper())
                    elif isinstance(item, dict):
                        sym = item.get("symbol") or item.get("ticker")
                        if sym:
                            out.append(str(sym).strip().upper())
        if out:
            return list(dict.fromkeys(out))
        for key in ("symbols", "tickers", "Symbol", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, str):
            out.append(item.strip().upper())
        elif isinstance(item, dict):
            sym = item.get("symbol") or item.get("ticker") or item.get("Symbol")
            if sym:
                out.append(str(sym).strip().upper())
    return list(dict.fromkeys(out))


def parse_sidebar_json(raw: str) -> dict[str, list[str]]:
    """Parse sidebar vision JSON into E_Main INDEXES/LONGS/SHORTS/FOCUS/TRACKING."""
    empty = {
        "INDEXES": [],
        "LONGS": [],
        "SHORTS": [],
        "FOCUS": [],
        "TRACKING": [],
        "flat": [],
    }
    data = _extract_json_blob(raw)
    if data is None:
        return empty
    if isinstance(data, list):
        return {
            **empty,
            "flat": filter_symbols(
                [str(x).upper() for x in data if isinstance(x, str)],
                allow_unknown_long=True,
            ),
        }
    if not isinstance(data, dict):
        return empty

    def _list(*keys: str) -> list[str]:
        for k in keys:
            val = data.get(k)
            if isinstance(val, list):
                out: list[str] = []
                for item in val:
                    if isinstance(item, str):
                        out.append(item.strip().upper())
                    elif isinstance(item, dict):
                        sym = item.get("symbol") or item.get("ticker")
                        if sym:
                            out.append(str(sym).strip().upper())
                return filter_symbols(out, allow_unknown_long=True)
        return []

    return {
        "INDEXES": _list("indexes", "Indexes", "INDEXES", "indices", "Indices", "INDICES"),
        "LONGS": _list("longs", "Longs", "LONGS", "long", "Long", "LONG"),
        "SHORTS": _list("shorts", "Shorts", "SHORTS", "short", "Short", "SHORT"),
        "FOCUS": _list("focus", "Focus", "FOCUS"),
        "TRACKING": _list("tracking", "Tracking", "TRACKING", "track"),
        "flat": _list("flat", "symbols", "tickers"),
    }


def parse_classified_json(raw: str) -> dict[str, list[str]]:
    """Back-compat wrapper around parse_sidebar_json."""
    side = parse_sidebar_json(raw)
    return {
        "long": side["LONGS"],
        "short": side["SHORTS"],
        "focus": side["FOCUS"],
        "indexes": side["INDEXES"],
        "tracking": side["TRACKING"],
        "flat": side["flat"],
        **side,
    }


def vision_available() -> dict[str, Any]:
    """Which vision backend can run (if any)."""
    if (settings.openai_api_key or "").strip():
        return {
            "ok": True,
            "backend": "openai",
            "model": (getattr(settings, "vision_model", None) or settings.openai_model or "gpt-4o-mini"),
        }
    vision_ollama = (getattr(settings, "vision_ollama_model", None) or "").strip()
    if vision_ollama:
        return {"ok": True, "backend": "ollama", "model": vision_ollama}
    return {"ok": False, "backend": None, "model": None}


def _openai_vision(path: Path, model: str, prompt: str) -> str:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.openai_api_key}",
    }
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": _image_data_url(path)}},
                ],
            }
        ],
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.post(
            f"{settings.openai_base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


def _ollama_vision(path: Path, model: str, prompt: str) -> str:
    raw = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0},
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [raw],
            }
        ],
    }
    with httpx.Client(timeout=180.0) as client:
        r = client.post(f"{settings.ollama_base_url.rstrip('/')}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()


def _run_vision(path: Path, prompt: str) -> dict[str, Any]:
    avail = vision_available()
    if not avail.get("ok"):
        return {
            "raw": "",
            "backend": None,
            "model": None,
            "error": "no vision backend (set TUBEON_OPENAI_API_KEY or TUBEON_VISION_OLLAMA_MODEL)",
        }
    p = Path(path)
    if not p.exists():
        return {
            "raw": "",
            "backend": avail["backend"],
            "model": avail["model"],
            "error": f"missing {p}",
        }
    try:
        if avail["backend"] == "openai":
            raw = _openai_vision(p, str(avail["model"]), prompt)
        else:
            raw = _ollama_vision(p, str(avail["model"]), prompt)
        return {
            "raw": raw[:2000],
            "backend": avail["backend"],
            "model": avail["model"],
            "error": None,
        }
    except Exception as e:
        return {
            "raw": "",
            "backend": avail["backend"],
            "model": avail["model"],
            "error": str(e),
        }


def read_screener_symbols(image_path: Path) -> dict[str, Any]:
    """Vision-read Potent/Leader Symbol column as a flat list (no L/S invent)."""
    avail = vision_available()
    run = _run_vision(image_path, VISION_PROMPT_POTENT)
    if run.get("error") and not run.get("raw"):
        return {
            "symbols": [],
            "buckets": None,
            "sidebar": False,
            "backend": run.get("backend") or avail.get("backend"),
            "model": run.get("model") or avail.get("model"),
            "raw": run.get("raw") or "",
            "error": run.get("error"),
        }
    symbols = filter_symbols(_parse_symbol_json(run.get("raw") or ""), allow_unknown_long=True)
    return {
        "symbols": symbols,
        "buckets": None,
        "sidebar": False,
        "backend": run.get("backend"),
        "model": run.get("model"),
        "raw": run.get("raw"),
        "error": None,
    }


def read_screener_classified(image_path: Path) -> dict[str, Any]:
    """Back-compat wrapper — Potent path is flat; does not invent L/S buckets."""
    result = read_screener_symbols(image_path)
    return {
        **result,
        "buckets": {"long": [], "short": [], "focus": [], "flat": result.get("symbols") or []},
    }


def read_sidebar_sections(image_path: Path) -> dict[str, Any]:
    """Vision-read watchlist sidebar sections when INDEXES/LONG/FOCUS/SHORT visible."""
    run = _run_vision(image_path, VISION_PROMPT_SIDEBAR)
    if run.get("error") and not run.get("raw"):
        return {
            "buckets": {"Indexes": [], "Long": [], "Focus": [], "Short": []},
            "symbols": [],
            "sidebar": False,
            "backend": run.get("backend"),
            "model": run.get("model"),
            "raw": run.get("raw") or "",
            "error": run.get("error"),
        }
    parsed = parse_sidebar_json(run.get("raw") or "")
    buckets = {
        "INDEXES": parsed["INDEXES"],
        "LONGS": parsed["LONGS"],
        "SHORTS": parsed["SHORTS"],
        "FOCUS": parsed["FOCUS"],
        "TRACKING": parsed["TRACKING"],
    }
    has_sections = any(buckets.values())
    symbols = (
        buckets["INDEXES"]
        + buckets["LONGS"]
        + buckets["SHORTS"]
        + buckets["FOCUS"]
        + buckets["TRACKING"]
    )
    if not has_sections and parsed.get("flat"):
        symbols = list(parsed["flat"])
    return {
        "buckets": buckets if has_sections else {
            "INDEXES": [],
            "LONGS": [],
            "SHORTS": [],
            "FOCUS": [],
            "TRACKING": [],
        },
        "symbols": symbols,
        "flat": parsed.get("flat") or [],
        "sidebar": has_sections,
        "backend": run.get("backend"),
        "model": run.get("model"),
        "raw": run.get("raw"),
        "error": None,
    }


def read_best_screener_frames(
    frame_paths: list[Path],
    *,
    max_frames: int = 3,
) -> dict[str, Any]:
    """Vision-read up to max_frames Potent tables; merge flat Symbol lists (first-seen)."""
    avail = vision_available()
    merged: list[str] = []
    seen: set[str] = set()
    reads: list[dict[str, Any]] = []
    for path in frame_paths[: max(0, max_frames)]:
        result = read_screener_symbols(path)
        reads.append({"path": str(path), **result})
        for s in result.get("symbols") or []:
            if s in seen:
                continue
            seen.add(s)
            merged.append(s)
    return {
        "symbols": merged,
        "buckets": None,
        "sidebar": False,
        "backend": avail.get("backend"),
        "model": avail.get("model"),
        "reads": reads,
        "available": bool(avail.get("ok")),
    }
