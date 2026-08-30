"""Compare faster-whisper vs WhisperX — find time/text regions that are out of sync."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .asr_fix import fix_asr
from .config import DATA_DIR
from .speech_audit import NEEDLES
from .transcript import format_ts

# Bucket size for sync scan (seconds)
BUCKET = 15.0
# Text similarity below this → mark as content_desync
SIM_THRESH = 0.35
# Start-time drift (sec) for same overlapping bucket content considered timing_desync
DRIFT_THRESH = 4.0


def _norm(text: str) -> str:
    t = fix_asr(text).lower()
    t = re.sub(r"[^a-z0-9\s$]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _tokens(text: str) -> set[str]:
    return {w for w in _norm(text).split() if len(w) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _gaps(snippets: list[dict[str, Any]], min_gap: float = 120.0) -> list[dict[str, Any]]:
    gaps = []
    prev_end = 0.0
    for s in snippets:
        st = float(s.get("start") or 0)
        if st - prev_end >= min_gap:
            gaps.append(
                {
                    "from": format_ts(prev_end),
                    "to": format_ts(st),
                    "minutes": round((st - prev_end) / 60, 1),
                }
            )
        dur = float(s.get("duration") or 0) or 2.0
        prev_end = st + dur
    return gaps


def _ticker_hits(snippets: list[dict[str, Any]]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for s in snippets:
        text = fix_asr(str(s.get("text") or "")).lower()
        t = format_ts(float(s.get("start") or 0))
        for tick, needles in NEEDLES.items():
            if any(n in text for n in needles):
                found.setdefault(tick.upper(), []).append(t)
    return {k: v[:12] for k, v in sorted(found.items())}


def _coverage_seconds(snippets: list[dict[str, Any]]) -> float:
    if not snippets:
        return 0.0
    last = snippets[-1]
    return float(last.get("start") or 0) + float(last.get("duration") or 0)


def summarize_transcript(label: str, snippets: list[dict[str, Any]]) -> dict[str, Any]:
    gaps = _gaps(snippets)
    hits = _ticker_hits(snippets)
    return {
        "label": label,
        "snippet_count": len(snippets),
        "coverage_sec": round(_coverage_seconds(snippets), 1),
        "gap_count": len(gaps),
        "gaps": gaps[:20],
        "ticker_types": len(hits),
        "tickers": hits,
        "has_word_ts": any(s.get("words") for s in snippets[:20]),
    }


def load_snippets(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return list(data.get("snippets") or [])


def _bucket_map(snippets: list[dict[str, Any]], bucket: float = BUCKET) -> dict[int, dict[str, Any]]:
    """Map bucket_index → merged text + mean start."""
    bags: dict[int, list[dict[str, Any]]] = {}
    for s in snippets:
        st = float(s.get("start") or 0)
        idx = int(st // bucket)
        bags.setdefault(idx, []).append(s)
    out: dict[int, dict[str, Any]] = {}
    for idx, rows in bags.items():
        texts = [fix_asr(str(r.get("text") or "")) for r in rows]
        starts = [float(r.get("start") or 0) for r in rows]
        out[idx] = {
            "t": format_ts(idx * bucket),
            "t_end": format_ts((idx + 1) * bucket),
            "start_mean": sum(starts) / len(starts),
            "text": " ".join(texts),
            "n": len(rows),
        }
    return out


def find_desync(
    a: list[dict[str, Any]],
    b: list[dict[str, Any]],
    *,
    label_a: str = "faster-whisper",
    label_b: str = "whisperx",
    bucket: float = BUCKET,
) -> list[dict[str, Any]]:
    """Find buckets where coverage / text / timing disagree."""
    ba = _bucket_map(a, bucket)
    bb = _bucket_map(b, bucket)
    keys = sorted(set(ba) | set(bb))
    issues: list[dict[str, Any]] = []

    for idx in keys:
        left = ba.get(idx)
        right = bb.get(idx)
        t0 = format_ts(idx * bucket)
        t1 = format_ts((idx + 1) * bucket)

        if left and not right:
            issues.append(
                {
                    "kind": "only_a",
                    "t": t0,
                    "t_end": t1,
                    "side": label_a,
                    "text": left["text"][:180],
                    "note": f"只有 {label_a} 有語音／字幕；{label_b} 呢段空白或未對齊",
                }
            )
            continue
        if right and not left:
            issues.append(
                {
                    "kind": "only_b",
                    "t": t0,
                    "t_end": t1,
                    "side": label_b,
                    "text": right["text"][:180],
                    "note": f"只有 {label_b} 有語音／字幕；{label_a} 呢段空白或未對齊",
                }
            )
            continue
        if not left or not right:
            continue

        ta, tb = _tokens(left["text"]), _tokens(right["text"])
        sim = _jaccard(ta, tb)
        drift = abs(left["start_mean"] - right["start_mean"])

        # ticker disagreement in window
        tick_a = {k for k, needles in NEEDLES.items() if any(n in left["text"].lower() for n in needles)}
        tick_b = {k for k, needles in NEEDLES.items() if any(n in right["text"].lower() for n in needles)}
        tick_only_a = sorted(tick_a - tick_b)
        tick_only_b = sorted(tick_b - tick_a)

        if sim < SIM_THRESH:
            issues.append(
                {
                    "kind": "content_desync",
                    "t": t0,
                    "t_end": t1,
                    "similarity": round(sim, 2),
                    "drift_sec": round(drift, 1),
                    label_a: left["text"][:160],
                    label_b: right["text"][:160],
                    "tickers_only_a": tick_only_a,
                    "tickers_only_b": tick_only_b,
                    "note": "同一時段兩邊文字差好遠",
                }
            )
        elif drift >= DRIFT_THRESH and sim >= 0.5:
            issues.append(
                {
                    "kind": "timing_desync",
                    "t": t0,
                    "t_end": t1,
                    "similarity": round(sim, 2),
                    "drift_sec": round(drift, 1),
                    label_a: left["text"][:120],
                    label_b: right["text"][:120],
                    "note": f"內容似但平均時間差 {drift:.1f}s（WhisperX 對齊可能較準）",
                }
            )
        elif tick_only_a or tick_only_b:
            issues.append(
                {
                    "kind": "ticker_desync",
                    "t": t0,
                    "t_end": t1,
                    "similarity": round(sim, 2),
                    "tickers_only_a": tick_only_a,
                    "tickers_only_b": tick_only_b,
                    label_a: left["text"][:120],
                    label_b: right["text"][:120],
                    "note": "同一時段 ticker 命中唔一致",
                }
            )
    return issues


def compare_whisper_vs_whisperx(
    whisper_path: Path,
    whisperx_path: Path,
    *,
    label_a: str = "faster-whisper",
    label_b: str = "whisperx",
) -> dict[str, Any]:
    a = load_snippets(whisper_path)
    b = load_snippets(whisperx_path)
    asum = summarize_transcript(label_a, a)
    bsum = summarize_transcript(label_b, b)
    desync = find_desync(a, b, label_a=label_a, label_b=label_b)
    by_kind: dict[str, int] = {}
    for d in desync:
        by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1

    a_ticks = set(asum["tickers"])
    b_ticks = set(bsum["tickers"])
    return {
        "pair": f"{label_a} vs {label_b}",
        "a": asum,
        "b": bsum,
        "only_a_tickers": sorted(a_ticks - b_ticks),
        "only_b_tickers": sorted(b_ticks - a_ticks),
        "both_tickers": sorted(a_ticks & b_ticks),
        "desync_count": len(desync),
        "desync_by_kind": by_kind,
        "desync": desync[:80],
        "hint": _sync_hint(asum, bsum, by_kind),
    }


def _sync_hint(a: dict[str, Any], b: dict[str, Any], by_kind: dict[str, int]) -> str:
    parts = []
    if by_kind.get("only_a") or by_kind.get("only_b"):
        parts.append("有時段一邊有字一邊空白（覆蓋／VAD 唔 sync）")
    if by_kind.get("timing_desync"):
        parts.append("有 timing drift — 優先信 WhisperX 字級時間戳")
    if by_kind.get("content_desync") or by_kind.get("ticker_desync"):
        parts.append("有內容／ticker 分歧 — 要聽原片或畫面核對")
    if b.get("gap_count", 0) < a.get("gap_count", 0):
        parts.append("WhisperX 大段空白較少")
    elif a.get("gap_count", 0) < b.get("gap_count", 0):
        parts.append("faster-whisper 大段空白較少")
    if not parts:
        return "兩邊大致 sync；可合併用"
    return "；".join(parts)


# Back-compat aliases used by older scripts
def compare_files(path_a: Path, path_b: Path) -> dict[str, Any]:
    return compare_whisper_vs_whisperx(path_a, path_b)


def run_compare(
    video_id: str,
    *,
    whisper_model: str = "large-v3-turbo",
    reuse_audio: bool = True,
    skip_whisper: bool = False,
    skip_whisperx: bool = False,
) -> dict[str, Any]:
    """Download once, run faster-whisper + WhisperX, write sync report."""
    from .asr_whisperx import fetch_via_whisperx
    from .whisper_fallback import AUDIO_DIR, download_audio, fetch_via_whisper

    audio = None
    if reuse_audio:
        for ext in ("mp3", "m4a", "webm", "wav", "opus"):
            p = AUDIO_DIR / f"{video_id}.{ext}"
            if p.exists():
                audio = p
                break
    if audio is None:
        audio = download_audio(video_id)

    w_path = DATA_DIR / "transcripts" / f"{video_id}.whisper-{whisper_model}.json"
    x_path = DATA_DIR / "transcripts" / f"{video_id}.whisperx-{whisper_model}.json"

    if not skip_whisper:
        fetch_via_whisper(video_id, model_size=whisper_model, audio_path=audio)
    if not skip_whisperx:
        fetch_via_whisperx(video_id, model_size=whisper_model, audio_path=audio)

    if not w_path.exists():
        w_path = DATA_DIR / "transcripts" / f"{video_id}.whisper.json"
    if not x_path.exists():
        x_path = DATA_DIR / "transcripts" / f"{video_id}.whisperx.json"
    if not w_path.exists() or not x_path.exists():
        raise FileNotFoundError(f"Need both caches: {w_path} and {x_path}")

    report = compare_whisper_vs_whisperx(w_path, x_path)
    report["video_id"] = video_id
    report["model"] = whisper_model
    report["audio"] = str(audio)
    report["whisper_path"] = str(w_path)
    report["whisperx_path"] = str(x_path)

    out = DATA_DIR / "asr_compare" / f"{video_id}.whisper-vs-whisperx.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(out)
    return report
