# -*- coding: utf-8 -*-
"""Block lean-short badges that still say 睇落強／破位. Used before git push."""
from __future__ import annotations

import re
from pathlib import Path

from .config import OUTPUT_DIR, SUMMARY_DIR, ROOT

_BULL_REASON = re.compile(
    r"睇落.*強|破位／轉強|相對強勢|仍有強勢|有機會／未跟到|反彈|企穩"
)
_SHORT_BADGE = re.compile(r"偏空|做空／short")
_PLAIN_WATCH = re.compile(r"觀望／watch")
_DIR_REASON = re.compile(
    r"睇落.*強|破位／轉強|相對強勢|仍有強勢|有機會／未跟到|反彈|企穩|"
    r"被 reject|跟空|shortable|想／考慮短|收市偏弱|問／考慮短|有少少弱"
)


def _digest_section(md: str) -> str:
    lines = md.splitlines()
    grab = False
    out: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if grab:
                break
            grab = "真正摘要" in line
            continue
        if grab:
            out.append(line)
    return "\n".join(out)


def digest_contradictions(md: str, video_id: str = "") -> list[str]:
    """Lean-short / short badge must not carry bullish reason bits."""
    hits: list[str] = []
    for line in _digest_section(md).splitlines():
        if not line.startswith("- **"):
            continue
        if "今日總覽" in line or "實際操作" in line:
            continue
        if "—" not in line and "–" not in line:
            continue
        badge, reason = re.split(r"\s+[—–-]\s+", line, maxsplit=1)
        if _SHORT_BADGE.search(badge) and _BULL_REASON.search(reason):
            hits.append(f"{video_id} {line}".strip())
        elif (
            _PLAIN_WATCH.search(badge)
            and "偏" not in badge
            and _DIR_REASON.search(reason)
            and reason.strip() not in {"觀望", "觀望／watch"}
        ):
            hits.append(f"{video_id} {line}".strip())
    return hits


def scan_outputs_gate() -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for folder in (OUTPUT_DIR, SUMMARY_DIR):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            key = path.stem
            if key in seen:
                continue
            seen.add(key)
            try:
                md = path.read_text(encoding="utf-8")
            except OSError:
                continue
            hits.extend(digest_contradictions(md, path.stem))
    return hits


def run_gate() -> int:
    """0 = ok to push. 1 = contradictions in written summaries."""
    hits = scan_outputs_gate()
    if not hits:
        print("[OK] side gate: no lean-short vs strength contradictions")
        return 0
    print("[ERROR] side gate failed — not pushing contradictory digest")
    for h in hits:
        print(" ", h)
    print(f"ROOT={ROOT}")
    return 1
