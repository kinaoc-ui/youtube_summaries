"""Turn dual-ASR rows into a short Chinese digest (real summary, not ASR dump)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .parse_md import stamp_md_link
from .speech_zh import translate_speech_zh

# #region agent log
_DBG = Path(__file__).resolve().parents[1] / "debug-ec629f.log"


def _dbg(hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    try:
        with _DBG.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "ec629f",
                        "hypothesisId": hypothesis_id,
                        "location": location,
                        "message": message,
                        "data": data,
                        "timestamp": int(time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass


# #endregion


# Spoken cues that he actually traded / is in a position (not just watch).
_ACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"re-?enter", re.I), "再入場"),
    (re.compile(r"close my|closing my|should like close my|close my \w+", re.I), "講緊平倉"),
    (re.compile(r"\bi bought\b|\bbought the\b|i'm buying|i am buying", re.I), "講買入"),
    (re.compile(r"too early on .{0,24}long", re.I), "已有倉（話太早）"),
    (re.compile(r"stopped me out|got stopped", re.I), "之前止蝕離場"),
    (re.compile(r"trim(?:ming)? my|i'?m trimming|take(?:ing)? off (?:some|my)", re.I), "減倉中"),
    (re.compile(r"i'?m (?:getting )?long|got long|went long", re.I), "已做多"),
    (re.compile(r"i'?m (?:getting )?short|got short|went short|i shorted", re.I), "已做空"),
    (re.compile(r"good short", re.I), "問／考慮短"),
]


def _side_zh(side: str) -> str:
    s = str(side or "")
    if "shortable" in s.lower() or "Short（考慮）" in s:
        return "考慮短"
    if re.search(r"\bshort\b|做空|偏空", s, re.I):
        return "偏空／短"
    if "Trim" in s or "平倉" in s:
        return "考慮減／平"
    if re.search(r"\blong\b|偏多", s, re.I):
        return "偏多／長"
    return "觀望"


def _bucket(side_zh: str) -> str:
    if "減" in side_zh or "平" in side_zh:
        return "trim"
    if "短" in side_zh or "空" in side_zh:
        return "short"
    if "多" in side_zh or "長" in side_zh:
        return "long"
    return "watch"


def _blob(r: dict[str, Any]) -> str:
    return f"{r.get('text') or ''} {r.get('reason') or ''}"


def _action_tags(text: str, label: str = "") -> list[str]:
    low = text or ""
    out: list[str] = []
    skip_bought = bool(re.search(r"\btrial\b", low, re.I))
    for pat, tag in _ACTION_PATTERNS:
        if skip_bought and "買入" in tag:
            continue
        if pat.search(low) and tag not in out:
            out.append(tag)
    return out


def _actions_for_label(label: str, rs: list[dict[str, Any]], all_rows: list[dict[str, Any]]) -> list[str]:
    tags: list[str] = []
    for r in rs:
        for t in _action_tags(_blob(r), label):
            if t not in tags:
                tags.append(t)
    if label.lower() == "cyber":
        for r in all_rows:
            blob = _blob(r)
            if re.search(r"too early on .{0,24}long", blob, re.I) and re.search(
                r"cypress|cyber", blob, re.I
            ):
                if "已有倉（話太早）" not in tags:
                    tags.append("已有倉（話太早）")
    return tags


def _reason_bits(label: str, side: str, text: str) -> list[str]:
    low = (text or "").lower()
    lab = (label or "").lower()
    bits: list[str] = []
    wait_gap = bool(re.search(r"wait for (?:the\s+)*gap down", low))
    got_gap = bool(
        re.search(
            r"today we got a gap down|got a gap down|we get the market to gap down",
            low,
        )
    )
    if "qs" in low or "q's" in low or "qz" in low:
        bits.append("Qs 弱／拒 daily 9&21")
    if wait_gap:
        bits.append("等 gap down／早市 flush 先買 dips")
    elif got_gap:
        bits.append("今日已 gap down")
    elif "gap down" in low and "wait for" not in low:
        bits.append("gap down")
    if "hourly 50" in low or "hourly fifty" in low:
        bits.append("落 hourly 50")
    if "shortable" in low or "good short" in low:
        bits.append("或 shortable／good short")
    if "breaking out" in low or "breakout" in low:
        bits.append("破位／轉強")
    if "stopped" in low:
        bits.append("之前止蝕／試多次")
    if "reject" in low and "nine" in low:
        bits.append("拒 declining 9")
    if "earnings" in low or "nvidia" in low or lab == "nvda":
        bits.append("NVDA 業績後或轉方向")
    if "reclaim" in low and lab == "smtc":
        bits.append("reclaim open／VWAP，今日唔急買")
    if "support" in low and ("21" in low or "ema" in low):
        bits.append("企穩 21 EMA")
    if "software" in low and "gap" in low and not wait_gap:
        bits.append("software gap 填缺口可關注")
    if "cypress" in low or re.search(r"too early on .{0,24}(cyber|cypress)", low):
        bits.append("cyber long 太早；software 有撐")
    if "crypto" in low or lab == "crcl":
        bits.append("唔鐘意 crypto，考慮平")
    if "recover" in low or "strong candle" in low:
        bits.append("強燭收復 9&21")
    if "follow through" in low or "downside" in low:
        bits.append("或跟空／向下")
    if "not very confident" in low or "aggressive" in low:
        bits.append("短倉唔敢太進取")
    if "re-entering" in low or "reentering" in low:
        bits.append("再入場")
    if "bouncing" in low:
        if "hourly 21" in low or "hourly twenty" in low:
            bits.append("反彈，睇 hourly 21")
        else:
            bits.append("反彈／回測")
    if "strength" in low and lab in {"cyber", "wulf", "smci", "semis"}:
        bits.append("仍有強勢")
    if re.search(r"better to wait|wait for the extension", low) and not wait_gap:
        bits.append("建議再等一等先入")
    return bits


def _reason_zh(label: str, side: str, text: str, conf: str = "") -> str:
    bits = _reason_bits(label, side, text)
    if not bits:
        bits = [_side_zh(side)]
    return "；".join(bits[:3])


def _merge_reasons(label: str, rs: list[dict[str, Any]]) -> str:
    seen: list[str] = []
    for r in rs:
        for b in _reason_bits(label, str(r.get("side") or ""), _blob(r)):
            if b not in seen:
                seen.append(b)
    if not seen:
        seen = [_side_zh(str(rs[-1].get("side") or ""))]
    return "；".join(seen[:4])


def _side_arc(rs: list[dict[str, Any]]) -> str | None:
    """Describe real side evolution — never invent 偏多 if he never went long."""
    seq: list[str] = []
    for x in rs:
        b = _bucket(_side_zh(str(x.get("side") or "")))
        if not seq or seq[-1] != b:
            seq.append(b)
    if len(seq) < 2:
        return None
    names = {"long": "偏多", "short": "偏空／短", "trim": "減／平", "watch": "觀望"}
    return "→".join(names.get(s, s) for s in seq)


def _session_lede(groups: list[tuple[str, str, str]]) -> str:
    """Overview must match the buckets below — no hardcoded other-day template."""
    by_b: dict[str, list[str]] = {"long": [], "short": [], "trim": [], "watch": []}
    for label, bucket, _reason in groups:
        by_b.setdefault(bucket, []).append(label)
    parts: list[str] = []
    if by_b["short"]:
        parts.append("做空／偏空：" + "、".join(by_b["short"][:6]))
    if by_b["long"]:
        parts.append("做多／偏多：" + "、".join(by_b["long"][:6]))
    if by_b["trim"]:
        parts.append("減／平：" + "、".join(by_b["trim"][:4]))
    watch_theme = [x for x in by_b["watch"] if x.lower() in {"software", "cyber", "quantum", "semis"}]
    if watch_theme and not by_b["long"] and not by_b["short"]:
        parts.append("觀望：" + "、".join(watch_theme[:5]))
    elif not parts:
        parts.append("今日以觀望為主")
    return "；".join(parts) + "。"


def build_zh_digest(rows: list[dict[str, Any]], video_id: str = "") -> list[str]:
    """Grouped Chinese digest: 實際操作 + 做多/做空/減倉/觀望. No meta/mute lines."""
    by_label: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if r.get("confidence") == "gap":
            continue
        label = str(r.get("label") or r.get("ticker") or "?").strip()
        if not label or label == "字幕缺口":
            continue
        by_label.setdefault(label, []).append(r)

    buckets: dict[str, list[str]] = {"long": [], "short": [], "trim": [], "watch": []}
    actions: list[str] = []
    groups: list[tuple[str, str, str]] = []

    for label, rs in by_label.items():
        rs = sorted(rs, key=lambda x: float(x.get("start") or 0))
        last = rs[-1]
        # Last actionable side wins — trailing Watch must not erase Short/Long/Trim
        pick = last
        for x in rs:
            if _bucket(_side_zh(str(x.get("side") or ""))) != "watch":
                pick = x
        side = _side_zh(str(pick.get("side") or ""))
        reason = _merge_reasons(label, rs)
        arc = _side_arc(rs)
        if arc and label.lower() in {"semis", "software", "cyber"}:
            reason = f"{arc}；{reason}" if reason else arc

        tags = _actions_for_label(label, rs, rows)
        if label.lower() == "software":
            tags = [t for t in tags if "已有倉" not in t]
            reason = re.sub(r"cyber long 太早；?", "", reason).strip("；")
        bucket = _bucket(side)
        if bucket != "watch" and (not reason or reason == "觀望"):
            reason = side
        # #region agent log
        _dbg(
            "H2",
            "zh_digest.build_zh_digest",
            "bucket_pick",
            {
                "label": label,
                "last_side": str(last.get("side") or ""),
                "pick_side": str(pick.get("side") or ""),
                "pick_t": pick.get("t"),
                "bucket": bucket,
            },
        )
        # #endregion
        tlink = stamp_md_link(video_id, str(pick.get("t") or "")) if video_id else ""
        tbit = f" {tlink}" if tlink else ""
        if tags:
            actions.append(
                f"- **實際操作｜{label}**{tbit} — {'；'.join(tags)}（{_bucket_title(bucket)}）"
            )

        line = f"- **{_bucket_title(bucket)}｜{label}**{tbit} — {reason}"
        buckets[bucket].append(line)
        groups.append((label, bucket, reason))

    lede = _session_lede(groups)
    lines: list[str] = [
        f"- **今日總覽** — {lede}",
    ]
    lines.extend(actions)

    for key, _title in (
        ("long", "做多"),
        ("short", "做空"),
        ("trim", "減倉／平倉"),
        ("watch", "觀望"),
    ):
        lines.extend(buckets[key])

    if len(lines) <= 1:
        lines.append("- （未有足夠雙 ASR 內容可寫摘要）")
    # #region agent log
    bugs: list[dict[str, Any]] = []
    for label, bucket, reason in groups:
        rlow = (reason or "").lower()
        if bucket == "short" and re.search(r"強勢|偏多|做多", reason or ""):
            bugs.append({"kind": "H1_short_vs_bull", "label": label, "bucket": bucket, "reason": reason})
        if bucket == "long" and re.search(r"偏空|做空|shortable|跟空", reason or ""):
            bugs.append({"kind": "H1_long_vs_bear", "label": label, "bucket": bucket, "reason": reason})
        if "仍有強勢" in (reason or "") and bucket == "short":
            bugs.append({"kind": "H3_strength_on_short", "label": label, "reason": reason})
        if "早段偏多" in (reason or ""):
            bugs.append({"kind": "H2_fake_arc", "label": label, "reason": reason})
        rs = by_label.get(label) or []
        sides = [str(x.get("side") or "") for x in rs]
        texts = [str(x.get("text") or "")[:120] for x in rs]
        if label.upper() in {"FIG", "SOFTWARE", "SEMIS"} or bugs:
            _dbg(
                "H2",
                "zh_digest.build_zh_digest",
                "group_detail",
                {
                    "label": label,
                    "bucket": bucket,
                    "side_last": str((rs[-1].get("side") if rs else "") or ""),
                    "sides": sides,
                    "reason": reason,
                    "texts": texts,
                },
            )
    lede_short = re.findall(r"做空／偏空：([^；。]+)", lede)
    lede_long = re.findall(r"做多／偏多：([^；。]+)", lede)
    short_set = {x.strip() for part in lede_short for x in part.split("、") if x.strip()}
    long_set = {x.strip() for part in lede_long for x in part.split("、") if x.strip()}
    for lab, b, _r in groups:
        if lab in short_set and b != "short":
            bugs.append({"kind": "H1_lede_mismatch", "label": lab, "bucket": b, "lede": "short"})
        if lab in long_set and b != "long":
            bugs.append({"kind": "H1_lede_mismatch", "label": lab, "bucket": b, "lede": "long"})
    _dbg(
        "H1",
        "zh_digest.build_zh_digest",
        "digest_scan",
        {
            "lede": lede,
            "groups": [{"label": a, "bucket": b, "reason": c} for a, b, c in groups],
            "bugs": bugs,
            "bug_count": len(bugs),
        },
    )
    # #endregion
    return lines


def _bucket_title(key: str) -> str:
    return {
        "long": "做多",
        "short": "做空",
        "trim": "減倉",
        "watch": "觀望",
    }.get(key, "觀望")


def _speech_zh(label: str, side: str, text: str) -> str:
    """Faithful Chinese of the spoken English. label/side do not change wording."""
    return translate_speech_zh(text)


def _source_zh(r: dict[str, Any]) -> str:
    if r.get("quote_source") == "cc":
        return {
            "dual": "YouTube字幕＋雙ASR核對",
            "whisperx": "YouTube字幕＋WhisperX",
            "faster": "YouTube字幕＋faster",
            "captions": "YouTube字幕",
        }.get(str(r.get("confidence") or ""), "YouTube字幕")
    return "雙ASR確認" if r.get("confidence") == "dual" else "WhisperX"


def _source_en(r: dict[str, Any]) -> str:
    if r.get("quote_source") == "cc":
        return {
            "dual": "YouTube CC + dual ASR",
            "whisperx": "YouTube CC + WhisperX",
            "faster": "YouTube CC + faster-whisper",
            "captions": "YouTube CC",
        }.get(str(r.get("confidence") or ""), "YouTube CC")
    return "dual ASR" if r.get("confidence") == "dual" else "WhisperX"


def _stamp(r: dict[str, Any], video_id: str) -> str:
    t = str(r.get("t") or "")
    return stamp_md_link(video_id, t) if video_id else f"`{t}`"


def content_zh_line(r: dict[str, Any], video_id: str = "") -> str:
    """Timeline content — faithful Chinese of the quote English (CC or ASR)."""
    stamp = _stamp(r, video_id)
    if r.get("confidence") == "gap":
        return (
            f"- {stamp} **字幕缺口** | — | 咪 mute／無語音 | "
            f"{r.get('reason') or '兩邊 ASR 近乎空白'}"
        )
    conf = _source_zh(r)
    side = r.get("side") or "Watch"
    label = str(r.get("label") or "?")
    blob = str(r.get("text") or "").strip()
    if len(blob) < 12:
        blob = (blob + " " + str(r.get("reason") or "")).strip()
    say = translate_speech_zh(blob)
    if len(say) > 420:
        say = say[:417] + "…"
    return f"- {stamp} **{label}** | {side} | {conf} | {say}"


def content_en_line(r: dict[str, Any], video_id: str = "") -> str:
    """Same timeline rows as ZH, but with raw ASR English (no paraphrase)."""
    stamp = _stamp(r, video_id)
    if r.get("confidence") == "gap":
        return (
            f"- {stamp} **Mute gap** | — | mic muted / no speech | "
            f"{r.get('reason') or 'both ASR streams nearly empty'}"
        )
    conf = _source_en(r)
    side = r.get("side") or "Watch"
    label = str(r.get("label") or "?")
    blob = str(r.get("text") or "").strip()
    if len(blob) < 12:
        blob = (blob + " " + str(r.get("reason") or "")).strip()
    # Keep spoken English; trim only runaway length
    en = re.sub(r"\s+", " ", blob).strip()
    if len(en) > 520:
        en = en[:517] + "…"
    return f"- {stamp} **{label}** | {side} | {conf} | {en}"
