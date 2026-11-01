# -*- coding: utf-8 -*-
"""Vision/LLM read of TradingView screener frames (prefer over RapidOCR gibberish).

Uses OpenAI-compatible chat.completions with image_url when
``TUBEON_OPENAI_API_KEY`` is set (model default gpt-4o-mini / override via
``TUBEON_VISION_MODEL``). Falls back to Ollama vision model if configured.

Never invents tickers beyond what the model returns; results are still passed
through ``us_tickers.filter_symbols``.
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

VISION_PROMPT = (
    "This is a screenshot from a TradingView screener / Leader table on a "
    "livestream. Read ONLY the Symbol column of the screener table (the vertical "
    "list of stock tickers). Ignore prices, % change, volume, company names, "
    "chart chrome, chat, and any detail panel on the right (e.g. a single name "
    "like BRZE with a large price).\n\n"
    "Return a JSON array of uppercase ticker strings only, e.g. "
    '["AXSM","GNS","ICLR"]. No commentary.'
)


def _image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _parse_symbol_json(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.M).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[[^\]]*\]", text, re.S)
        if not m:
            # fallback: tokens
            return re.findall(r"\b[A-Z]{1,5}\b", text.upper())
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return re.findall(r"\b[A-Z]{1,5}\b", text.upper())
    if isinstance(data, dict):
        for key in ("symbols", "tickers", "Symbol", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        if isinstance(item, str):
            out.append(item.strip().upper())
        elif isinstance(item, dict):
            sym = item.get("symbol") or item.get("ticker") or item.get("Symbol")
            if sym:
                out.append(str(sym).strip().upper())
    return out


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


def _openai_vision(path: Path, model: str) -> str:
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
                    {"type": "text", "text": VISION_PROMPT},
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


def _ollama_vision(path: Path, model: str) -> str:
    # Ollama /api/chat with images as base64
    raw = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0},
        "messages": [
            {
                "role": "user",
                "content": VISION_PROMPT,
                "images": [raw],
            }
        ],
    }
    with httpx.Client(timeout=180.0) as client:
        r = client.post(f"{settings.ollama_base_url.rstrip('/')}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()


def read_screener_symbols(image_path: Path) -> dict[str, Any]:
    """Vision-read Symbol column from one frame. Returns {symbols, backend, raw, error}."""
    avail = vision_available()
    if not avail.get("ok"):
        return {
            "symbols": [],
            "backend": None,
            "raw": "",
            "error": "no vision backend (set TUBEON_OPENAI_API_KEY or TUBEON_VISION_OLLAMA_MODEL)",
        }
    path = Path(image_path)
    if not path.exists():
        return {"symbols": [], "backend": avail["backend"], "raw": "", "error": f"missing {path}"}
    try:
        if avail["backend"] == "openai":
            raw = _openai_vision(path, str(avail["model"]))
        else:
            raw = _ollama_vision(path, str(avail["model"]))
        parsed = _parse_symbol_json(raw)
        # Vision may see real names not yet in allowlist — allow unknown 3–5 letter
        symbols = filter_symbols(parsed, allow_unknown_long=True)
        return {
            "symbols": symbols,
            "backend": avail["backend"],
            "model": avail["model"],
            "raw": raw[:1000],
            "parsed_n": len(parsed),
            "error": None,
        }
    except Exception as e:
        return {
            "symbols": [],
            "backend": avail["backend"],
            "model": avail["model"],
            "raw": "",
            "error": str(e),
        }


def read_best_screener_frames(
    frame_paths: list[Path],
    *,
    max_frames: int = 3,
) -> dict[str, Any]:
    """Vision-read up to max_frames images; merge unique Symbol-column tickers."""
    avail = vision_available()
    merged: list[str] = []
    seen: set[str] = set()
    reads: list[dict[str, Any]] = []
    for path in frame_paths[: max(0, max_frames)]:
        result = read_screener_symbols(path)
        reads.append({"path": str(path), **result})
        for s in result.get("symbols") or []:
            if s not in seen:
                seen.add(s)
                merged.append(s)
    return {
        "symbols": merged,
        "backend": avail.get("backend"),
        "model": avail.get("model"),
        "reads": reads,
        "available": bool(avail.get("ok")),
    }
