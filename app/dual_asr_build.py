"""Build exec summary from faster-whisper ∩ WhisperX (high confidence) + WhisperX-only."""
from __future__ import annotations

import re
from typing import Any

from .asr_compare import load_snippets
from .asr_fix import fix_asr
from .auto_summary import EXTRA_ALIASES, _infer_side, _window
from .zh_digest import build_zh_digest, content_en_line, content_zh_line
from .speech_audit import NEEDLES, nearest_speech_time, speech_hit
from .transcript import format_ts, load_caption_snippets
from .triple_check import _find_transcript_pair


SKIP = {"GOLD", "SK HYNIX"}
_NOISE = {"you", "and", "yeah", "uh", "um", "hmm", "oh", "ok", "okay", "yes", "no"}


def _hits_from(snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from .auto_summary import _find_ticker_hits

    return _find_ticker_hits(snippets)


def _real_speech_ends(snippets: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """(start, end) of segments that are real speech, not VAD junk."""
    out: list[tuple[float, float]] = []
    for s in snippets:
        text = fix_asr(str(s.get("text") or "")).strip()
        low = text.lower().strip(" .,!")
        if len(text) < 12 or low in _NOISE:
            continue
        st = float(s.get("start") or 0)
        dur = float(s.get("duration") or 0) or max(2.0, len(text) * 0.04)
        out.append((st, st + dur))
    out.sort()
    return out


def find_mute_gaps(
    a: list[dict[str, Any]],
    b: list[dict[str, Any]],
    *,
    min_gap_sec: float = 480.0,
    primary: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Gaps with no real speech. Prefer YouTube CC spans when CC is the quote source."""
    spans = _real_speech_ends(primary) if primary else []
    if not spans:
        spans = _real_speech_ends(b) or _real_speech_ends(a)
    if not spans:
        return []
    merged: list[list[float]] = [list(spans[0])]
    for st, en in spans[1:]:
        if st <= merged[-1][1] + 30:
            merged[-1][1] = max(merged[-1][1], en)
        else:
            merged.append([st, en])
    gaps: list[dict[str, Any]] = []
    for i in range(len(merged) - 1):
        gap_start = merged[i][1]
        gap_end = merged[i + 1][0]
        if gap_end - gap_start < min_gap_sec:
            continue
        mid_chars = 0
        for s in a:
            st = float(s.get("start") or 0)
            if gap_start <= st < gap_end:
                t = fix_asr(str(s.get("text") or "")).strip()
                if t.lower().strip(" .,!") not in _NOISE:
                    mid_chars += len(t)
        note = "兩邊 ASR 都冇正常語音"
        if primary is not None:
            note = "字幕同語音都近乎空白（疑似咪 mute／冇講嘢）"
        elif mid_chars < 40:
            note = "疑似咪 mute／冇講嘢（faster+WhisperX 都近乎空白）"
        gaps.append(
            {
                "start": gap_start,
                "end": gap_end,
                "t": format_ts(gap_start),
                "t_end": format_ts(gap_end),
                "minutes": round((gap_end - gap_start) / 60, 1),
                "note": note,
                "confidence": "gap",
                "label": "字幕缺口",
                "ticker": "字幕缺口",
                "side": "—",
                "reason": f"{format_ts(gap_start)}–{format_ts(gap_end)} 約 {(gap_end - gap_start) / 60:.0f} 分鐘：{note}",
                "text": note,
            }
        )
    return gaps


def _nearby(hit: dict[str, Any], others: list[dict[str, Any]], window: float = 120.0) -> dict[str, Any] | None:
    tick = str(hit.get("ticker") or "").upper()
    t0 = float(hit.get("start") or 0)
    for o in others:
        if str(o.get("ticker") or "").upper() != tick:
            continue
        if abs(float(o.get("start") or 0) - t0) <= window:
            return o
    return None


def _rows_from_captions(
    cc: list[dict[str, Any]],
    a: list[dict[str, Any]],
    b: list[dict[str, Any]],
) -> dict[str, Any]:
    """YouTube CC = quote + timeline; faster-whisper / WhisperX only verify tickers."""
    hc = _hits_from(cc)
    ha = _hits_from(a) if a else []
    hb = _hits_from(b) if b else []
    dual: list[dict[str, Any]] = []
    wx_only: list[dict[str, Any]] = []
    faster_only: list[dict[str, Any]] = []
    cc_only: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    for h in hc:
        tick = str(h.get("ticker") or "").upper()
        if tick in SKIP:
            continue
        wx = _nearby(h, hb)
        fw = _nearby(h, ha)
        if wx and fw:
            conf = "dual"
            dual.append({**h})
        elif wx:
            conf = "whisperx"
            wx_only.append({**h})
        elif fw:
            conf = "faster"
            faster_only.append({**h})
        else:
            conf = "captions"
            cc_only.append({**h})
        row = {
            **h,
            "confidence": conf,
            "quote_source": "cc",
            "label": _label(tick),
        }
        if any(
            abs(o["start"] - row["start"]) < 90 and o["ticker"].upper() == tick for o in out
        ):
            continue
        out.append(row)

    gaps = find_mute_gaps(a, b, min_gap_sec=480.0, primary=cc)
    merged = sorted(out + gaps, key=lambda r: float(r["start"]))
    return {
        "quote_source": "cc",
        "dual": dual,
        "wx_only": wx_only,
        "faster_only": faster_only,
        "cc_only": cc_only,
        "gaps": gaps,
        "rows": merged,
        "dual_count": len(dual),
        "wx_only_count": len(wx_only),
        "faster_only_count": len(faster_only),
        "cc_only_count": len(cc_only),
        "gap_count": len(gaps),
    }


def build_dual_confirmed_rows(video_id: str, *, model: str = "small") -> dict[str, Any]:
    """CC timeline when YouTube captions exist; else WhisperX∩faster as before."""
    w_path, x_path = _find_transcript_pair(video_id, model)
    a = load_snippets(w_path) if w_path else []
    b = load_snippets(x_path) if x_path else []
    cc = load_caption_snippets(video_id)
    if cc:
        return _rows_from_captions(cc, a, b)
    if not b:
        return {"dual": [], "wx_only": [], "faster_only": [], "rows": [], "quote_source": "asr"}

    ha, hb = _hits_from(a), _hits_from(b)
    used_b: set[int] = set()
    dual: list[dict[str, Any]] = []
    for i, hb_row in enumerate(hb):
        tick = hb_row["ticker"].upper()
        if tick in SKIP:
            continue
        match = None
        for ha_row in ha:
            if ha_row["ticker"].upper() != tick:
                continue
            if abs(ha_row["start"] - hb_row["start"]) <= 120:
                match = ha_row
                break
        if match:
            used_b.add(i)
            dual.append(
                {
                    **hb_row,
                    "confidence": "dual",
                    "quote_source": "asr",
                    "faster_t": match["t"],
                    "label": _label(tick),
                }
            )

    wx_only: list[dict[str, Any]] = []
    for i, hb_row in enumerate(hb):
        if i in used_b:
            continue
        tick = hb_row["ticker"].upper()
        if tick in SKIP:
            continue
        wx_only.append({**hb_row, "confidence": "whisperx", "quote_source": "asr", "label": _label(tick)})

    faster_only: list[dict[str, Any]] = []
    for ha_row in ha:
        tick = ha_row["ticker"].upper()
        if tick in SKIP:
            continue
        if any(
            hb_row["ticker"].upper() == tick and abs(hb_row["start"] - ha_row["start"]) <= 120
            for hb_row in hb
        ):
            continue
        if any(d["ticker"].upper() == tick and abs(d["start"] - ha_row["start"]) <= 120 for d in dual):
            continue
        faster_only.append({**ha_row, "confidence": "faster_only", "label": _label(tick)})

    rows = sorted(dual + wx_only, key=lambda r: r["start"])
    out: list[dict[str, Any]] = []
    for r in rows:
        if any(abs(o["start"] - r["start"]) < 90 and o["ticker"].upper() == r["ticker"].upper() for o in out):
            continue
        out.append(r)

    gaps = find_mute_gaps(a, b, min_gap_sec=480.0)
    merged_rows = sorted(out + gaps, key=lambda r: float(r["start"]))

    return {
        "quote_source": "asr",
        "dual": dual,
        "wx_only": wx_only,
        "faster_only": faster_only,
        "gaps": gaps,
        "rows": merged_rows,
        "dual_count": len(dual),
        "wx_only_count": len(wx_only),
        "faster_only_count": len(faster_only),
        "gap_count": len(gaps),
    }


def _label(tick: str) -> str:
    u = tick.upper()
    if u == "CYBER":
        return "Cyber"
    if u == "SEMIS":
        return "Semis"
    if u == "SOFTWARE":
        return "Software"
    if u == "QUANTUM":
        return "Quantum"
    return tick if tick != "QUANTUM" else "Quantum"


def patch_markdown_with_dual(video_id: str, md: str, *, model: str = "small") -> tuple[str, dict[str, Any]]:
    """Write 真正摘要（中文） + 時間軸內容(ZH) + Timeline content (EN ASR)."""
    built = build_dual_confirmed_rows(video_id, model=model)
    rows = built["rows"]
    digest_lines = build_zh_digest(rows)
    content_lines = [content_zh_line(r) for r in rows]
    content_en_lines = [content_en_line(r) for r in rows]
    if not content_lines:
        content_lines = ["- （字幕／ASR 未搵到 ticker）"]
        content_en_lines = ["- （no tickers）"]

    cc_mode = built.get("quote_source") == "cc"
    en_head = (
        "Time | Ticker | Long/Short | Source | YouTube CC English (original)"
        if cc_mode
        else "Time | Ticker | Long/Short | Source | ASR English (original)"
    )
    zh_intro = (
        "撳時間可跳片。有 YouTube 字幕就用字幕做原文；faster-whisper／WhisperX 只核對 ticker。"
        if cc_mode
        else "撳時間可跳片。摘要按做多／做空／減倉／觀望分組；細節喺時間軸。"
    )
    skip_heads = (
        "真正摘要",
        "時間軸內容",
        "Timeline content",
        "重點摘要",
        "時間軸／筆記",
        "時間軸重點",
        "Timestamped notes",
    )
    out: list[str] = []
    skipping = False
    inserted = False
    for line in md.splitlines():
        if line.startswith("## "):
            if any(h in line for h in skip_heads):
                if not inserted:
                    out.append("## 真正摘要（中文）")
                    out.append("")
                    out.append(zh_intro)
                    out.append("")
                    out.extend(digest_lines)
                    out.append("")
                    out.append("## 時間軸內容")
                    out.append("")
                    out.append("時間 | 股票 | Long/Short | 建議 | 語音中文翻譯")
                    out.append("")
                    out.extend(content_lines)
                    out.append("")
                    out.append("## Timeline content (EN)")
                    out.append("")
                    out.append(en_head)
                    out.append("")
                    out.extend(content_en_lines)
                    out.append("")
                    inserted = True
                skipping = True
                continue
            skipping = False
            out.append(line)
            continue
        if skipping:
            continue
        out.append(line)
    if not inserted:
        out.append("")
        out.append("## 真正摘要（中文）")
        out.append("")
        out.extend(digest_lines)
        out.append("")
        out.append("## 時間軸內容")
        out.append("")
        out.extend(content_lines)
        out.append("")
        out.append("## Timeline content (EN)")
        out.append("")
        out.extend(content_en_lines)

    text = "\n".join(out)
    text = re.sub(r"\n### 已刪[^\n]*\n(?:- `[^\n]*\n)*", "\n", text)
    return text, built
