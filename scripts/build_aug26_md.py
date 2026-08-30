# -*- coding: utf-8 -*-
"""Too early on cyber longs | 26 Aug 2026 — speech-first summary.

Whisper has large gaps (~07:28–17:18, ~17:47–1:05:30, etc.). Only claim
tickers that appear in surviving ASR (with listed alias fixes).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "EhTGyU44w9M.md"

EXEC = [
    ("00:00", "**字幕缺口** | — | Whisper 大段空白 | 約 07:28–17:18、17:47–1:05:30 等缺語音；以下只寫有字幕段落。畫面核對可補。"),
    ("03:57", "**大方向** | 偏空指數 | 睇 Qs 弱／短機會 | Gap 穿 60m 9&21；Qs 昨日拒 daily 9/21"),
    ("05:00", "**SPCX** | Short（考慮） | 考慮今日 flip short | 原文 considering flipping short on SpaceX（WhisperX 字級；段首 04:28 係 Qs）"),
    ("05:47", "**Quantum** | Short（考慮） | maybe shortable today | 原文 maybe the quantum's looking a little bit shortable today"),
    ("06:08", "**SMCI** | Watch／相對強 | 強 semi 之一 | ASR SMC IRD＝SMCI；近業績"),
    ("07:28", "**ORCL** | Long／破位 | 跟突破（之前止蝕多次） | ASR auricle＝ORCL breaking out"),
    ("17:18", "**Cyber** | Long 太早 | 等 software／dip 支援 | Too early on cyber longs；software 撐住"),
    ("1:05:30", "**Semis** | Short／好弱 | 拒 declining 9／21 | Sammy's／Sambies＝semis；擔心弱勢蔓延"),
    ("1:10:04", "**NVDA** | Watch | 今日業績 | NVIDIA earnings today"),
    ("1:10:07", "**IONQ / ALAB / RKLB / ASTS** | Watch | 名單追蹤 | 原文連讀"),
    ("1:12:37", "**IWM** | Watch | 同 semi 一齊弱會好難做 | 原文 IWM + semis"),
    ("1:13:31", "**SMTC** | Watch | Reclaim open／VWAP | 原文 SMTC reclaiming opening；今日唔買、追蹤強弱"),
    ("1:15:14", "**CRWV** | Short | 好短位 | ASR CORE VIVA＝CRWV good short"),
    ("1:22:04", "**TEM** | Long／追蹤 | Flag 失敗後 pullback buy（~64） | 覺得少有更好；睇市況／板塊"),
    ("1:23:32", "**WULF** | Long／強 | 21 EMA 支援 | ASR Willio＝WULF（未百分百；畫面可核）"),
    ("1:30:47", "**FTNT / PANW** | Watch／猶豫 | 試多次唔夠信心 | ASR FDNT＝FTNT；同 PANW"),
    ("1:31:31", "**Software** | Long／dip | Gap 入 unfilled 可買 | Software 板塊 gap down 係 decent spot"),
    ("1:34:07", "**Cyber** | Long／等 flush | 唔好買 hourly EMA | 等早段 gap／flush，買 daily／weekly 位"),
    ("1:37:48", "**SNDK** | Long 止蝕 | 已 stopped out | Oops I got stopped up on SNDK"),
    ("1:40:44", "**CRCL** | Trim／考慮平 | 考慮 close | 唔鍾意而家 crypto action"),
    ("1:43:01", "**ASTS / IONQ / ALAB** | Watch | 再提及 | ASR 重複讀"),
    ("1:48:21", "**QQQ** | Watch／轉強 | 收復 9&21 | 先弱後印強 candle；SPY/IWM 相對強 → 唔好太 bearish"),
    ("1:49:18", "**SPY / IWM** | Watch | 等收上 9 再穩陣 | 相對 Qs 強；safer＝breakout 後 pullback"),
    ("1:53:29", "**Cyber** | 仍強 | 市太分裂可離場 | Cyber 仲強；bifurcated → step away；唔好 force trade"),
]

EN = [
    ("03:04", "Open: gap below 60m 9&21; Qs weak after daily 9/21 reject"),
    ("05:00", "Considering flip short SPCX today"),
    ("05:47", "Quantum looking a little bit shortable today"),
    ("05:58", "SMCI among stronger semis"),
    ("07:28", "ORCL (ASR auricle) breaking out after prior stops"),
    ("17:18", "Too early on cyber longs — finding support with software"),
    ("1:05:30", "Market rejecting declining 9; semis very weak; contagion worry"),
    ("1:10:04", "NVDA earnings today; IONQ/ALAB/RKLB/ASTS names"),
    ("1:13:31", "SMTC reclaiming open; CRWV (CORE VIVA) good short"),
    ("1:22:04", "TEM best-looking — pullback buy after failed flag ~64"),
    ("1:23:32", "WULF (ASR Willio) strong on 21 EMA"),
    ("1:30:47", "FTNT/PANW — hesitated after many tries"),
    ("1:31:31", "Software gap into unfilled = decent long spot; wait flush not hourly EMA chase"),
    ("1:37:48", "Stopped out SNDK; considering close CRCL (crypto soft)"),
    ("1:48:21", "QQQ recovers 9&21; SPY/IWM stronger — not super bearish"),
    ("1:55:12", "Cyber still strong; market bifurcated — step away"),
]

ZH = [
    ("03:04", "開場：Gap 穿 60m 9&21；Qs 弱"),
    ("05:00", "考慮今日短 SPCX"),
    ("05:47", "Quantum 今日 maybe shortable"),
    ("05:58", "SMCI 相對強"),
    ("07:28", "ORCL（ASR auricle）破位"),
    ("17:18", "Cyber long 太早；software 撐住"),
    ("1:05:30", "拒 declining 9；semis 好弱；擔心蔓延"),
    ("1:10:04", "NVDA 業績；IONQ／ALAB／RKLB／ASTS"),
    ("1:13:31", "SMTC reclaim；CRWV（CORE VIVA）好短"),
    ("1:22:04", "TEM 最好睇 — flag 後 pullback"),
    ("1:23:32", "WULF（ASR Willio）強、企 21"),
    ("1:30:47", "FTNT／PANW 試多次唔敢入"),
    ("1:31:31", "Software gap 可買；等 flush 唔追 hourly"),
    ("1:37:48", "SNDK 止蝕；考慮平 CRCL"),
    ("1:48:21", "QQQ 收復 9&21；SPY/IWM 相對強"),
    ("1:55:12", "Cyber 仲強；市分裂 → 離場"),
]

parts = [
    "# Too early on cyber longs | 26 Aug 2026",
    "",
    "- **Video:** [EhTGyU44w9M](https://www.youtube.com/watch?v=EhTGyU44w9M)",
    "- **Channel:** martinlukkt",
    "- **Source:** auto+cursor（Whisper；大段空白已標；語音閘）",
    "- **Length:** ~2h",
    "",
    "## 重點摘要（中文）",
    "",
]
parts += [f"- `{t}` {txt}" for t, txt in EXEC]
parts += ["", "## Timestamped notes (EN)", ""]
parts += [f"- `{t}` {txt}" for t, txt in EN]
parts += ["", "## 時間軸重點（中文）", ""]
parts += [f"- `{t}` {txt}" for t, txt in ZH]
parts.append("")

OUT.write_text("\n".join(parts), encoding="utf-8")
print("wrote", OUT, "exec", len(EXEC))
