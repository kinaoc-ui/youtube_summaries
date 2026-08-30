# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from pathlib import Path

from zh_ep90 import EXEC, ZH

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "ufN4u_ncWZg.md"
OLD = OUT if OUT.exists() else None

# Prefer EN lines from existing markdown if present
EN: list[tuple[str, str]] = []
if OLD and OLD.exists():
    text = OLD.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"## Timestamped notes \(EN\)\n([\s\S]*?)\n## ", text)
    if m:
        for line in m.group(1).splitlines():
            mm = re.match(r"^- `([^`]+)` (.+)$", line.strip())
            if mm:
                EN.append((mm.group(1), mm.group(2)))

if not EN:
    raise SystemExit("No EN bullets found — restore outputs/ufN4u_ncWZg.md EN section first")

missing = [t for t, _ in EN if t not in ZH]
if missing:
    raise SystemExit(f"Missing ZH for: {missing}")

parts = [
    "# EP90 | 28 Aug 2026",
    "",
    "- **Video:** [ufN4u_ncWZg](https://www.youtube.com/watch?v=ufN4u_ncWZg)",
    "- **Channel:** martinlukkt",
    "- **Source:** cursor-agent（由 auto-captions 總結／翻譯）",
    "- **Length:** ~3h05m",
    "",
    "## 重點摘要（中文）",
    "",
]
parts += [f"- `{t}` {txt}" for t, txt in EXEC]
parts += ["", "## Timestamped notes (EN)", ""]
parts += [f"- `{t}` {txt}" for t, txt in EN]
parts += ["", "## 時間軸重點（中文）", ""]
parts += [f"- `{t}` {ZH[t]}" for t, _ in EN]
parts += [
    "",
    "## Ticker board（提及）",
    "",
    "| Ticker | 立場／備註 |",
    "|---|---|",
    "| SNDK | 主力空；較大倉；多週期 EMA／50 EMA |",
    "| SK Hynix | 較大空；鍾意圖／韓國；買力限制加倉 |",
    "| IREN | Inverse-EP／5m breakdown；買力唔夠 skip |",
    "| MU | 靠近 gap + 1H/4H EMA |",
    "| HIMS | 早段周線 OK；後段弱／失 EMA |",
    "| SOXX | 靠近 daily 9 |",
    "| CRCL | 已賣；先前有抬結構 stop |",
    "| PATH | 已賣 |",
    "| XYZ | 留久啲；亦用作 2021 選擇性市況比喻 |",
    "| RBRK | 暴力反轉（約 10%/1m） |",
    "| TSLA | 50 EMA reject — short 或遲 |",
    "| IBM | Reject 未填 gap → 9/21 |",
    "| OSK | 想等彈 ~127.75-128 再短 |",
    "| GLW | 技術更弱短標；vs SK Hynix |",
    "| CRM | 伸展例：約高 9 EMA 25% |",
    "| FTNT | 留／賣視乎入場日 |",
    "| APLD / OLLI | yesterday weak-name short traction |",
    "| HOOD | Watchlist bucket |",
    "| RDDT | strong - do not short weak name in strong sector |",
    "| IGV | too extended - skip software long |",
    "| QQQ / SPY / IWM | breadth / key levels; late flush hourly 9 |",
    "",
]

OUT.write_text("\n".join(parts), encoding="utf-8")
print(f"wrote {OUT} en={len(EN)} zh={len(EN)} exec={len(EXEC)} fffd={OUT.read_text(encoding='utf-8').count(chr(0xfffd))}")
