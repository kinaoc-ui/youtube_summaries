# -*- coding: utf-8 -*-
"""Resolve Martin VOD calendar date for dated TradingView section titles.

Prefer stream/upload date from summary title / labels — never the run date.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config import DATA_DIR, SUMMARY_DIR
from .ticker_verify import DATE_IN_TITLE, MONTHS, parse_stream_date

ISO_DATE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
YMD_COMPACT = re.compile(r"(20\d{2})(\d{2})(\d{2})")


def _iso(d: date) -> str:
    return d.isoformat()


def resolve_vod_date(video_id: str, *, hint: str | None = None) -> str:
    """Return YYYY-MM-DD for ``video_id`` (fallback: unknown-date)."""
    # 1) Explicit hint (yt-dlp upload_date or caller)
    if hint:
        h = hint.strip()
        m = ISO_DATE.search(h)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        m = YMD_COMPACT.fullmatch(h) or YMD_COMPACT.search(h.replace("-", ""))
        if m and len(h.replace("-", "")) >= 8:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
            except ValueError:
                pass
        m = DATE_IN_TITLE.search(h)
        if m:
            day, mon, year = int(m.group(1)), MONTHS[m.group(2)[:3].lower()], int(m.group(3))
            try:
                return date(year, mon, day).isoformat()
            except ValueError:
                pass

    # 2) Summary title / ticker_verify helper
    d = parse_stream_date(video_id)
    if d:
        return _iso(d)

    # 3) summary json title
    for path in (SUMMARY_DIR / f"{video_id}.json", SUMMARY_DIR / f"{video_id}.md"):
        if not path.exists():
            continue
        try:
            if path.suffix == ".json":
                title = str(json.loads(path.read_text(encoding="utf-8")).get("title") or "")
            else:
                title = path.read_text(encoding="utf-8").splitlines()[0] if path.stat().st_size else ""
        except (json.JSONDecodeError, OSError):
            continue
        m = DATE_IN_TITLE.search(title)
        if m:
            day, mon, year = int(m.group(1)), MONTHS[m.group(2)[:3].lower()], int(m.group(3))
            try:
                return date(year, mon, day).isoformat()
            except ValueError:
                pass

    # 4) martin_state / watchlist job meta if present
    for path in (
        DATA_DIR / "watchlist_jobs" / f"{video_id}.json",
        DATA_DIR / "frames" / video_id / "watchlist.json",
    ):
        if not path.exists():
            continue
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for key in ("upload_date", "vod_date", "asof", "date"):
            val = meta.get(key)
            if val:
                got = resolve_vod_date(video_id, hint=str(val))
                if got != "unknown-date":
                    return got

    return "unknown-date"


def buckets_from_flat(
    symbols: list[str],
    *,
    default_bucket: str = "Long",
) -> dict[str, list[str]]:
    """Put unclassified symbols into default bucket (used when vision has no L/S)."""
    return {
        "Long": list(symbols) if default_bucket.lower() == "long" else [],
        "Short": list(symbols) if default_bucket.lower() == "short" else [],
        "Focus": list(symbols) if default_bucket.lower() == "focus" else [],
    }
