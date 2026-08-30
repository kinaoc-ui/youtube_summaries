"""After ASR compare: verify exec tickers against BOTH ASR streams and patch the summary."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .asr_compare import load_snippets
from .config import DATA_DIR, ROOT, SUMMARY_DIR
from .parse_md import parse_summary_markdown
from .speech_audit import (
    NEEDLES,
    SKIP_LABELS,
    TICKER_FROM_EXEC,
    nearest_speech_time,
    speech_hit,
    window_text,
)
from .transcript import format_ts
from .triple_check import _find_transcript_pair, load_report
from .video_check import parse_ts

# Chart won't show theme words — don't slap 畫面唔同＝SPCX on Quantum/Cyber/Semis
_THEME_TICKERS = {"QUANTUM", "CYBER", "SEMIS", "SOFTWARE"}

# #region agent log
_DBG = ROOT / "debug-ec629f.log"
# #endregion

FLAG_NONE = "⚠雙ASR未見"
FLAG_FASTER_ONLY = "⚠只得faster已刪"
FLAG_B = "⚠單邊ASR(whisperx)"
FLAG_B_OK = "單邊ASR(X)+畫面確認"
FLAG_SCREEN_DIFF = "⚠畫面唔同"
FLAG_RE = re.compile(
    r"\s*｜(?:⚠)?(?:語音未核實|雙ASR未見|只得faster已刪|單邊ASR\([^)]+\)|單邊ASR\+畫面確認|單邊ASR\(X\)\+畫面確認|畫面唔同(?:＝[^｜]*)?)"
)


def _load_pair_snippets(video_id: str, model: str = "small") -> tuple[list[dict], list[dict]]:
    w_path, x_path = _find_transcript_pair(video_id, model)
    a = load_snippets(w_path) if w_path else []
    b = load_snippets(x_path) if x_path else []
    if not a:
        from .transcript import load_transcript

        tr = load_transcript(video_id) or {}
        a = list(tr.get("snippets") or [])
    return a, b


def _ticker_parts(raw: str) -> list[str]:
    parts = re.split(r"\s*/\s*|\s*／\s*", raw)
    out = []
    for part in parts:
        part = re.sub(r"（.*?）|\(.*?\)", "", part).strip()
        if not part or part in SKIP_LABELS:
            continue
        out.append(part)
    return out


def _strip_flags(text: str) -> str:
    return FLAG_RE.sub("", text).rstrip()


def _timing_snap(center: float, desync: list[dict[str, Any]]) -> float | None:
    """If row sits in a timing_desync bucket, prefer WhisperX mean start."""
    for d in desync:
        if d.get("kind") != "timing_desync":
            continue
        t0 = parse_ts(str(d.get("t") or "0"))
        t1 = parse_ts(str(d.get("t_end") or "0"))
        if t0 <= center <= t1 + 0.01:
            # drift note already computed; snap toward later of means if present
            # We don't store means in report — use bucket start + half drift toward wx
            drift = float(d.get("drift_sec") or 0)
            # Prefer shifting toward WhisperX: report says content similar; use mid of bucket + sign
            return t0 + min(drift, 14.0) * 0.5
    return None


def _hit_side(ticker: str, blob: str) -> bool:
    if ticker.startswith("Quantum"):
        return "quantum" in blob or any(speech_hit(x, blob) for x in ("QBTS", "RGTI", "IONQ"))
    if ticker in {"金／銀", "金", "銀"}:
        return speech_hit("GOLD", blob)
    return speech_hit(ticker, blob)


def build_exec_actions(
    video_id: str,
    *,
    report: dict[str, Any] | None = None,
    model: str = "small",
) -> dict[str, Any]:
    """Per-exec verification against dual ASR (+ optional screen from report)."""
    report = report or load_report(video_id) or {}
    md_path = SUMMARY_DIR / f"{video_id}.md"
    if not md_path.exists():
        return {"video_id": video_id, "error": "no markdown", "actions": []}
    md = md_path.read_text(encoding="utf-8")
    parsed = parse_summary_markdown(md)
    a_snips, b_snips = _load_pair_snippets(video_id, model)
    desync = ((report.get("asr") or {}).get("desync") or [])
    labels_path = DATA_DIR / "frames" / video_id / "labels.json"
    labels: dict[str, Any] = {}
    if labels_path.exists():
        try:
            labels = json.loads(labels_path.read_text(encoding="utf-8")).get("by_t") or {}
        except json.JSONDecodeError:
            labels = {}
    vision_by_t: dict[str, Any] = {}
    try:
        from .video_check import load_report as load_vision

        for it in (load_vision(video_id) or {}).get("items") or []:
            if it.get("t"):
                vision_by_t[str(it["t"])] = it
    except Exception:
        vision_by_t = {}
    screen_by_t = {
        str(m.get("t")): m for m in ((report.get("screen") or {}).get("mismatches") or [])
    }

    actions: list[dict[str, Any]] = []
    for row in parsed.get("content_zh") or parsed.get("exec_zh") or []:
        t = str(row.get("t") or "")
        text = _strip_flags(str(row.get("text") or ""))
        m = TICKER_FROM_EXEC.search(text)
        if not m:
            continue
        raw = m.group(1).strip()
        if raw in SKIP_LABELS:
            continue
        center = parse_ts(t) if t else 0.0
        parts = _ticker_parts(raw)
        if not parts:
            continue

        # Snap to true spoken time (WhisperX words / char offset in long segments)
        speech_times = []
        for p in parts:
            # Prefer WhisperX word timestamps, then faster-whisper estimate
            for snips in (b_snips, a_snips):
                nt = nearest_speech_time(snips, p, prefer_center=center) if snips else None
                if nt is not None:
                    speech_times.append(nt)
                    break
        # Earliest real spoken time among the row's tickers (WhisperX words preferred per ticker)
        spoken = min(speech_times) if speech_times else None
        # Never let ASR bucket desync override a real spoken timestamp
        if spoken is not None:
            snap = spoken if format_ts(spoken) != t else None
        else:
            snap = _timing_snap(center, desync)
        new_t = format_ts(snap) if snap is not None and format_ts(snap) != t else t
        # Re-check hits around the spoken time (tight window), not the wrong exec stamp
        check_at = float(spoken if spoken is not None else (snap if snap is not None else center))
        blob_a = window_text(a_snips, check_at, before=40, after=40) if a_snips else ""
        blob_b = window_text(b_snips, check_at, before=40, after=40) if b_snips else ""

        hits_a = [p for p in parts if _hit_side(p, blob_a)]
        hits_b = [p for p in parts if _hit_side(p, blob_b)]
        # Nearest Cursor label by time (discrete ±offsets miss 05:00→05:28)
        screen = None
        best_lab: tuple[float, str] | None = None
        for t_str, lab in labels.items():
            sym = lab.get("symbol")
            if not sym:
                continue
            try:
                ts = parse_ts(str(t_str))
            except Exception:
                continue
            d = abs(ts - check_at)
            if d <= 50.0 and (best_lab is None or d < best_lab[0]):
                best_lab = (d, str(sym))
        if best_lab:
            screen = best_lab[1]
        if not screen:
            vit = vision_by_t.get(new_t) or vision_by_t.get(t) or {}
            screen = vit.get("screen_symbol") or (vit.get("ocr_tickers") or [None])[0]
        if not screen:
            scr_row = screen_by_t.get(new_t) or screen_by_t.get(t) or {}
            screen = scr_row.get("screen") or (scr_row.get("ocr_tickers") or [None])[0]
        screen = str(screen).upper() if screen else None
        screen_ok = bool(
            screen
            and any(
                screen == p.upper() or p.upper().startswith(screen) or screen.startswith(p.upper())
                for p in parts
            )
        )

        # Policy: if WhisperX exists, faster-whisper–only hits are deleted (hallucination-prone)
        has_whisperx = bool(b_snips)
        if hits_a and hits_b:
            status = "ok_dual"
            flag = None
            if screen and not screen_ok and not any(p.upper() in _THEME_TICKERS for p in parts):
                status = "screen_diff"
                flag = f"{FLAG_SCREEN_DIFF}＝{screen}"
        elif hits_a and not hits_b:
            if has_whisperx:
                status = "drop"
                flag = FLAG_FASTER_ONLY
            elif screen_ok:
                status = "ok_a_screen"
                flag = "單邊ASR+畫面確認"
            elif screen:
                status = "screen_diff"
                flag = f"{FLAG_SCREEN_DIFF}＝{screen}（語音只有 faster）"
            else:
                status = "ok_a"
                flag = "⚠單邊ASR(faster)"
        elif hits_b and not hits_a:
            if screen_ok:
                status = "ok_b_screen"
                flag = FLAG_B_OK
            elif screen:
                status = "screen_diff"
                flag = f"{FLAG_SCREEN_DIFF}＝{screen}（語音只有 WhisperX）"
            else:
                status = "ok_b"
                flag = FLAG_B
        elif screen_ok:
            status = "ok_screen"
            flag = None
        elif screen:
            # Has chart label but speech window empty / mismatch — keep row, don't silently drop
            status = "screen_diff"
            flag = f"{FLAG_SCREEN_DIFF}＝{screen}"
        else:
            status = "drop"
            flag = FLAG_NONE

        # Theme names never appear as TV chart symbol — ignore nearby QQQ/SPCX labels
        if status == "screen_diff" and any(p.upper() in _THEME_TICKERS for p in parts):
            if hits_a and hits_b:
                status, flag = "ok_dual", None
            elif hits_b:
                status, flag = "ok_b", None
            elif hits_a and not has_whisperx:
                status, flag = "ok_a", None
            # if faster-only + WhisperX present, keep drop from above
        if status == "drop" and flag == FLAG_FASTER_ONLY:
            pass  # never resurrect faster-only rows

        # ticker_desync buckets overlapping this row
        tick_conflict = []
        for d in desync:
            if d.get("kind") != "ticker_desync":
                continue
            t0 = parse_ts(str(d.get("t") or "0"))
            t1 = parse_ts(str(d.get("t_end") or "0"))
            if t0 <= center <= t1 + 0.01:
                tick_conflict.append(
                    {
                        "only_a": d.get("tickers_only_a") or [],
                        "only_b": d.get("tickers_only_b") or [],
                    }
                )

        actions.append(
            {
                "t": t,
                "new_t": new_t,
                "tickers": parts,
                "status": status,
                "flag": flag,
                "hits_a": hits_a,
                "hits_b": hits_b,
                "screen": screen,
                "screen_ok": screen_ok,
                "speech_at": format_ts(spoken) if spoken is not None else None,
                "tick_conflict": tick_conflict,
                "text": text[:180],
            }
        )

    keep = sum(1 for a in actions if a["status"] != "drop")
    drop = sum(1 for a in actions if a["status"] == "drop")
    drop_faster = sum(1 for a in actions if a.get("flag") == FLAG_FASTER_ONLY)
    single = sum(1 for a in actions if a["status"] in {"ok_a", "ok_b"})
    screen_ok_n = sum(1 for a in actions if a["status"] in {"ok_a_screen", "ok_b_screen", "ok_screen"})
    screen_diff = sum(1 for a in actions if a["status"] == "screen_diff")
    snapped = sum(1 for a in actions if a["new_t"] != a["t"])
    return {
        "video_id": video_id,
        "actions": actions,
        "keep": keep,
        "drop": drop,
        "drop_faster_only": drop_faster,
        "single_asr": single,
        "screen_confirm": screen_ok_n,
        "screen_diff": screen_diff,
        "timing_snapped": snapped,
        "hint": (
            f"核實 {keep} 保留／刪 {drop_faster} 只得faster／"
            f"{drop - drop_faster} 雙ASR未見／"
            f"{screen_ok_n} 畫面確認／{screen_diff} 畫面唔同／"
            f"{snapped} 改時間戳（信 WhisperX）"
        ),
    }


def apply_actions_to_markdown(md: str, actions: list[dict[str, Any]]) -> str:
    """Rewrite exec + EN/ZH timeline: snap times, add flags, move drop rows."""
    by_key = {}
    tick_to_new: dict[str, str] = {}
    for a in actions:
        for tick in a["tickers"]:
            by_key[(a["t"], tick.upper())] = a
            tick_to_new[tick.upper()] = a["new_t"] or a["t"]

    out: list[str] = []
    dropped_lines: list[str] = []
    in_exec = False
    in_timeline = False
    for line in md.splitlines():
        if line.startswith("## "):
            if in_exec and dropped_lines:
                out.append("")
                out.append("### 已刪（只得 faster-whisper／雙ASR未見）")
                out.extend(dropped_lines)
                dropped_lines = []
            in_exec = "時間軸內容" in line or "重點摘要" in line or line.strip() == "## Executive summary"
            in_timeline = "Timestamped notes" in line or "時間軸重點" in line or "時間軸／筆記" in line
            out.append(line)
            continue
        if in_exec and line.startswith("- `"):
            m = re.match(r"^- `([^`]+)`\s+(.+)$", line)
            if m:
                t, rest = m.group(1), _strip_flags(m.group(2))
                tm = TICKER_FROM_EXEC.search(rest)
                if tm:
                    tick = re.sub(r"（.*?）|\(.*?\)", "", tm.group(1)).strip().upper()
                    tick0 = tick.split("/")[0].split("／")[0].strip()
                    act = by_key.get((t, tick0))
                    if act:
                        new_t = act["new_t"] or t
                        flag = act.get("flag")
                        body = rest
                        if flag:
                            body = f"{body} ｜{flag}"
                        new_line = f"- `{new_t}` {body}"
                        if act["status"] == "drop":
                            dropped_lines.append(new_line)
                            continue
                        out.append(new_line)
                        continue
        if in_timeline and line.startswith("- `") and tick_to_new:
            m = re.match(r"^- `([^`]+)`\s+(.+)$", line)
            if m:
                t, rest = m.group(1), m.group(2)
                up = rest.upper()
                for tick, new_t in tick_to_new.items():
                    if re.search(rf"\b{re.escape(tick)}\b", up) and t != new_t:
                        line = f"- `{new_t}` {rest}"
                        break
        out.append(line)

    if in_exec and dropped_lines:
        out.append("")
        out.append("### 已刪（只得 faster-whisper／雙ASR未見）")
        out.extend(dropped_lines)

    return "\n".join(out)


def reconcile_summary_from_compare(
    video_id: str,
    report: dict[str, Any] | None = None,
    *,
    model: str = "small",
) -> dict[str, Any]:
    """Rebuild exec from WhisperX∩faster (high confidence), then screen-flag; persist."""
    from .dual_asr_build import patch_markdown_with_dual
    from .storage import save_summary

    report = report or load_report(video_id) or {}
    md_path = SUMMARY_DIR / f"{video_id}.md"
    if not md_path.exists():
        return {"video_id": video_id, "error": "no markdown", "actions": []}
    old = md_path.read_text(encoding="utf-8")
    # 1) Replace sparse/wrong exec with full dual∪WhisperX table
    rebuilt, dual_meta = patch_markdown_with_dual(video_id, old, model=model)
    md_path.write_text(rebuilt, encoding="utf-8")
    # 2) Screen / timing flags on the rebuilt rows
    plan = build_exec_actions(video_id, report=report, model=model)
    if plan.get("error"):
        return plan

    # Never drop CC quotes or dual/WhisperX rows. faster-only stays dropped unless CC is primary.
    protect = list(dual_meta.get("dual") or []) + list(dual_meta.get("wx_only") or [])
    if dual_meta.get("quote_source") == "cc":
        protect += list(dual_meta.get("faster_only") or []) + list(dual_meta.get("cc_only") or [])
    actions = []
    for a in plan.get("actions") or []:
        ticks = {t.upper() for t in (a.get("tickers") or [])}
        keep = False
        for r in protect:
            if r["ticker"].upper() not in ticks:
                continue
            if abs(parse_ts(a.get("new_t") or a.get("t") or "0") - float(r["start"])) <= 120:
                keep = True
                break
        if keep and a.get("status") == "drop":
            conf = "ok_dual" if any(r.get("confidence") == "dual" and r["ticker"].upper() in ticks for r in protect) else "ok_b"
            a = {**a, "status": conf, "flag": None}
        actions.append(a)
    plan["actions"] = actions
    if dual_meta.get("quote_source") == "cc":
        # CC is the quote; don't snap/drop rows to ASR/faster-only rules
        new = rebuilt
    else:
        new = apply_actions_to_markdown(rebuilt, actions)
    changed = new != old
    plan["dual_count"] = dual_meta.get("dual_count")
    plan["wx_only_count"] = dual_meta.get("wx_only_count")
    plan["faster_only_count"] = dual_meta.get("faster_only_count")
    plan["cc_only_count"] = dual_meta.get("cc_only_count")
    plan["quote_source"] = dual_meta.get("quote_source")
    if dual_meta.get("quote_source") == "cc":
        plan["hint"] = (
            f"YouTube字幕 {len([r for r in (dual_meta.get('rows') or []) if r.get('confidence') != 'gap'])} 行"
            f"（雙ASR核到 {plan.get('dual_count') or 0}"
            f"／WhisperX {plan.get('wx_only_count') or 0}"
            f"／faster {plan.get('faster_only_count') or 0}"
            f"／ASR未核 {plan.get('cc_only_count') or 0}）"
        )
    else:
        plan["hint"] = (
            f"雙ASR確認 {plan.get('dual_count') or 0} 行＋WhisperX獨有 {plan.get('wx_only_count') or 0} 行"
            f"（faster獨有 {plan.get('faster_only_count') or 0} 已唔入主表）"
        )
    if changed:
        save_summary(
            video_id,
            new,
            meta={
                "provider": "reconcile+dual-asr",
                "reconcile": {
                    "dual_count": plan.get("dual_count"),
                    "wx_only_count": plan.get("wx_only_count"),
                    "faster_only_count": plan.get("faster_only_count"),
                    "hint": plan.get("hint"),
                    "asof": int(time.time()),
                },
            },
        )

    # Attach actionable ticker-focused slice onto compare report for UI
    asr = report.get("asr") or {}
    actionable = [
        d
        for d in (asr.get("desync") or [])
        if d.get("kind") in {"ticker_desync", "content_desync", "timing_desync"}
        or (d.get("kind") in {"only_a", "only_b"} and _bucket_has_ticker(d.get("text") or ""))
    ]
    report["actions"] = {
        "exec": plan.get("actions") or [],
        "hint": plan.get("hint"),
        "changed": changed,
        "dual_count": plan.get("dual_count"),
        "wx_only_count": plan.get("wx_only_count"),
        "faster_only_count": plan.get("faster_only_count"),
        "dual_rows": [
            {"t": r["t"], "ticker": r["ticker"], "side": r.get("side")}
            for r in (dual_meta.get("dual") or [])[:40]
        ],
        "keep": plan.get("keep"),
        "drop": plan.get("drop"),
        "timing_snapped": plan.get("timing_snapped"),
    }
    report["asr"] = {
        **asr,
        "desync_actionable": actionable[:40],
        "only_a_tickers": asr.get("only_a_tickers") or [],
        "only_b_tickers": asr.get("only_b_tickers") or [],
    }
    # Prefer ticker-focused overall hint
    hint_bits = [plan.get("hint") or ""]
    report.setdefault("summary", {})["hint"] = "；".join(x for x in hint_bits if x)
    report["summary"]["asr_desync"] = asr.get("desync_count") or 0
    report["summary"]["exec_drop"] = plan.get("drop") or 0
    report["summary"]["exec_single"] = plan.get("single_asr") or 0

    out = DATA_DIR / "asr_compare" / f"{video_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # #region agent log
    try:
        with _DBG.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "ec629f",
                        "hypothesisId": "R",
                        "location": "summary_reconcile.reconcile",
                        "message": "patched",
                        "data": {
                            "video_id": video_id,
                            "changed": changed,
                            "keep": plan.get("keep"),
                            "drop": plan.get("drop"),
                            "single": plan.get("single_asr"),
                            "snapped": plan.get("timing_snapped"),
                            "drops": [
                                {"t": a["t"], "tickers": a["tickers"]}
                                for a in (plan.get("actions") or [])
                                if a["status"] == "drop"
                            ][:20],
                        },
                        "timestamp": int(time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion

    return {**plan, "changed": changed, "report_path": str(out)}


def _bucket_has_ticker(text: str) -> bool:
    low = text.lower()
    for needles in NEEDLES.values():
        if any(n in low for n in needles):
            return True
    return False
