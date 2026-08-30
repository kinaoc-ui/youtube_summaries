"""Speech (faster-whisper) vs WhisperX vs screen labels — unified compare report."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .asr_compare import compare_whisper_vs_whisperx
from .config import DATA_DIR, SUMMARY_DIR
from .parse_md import parse_summary_markdown
from .speech_audit import TICKER_FROM_EXEC, nearest_speech_time, speech_hit, window_text
from .transcript import format_ts, load_transcript
from .video_check import parse_ts

LABELS = DATA_DIR / "frames"
COMPARE_DIR = DATA_DIR / "asr_compare"

SKIP = {"大方向", "買力", "主題", "執行紀律", "收結感覺", "字幕缺口", "Software", "Cyber", "Semis"}


def _load_labels(video_id: str) -> dict[str, Any]:
    path = LABELS / video_id / "labels.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("by_t") or {}
    except json.JSONDecodeError:
        return {}


def _load_vision_by_t(video_id: str) -> dict[str, Any]:
    from .video_check import load_report

    report = load_report(video_id) or {}
    out: dict[str, Any] = {}
    for it in report.get("items") or []:
        t = str(it.get("t") or "")
        if t:
            out[t] = it
    return out


def _find_transcript_pair(video_id: str, model: str) -> tuple[Path | None, Path | None]:
    w_candidates = [
        DATA_DIR / "transcripts" / f"{video_id}.whisper-{model}.json",
        DATA_DIR / "transcripts" / f"{video_id}.whisper.json",
    ]
    x_candidates = [
        DATA_DIR / "transcripts" / f"{video_id}.whisperx-{model}.json",
        DATA_DIR / "transcripts" / f"{video_id}.whisperx.json",
    ]
    w = next((p for p in w_candidates if p.exists()), None)
    x = next((p for p in x_candidates if p.exists()), None)
    return w, x


def _exec_tickers(video_id: str) -> list[dict[str, str]]:
    md_path = SUMMARY_DIR / f"{video_id}.md"
    if not md_path.exists():
        return []
    parsed = parse_summary_markdown(md_path.read_text(encoding="utf-8"))
    rows = []
    for row in parsed.get("exec_zh") or []:
        t = str(row.get("t") or "")
        text = str(row.get("text") or "")
        m = TICKER_FROM_EXEC.search(text)
        if not m:
            continue
        raw = m.group(1).strip()
        if raw in SKIP:
            continue
        tick = re.sub(r"（.*?）|\(.*?\)", "", raw).strip()
        tick = tick.split("/")[0].split("／")[0].strip().upper()
        if tick:
            rows.append({"t": t, "ticker": tick, "text": text[:160]})
    return rows


def compare_speech_vs_screen(video_id: str) -> dict[str, Any]:
    """At each exec timestamp: claimed ticker vs screen label vs speech window."""
    tr = load_transcript(video_id) or {}
    snippets = tr.get("snippets") or []
    labels = _load_labels(video_id)
    vision = _load_vision_by_t(video_id)
    mismatches: list[dict[str, Any]] = []
    ok_rows: list[dict[str, Any]] = []

    for row in _exec_tickers(video_id):
        t = row["t"]
        tick = row["ticker"]
        center = parse_ts(t) if t else 0.0
        spoken = nearest_speech_time(snippets, tick, prefer_center=center)
        # Only count as speech support if spoken near this stamp (long Whisper chunks lie)
        hit = bool(spoken is not None and abs(spoken - center) <= 20.0)
        blob = window_text(snippets, spoken if hit and spoken is not None else center, before=40, after=40)

        lab = labels.get(t) or {}
        screen = (lab.get("symbol") or "").upper() or None
        vis = vision.get(t) or {}
        ocr = vis.get("ocr_tickers") or vis.get("tickers") or []
        if not screen and ocr:
            screen = str(ocr[0]).upper()

        screen_ok = bool(
            screen and (screen == tick or tick.startswith(screen) or screen.startswith(tick))
        )
        speech_matches_screen = bool(screen and speech_hit(screen, blob))

        entry: dict[str, Any] = {
            "t": t,
            "claimed": tick,
            "screen": screen,
            "speech_hit_claimed": hit,
            "speech_hit_screen": speech_matches_screen,
            "speech_at": format_ts(spoken) if spoken is not None else None,
            "screen_ok": screen_ok,
            "text": row["text"],
        }

        if screen and not screen_ok:
            if spoken is not None and abs(spoken - center) > 45.0:
                entry["kind"] = "timestamp_early"
                entry["note"] = (
                    f"語音先喺 {format_ts(spoken)} 先講到 {tick}；"
                    f"而家標 {t} 太早（畫面 {screen}）— 應對齊時間戳"
                )
            elif hit and not speech_matches_screen:
                entry["kind"] = "screen_diff_speech_ok"
                entry["note"] = f"語音撐 {tick}；畫面係 {screen}（應兩邊都寫）"
            elif not hit:
                entry["kind"] = "wrong_or_unverified"
                entry["note"] = f"語音未見 {tick}；畫面 {screen}"
            else:
                entry["kind"] = "screen_diff"
                entry["note"] = f"聲稱 {tick} vs 畫面 {screen}"
            mismatches.append(entry)
        elif not hit and not screen_ok:
            entry["kind"] = "unverified"
            entry["note"] = f"語音＋畫面都未核實 {tick}"
            mismatches.append(entry)
        else:
            ok_rows.append(entry)

    return {
        "mismatch_count": len(mismatches),
        "ok_count": len(ok_rows),
        "mismatches": mismatches[:60],
        "has_labels": bool(labels),
        "has_vision": bool(vision),
        "label_times": len(labels),
        "vision_times": len(vision),
    }


def build_full_report(video_id: str, *, model: str = "large-v3-turbo") -> dict[str, Any]:
    """Merge whisper↔whisperx desync + speech↔screen mismatches."""
    w_path, x_path = _find_transcript_pair(video_id, model)
    asr_part: dict[str, Any] | None = None
    if w_path and x_path:
        asr_part = compare_whisper_vs_whisperx(w_path, x_path)
    elif w_path and not x_path:
        asr_part = {
            "pair": "faster-whisper vs whisperx",
            "whisperx_status": "pending",
            "hint": "WhisperX 套件可能已裝，但未產出轉寫檔；compare job 會補跑",
            "desync_count": 0,
            "desync": [],
            "desync_by_kind": {},
        }
    else:
        # Use main transcript as speech side only
        asr_part = {
            "pair": "faster-whisper vs whisperx",
            "whisperx_status": "pending",
            "faster_whisper_status": "using_main_transcript",
            "hint": "用主字幕做語音；WhisperX 轉寫未完成",
            "desync_count": 0,
            "desync": [],
            "desync_by_kind": {},
        }

    screen_part = compare_speech_vs_screen(video_id)

    # Cross: ASR desync buckets that also mention tickers differing from screen
    report = {
        "video_id": video_id,
        "model": model,
        "asr": asr_part,
        "screen": screen_part,
        "summary": {
            "asr_desync": (asr_part or {}).get("desync_count") or 0,
            "screen_mismatch": screen_part.get("mismatch_count") or 0,
            "hint": _overall_hint(asr_part, screen_part),
        },
    }
    COMPARE_DIR.mkdir(parents=True, exist_ok=True)
    out = COMPARE_DIR / f"{video_id}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(out)
    return report


def _overall_hint(asr: dict[str, Any] | None, screen: dict[str, Any]) -> str:
    parts = []
    n_scr = screen.get("mismatch_count") or 0
    by_kind = (asr or {}).get("desync_by_kind") or {}
    n_tick = by_kind.get("ticker_desync") or 0
    n_content = by_kind.get("content_desync") or 0
    if n_tick or n_content:
        parts.append(f"ticker/內容分歧 {n_tick + n_content}（會跟住改摘要）")
    if n_scr:
        parts.append(f"畫面／語音分歧 {n_scr} 行")
    if not screen.get("has_labels") and not screen.get("has_vision"):
        parts.append("未有畫面 labels——已／會開畫面核對")
    wx = (asr or {}).get("whisperx_status")
    if wx == "missing":
        parts.append("WhisperX 未安裝（pip install whisperx）")
    elif wx == "pending":
        parts.append("WhisperX 已可裝／裝咗但轉寫未完成（背景 job 跑緊或等重跑）")
    if not parts:
        return "語音＋畫面大致一致；對比後會自動核實摘要"
    return "；".join(parts)


def load_report(video_id: str) -> dict[str, Any] | None:
    path = COMPARE_DIR / f"{video_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
