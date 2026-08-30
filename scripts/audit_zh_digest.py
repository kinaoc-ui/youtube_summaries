"""Audit Chinese paraphrases against ASR English — print mismatches."""
from __future__ import annotations

import re
import sys

from app.dual_asr_build import build_dual_confirmed_rows
from app.zh_digest import _action_tags, _speech_zh


def main() -> int:
    built = build_dual_confirmed_rows("EhTGyU44w9M", model="small")
    issues: list[tuple] = []
    for r in built["rows"]:
        if r.get("confidence") == "gap":
            continue
        blob = f"{r.get('text') or ''} {r.get('reason') or ''}".strip()
        low = blob.lower()
        lab = str(r.get("label") or "").lower()
        zh = _speech_zh(str(r.get("label")), str(r.get("side") or ""), blob)
        flags: list[str] = []
        if "wait for" in low and "gap down" in low:
            if "今日已" in zh or "今日 gap" in zh or "已經 gap" in zh or "今日我哋有 gap down" in zh:
                flags.append("WAIT_GAP_AS_TODAY")
            if "等 gap down" not in zh and "最好等" not in zh:
                flags.append("WAIT_GAP_MISSING")
        if ("今日已 gap" in zh or "今日已經 gap" in zh or "今日 gap down" in zh) and not re.search(
            r"today we got a gap down|got a gap down|we get the market to gap down",
            low,
        ):
            flags.append("TODAY_GAP_BAD")
        if "再入場" in zh and not re.search(r"re-?enter", low):
            flags.append("REENTER_NO_SOURCE")
        if "mute" in zh.lower() and "mute" not in low:
            flags.append("MUTE_NO_SOURCE")
        acts = _action_tags(blob, str(r.get("label") or ""))
        if any("買入" in a for a in acts) and "trial" in low:
            flags.append("BOUGHT_TRIAL")
        if "shortable" in zh and "shortable" not in low:
            flags.append("SHORTABLE_NO_SOURCE")
        if "NVDA 業績" in zh and "nvidia" not in low and "nvda" not in low:
            flags.append("NVDA_NO_SOURCE")
        if zh.startswith("偏向") or not zh:
            flags.append("WEAK_FALLBACK")
        if "有強勢" in zh or "仍有強勢" in zh:
            if not re.search(
                r"strength|strong|pretty good|doing pretty well|decent spot|breaking out",
                low,
            ):
                flags.append("STRENGTH_WEAK")
        if "平倉" in zh or "平 CRCL" in zh:
            if "close" not in low and "crcl" not in low:
                flags.append("CLOSE_WEAK")
        if lab == "semis" and ("再入場" in zh or "re-enter" in zh.lower()):
            flags.append("SEMIS_POLLUTED_FTNT")
        if lab == "spy" and "破位" in zh and "break" not in low:
            flags.append("SPY_FAKE_BREAKOUT")
        if lab == "crcl" and "hourly 50" in zh and "hourly 50" not in low:
            flags.append("CRCL_POLLUTED_EMA")
        if lab == "spcx" and ("shortable" in zh or "hourly 50" in zh) and "shortable" not in low:
            flags.append("SPCX_POLLUTED_QUANTUM")
        # "提到 gap down" alone is ok if gap down in text
        print(f"--- {r.get('t')} {r.get('label')} | {r.get('side')} | {r.get('confidence')}")
        print("EN:", blob[:240].replace("\n", " "))
        print("ZH:", zh)
        if flags:
            print("!!", ",".join(flags))
            issues.append((r.get("t"), r.get("label"), flags, zh))
    print("==== ISSUES", len(issues))
    for t, lab, fl, zh in issues:
        print(f"{t} {lab}: {fl} | {zh}")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
