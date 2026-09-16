# -*- coding: utf-8 -*-
"""Scan every summary for side vs quote / digest contradictions."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.auto_summary import _infer_side, _watch_lean  # noqa: E402
from app.parse_md import split_bullet  # noqa: E402

OUT = ROOT / "outputs"
BULL = re.compile(
    r"really strong|pretty strong|looks? strong|breakouts?|breaking out|"
    r"sign of strength|holding near|attempts? to (?:push|go) lower.{0,40}failed",
    re.I,
)
BEAR = re.compile(
    r"\bshorting\b|\bshorted\b|shortable|rejected|rejection|closing weak|"
    r"gapping down|going lower|push lower",
    re.I,
)
BULL_REASON = re.compile(r"睇落.*強|仍然強|破位／轉強|相對強勢|轉強")
BEAR_REASON = re.compile(r"被 reject|想／考慮短|或跟空|shortable|收市偏弱|gap down")


def section(md: str, title: str) -> str:
    lines = md.splitlines()
    grab = False
    out: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if grab:
                break
            grab = title in line
            continue
        if grab:
            out.append(line)
    return "\n".join(out)


def en_quote(rest: str) -> str:
    if "‖" in rest:
        rest = rest.split("‖", 1)[0]
    cells = [c.strip() for c in rest.split("|")]
    return cells[-1] if cells else rest


def audit() -> None:
    hits: list[str] = []
    for p in sorted(OUT.glob("*.md")):
        md = p.read_text(encoding="utf-8")
        vid = p.stem
        title = md.splitlines()[0].lstrip("# ").strip() if md else vid
        digest = section(md, "真正摘要")
        en = section(md, "Timeline content (EN)") or section(md, "時間軸內容")
        for line in digest.splitlines():
            if not line.startswith("- **"):
                continue
            if "今日總覽" in line or "實際操作" in line:
                continue
            if "偏空" in line and BULL_REASON.search(line):
                hits.append(f"DIGEST {vid} {title}\n  {line}")
            if "偏多" in line and BEAR_REASON.search(line) and "偏空" not in line.split("—")[0]:
                # 偏多 badge with bear reason
                hits.append(f"DIGEST-FLIP {vid} {title}\n  {line}")
        for line in en.splitlines():
            got = split_bullet(line)
            if not got:
                continue
            t, rest = got
            if "字幕缺口" in rest or "Mute gap" in rest:
                continue
            cells = [c.strip() for c in rest.split("|")]
            if len(cells) < 2:
                continue
            label = re.sub(r"\*\*", "", cells[0]).strip()
            side = cells[1] if len(cells) > 1 else ""
            if label.lower() in {"session", "字幕缺口", "mute gap"}:
                continue
            quote = en_quote(rest)
            inferred = _infer_side(quote, label.upper() if label.isupper() or len(label) <= 5 else label)
            lean = _watch_lean(quote)
            if "偏空" in side and (BULL.search(quote) and not BEAR.search(quote)):
                hits.append(
                    f"ROW-BULL-AS-SHORT {vid} {t} {label} shown={side} infer={inferred} lean={lean}\n  {quote[:220]}"
                )
            if "偏多" in side and (BEAR.search(quote) and not BULL.search(quote)):
                hits.append(
                    f"ROW-BEAR-AS-LONG {vid} {t} {label} shown={side} infer={inferred} lean={lean}\n  {quote[:220]}"
                )
            if inferred != "Watch" and side.startswith("觀望") and "偏" not in side:
                if inferred.startswith("Watch／"):
                    hits.append(
                        f"ROW-MISSED-LEAN {vid} {t} {label} shown={side} infer={inferred}\n  {quote[:220]}"
                    )
    print(f"FINDINGS {len(hits)}")
    for h in hits:
        print("---")
        print(h)


if __name__ == "__main__":
    audit()
