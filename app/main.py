from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import DATA_DIR, ROOT, ensure_dirs, settings
from .meta import fetch_video_meta
from .parse_md import parse_summary_markdown
from .storage import get_markdown, list_summaries, load_summary, save_summary
from .summarize import bullets_to_markdown, summarize_chunks_llm
from .transcript import (
    CaptionsDisabledError,
    chunk_transcript,
    extract_video_id,
    fetch_captions,
    format_ts,
    load_transcript,
    save_transcript,
)

ensure_dirs()
PENDING_DIR = DATA_DIR / "pending"
PENDING_DIR.mkdir(parents=True, exist_ok=True)
WHISPER_JOB_DIR = DATA_DIR / "whisper_jobs"
WHISPER_JOB_DIR.mkdir(parents=True, exist_ok=True)
VISION_JOB_DIR = DATA_DIR / "vision_jobs"
VISION_JOB_DIR.mkdir(parents=True, exist_ok=True)
COMPARE_JOB_DIR = DATA_DIR / "asr_compare_jobs"
COMPARE_JOB_DIR.mkdir(parents=True, exist_ok=True)
FRAMES_DIR = DATA_DIR / "frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)
STATIC = ROOT / "static"

# #region agent log
_DBG_LOG = ROOT / "debug-ec629f.log"


def _dbg(hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    import time

    rec = {
        "sessionId": "ec629f",
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with _DBG_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _dbg_align_axti_twlo(video_id: str, packed: dict[str, Any], source: str) -> None:
    """Log why AXTI/TWLO may share 09:49 vs live at 10:10."""
    tr = load_transcript(video_id) or {}
    hits = []
    for s in tr.get("snippets") or []:
        text = str(s.get("text") or "")
        low = text.lower()
        if any(k in low for k in ("axti", "twilio", "twlo", "rising nine", "rising 9")):
            start = float(s.get("start") or 0)
            hits.append(
                {
                    "t": format_ts(start),
                    "start": start,
                    "end": start + float(s.get("duration") or 0),
                    "text": text[:160],
                }
            )
    exec_rows = [
        {"t": x.get("t"), "text": (x.get("text") or "")[:180]}
        for x in (packed.get("exec_zh") or [])
        if "TWLO" in (x.get("text") or "")
        or "Twilio" in (x.get("text") or "")
        or (x.get("t") == "09:49")
        or (x.get("t") == "10:10")
    ]
    zh_rows = [
        {"t": x.get("t"), "text": (x.get("text") or "")[:180]}
        for x in (packed.get("bullets_zh") or [])
        if x.get("t") in {"09:49", "10:10", "10:02"} or "TWLO" in (x.get("text") or "")
    ]
    labels_path = DATA_DIR / "frames" / video_id / "labels.json"
    label_hits = {}
    if labels_path.exists():
        by = (json.loads(labels_path.read_text(encoding="utf-8")).get("by_t") or {})
        for key in ("09:49", "09:55", "10:10"):
            if key in by:
                label_hits[key] = by[key]
    times = [h["start"] for h in hits]
    _dbg(
        "A",
        "main.py:_dbg_align_axti_twlo",
        "speech_vs_summary_stamps",
        {
            "source": source,
            "video_id": video_id,
            "speech_hits": hits,
            "exec_09_or_twlo": exec_rows,
            "zh_09_or_twlo": zh_rows,
            "labels_screen": label_hits,
            "has_exec_10_10": any(x.get("t") == "10:10" for x in packed.get("exec_zh") or []),
            "has_zh_10_10": any(x.get("t") == "10:10" for x in packed.get("bullets_zh") or []),
            "has_exec_09_55": any(x.get("t") == "09:55" for x in packed.get("exec_zh") or []),
            "chunk_window_sec": settings.chunk_seconds,
            "hypothesisA_frame_keyed": True,
            "min_hit": min(times) if times else None,
            "max_hit": max(times) if times else None,
        },
    )


# #endregion

app = FastAPI(title="Local TubeonAI", version="0.2.1")


class AnalyzeRequest(BaseModel):
    url: str
    provider: str | None = Field(
        default=None,
        description="cursor-agent | offline | ollama | openai",
    )
    title: str | None = None
    force: bool = False


class AnalyzeResponse(BaseModel):
    video_id: str
    title: str
    provider: str
    bullet_count: int
    bullets: list[dict[str, Any]]
    bullets_en: list[dict[str, Any]] = []
    bullets_zh: list[dict[str, Any]] = []
    digest_zh: list[dict[str, Any]] = []
    exec_zh: list[dict[str, Any]] = []
    exec_unverified: list[dict[str, Any]] = []
    markdown: str
    url: str
    status: str = "ok"
    hint: str | None = None
    speech_audit: dict[str, Any] | None = None
    verify: dict[str, Any] | None = None


def _asr_compare_status(video_id: str) -> dict[str, Any] | None:
    import time

    path = COMPARE_JOB_DIR / f"{video_id}.json"
    if not path.exists():
        return None
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    mtime = path.stat().st_mtime
    hb = st.get("heartbeat_ts")
    if hb is None:
        st["heartbeat_ts"] = int(mtime)
        hb = mtime
    st["heartbeat_age_sec"] = max(0, int(time.time() - float(hb)))
    st["status_file_age_sec"] = max(0, int(time.time() - mtime))
    return st


def _whisperx_ready() -> bool:
    import importlib.util

    return importlib.util.find_spec("whisperx") is not None


def _has_whisperx_transcript(video_id: str) -> bool:
    tr = DATA_DIR / "transcripts"
    return any(tr.glob(f"{video_id}.whisperx*.json"))


def _start_asr_compare_job(video_id: str, *, force: bool = False) -> dict[str, Any]:
    st = _asr_compare_status(video_id)
    if st and st.get("status") in {"running", "starting"}:
        return st
    # Stale "done" after user installs WhisperX — re-run until .whisperx*.json exists
    needs_whisperx = _whisperx_ready() and not _has_whisperx_transcript(video_id)
    if st and st.get("status") == "done" and not force and not needs_whisperx:
        from .triple_check import load_report

        if load_report(video_id):
            return st
    if needs_whisperx:
        force = True
    job_script = ROOT / "scripts" / "asr_compare_job.py"
    COMPARE_JOB_DIR.mkdir(parents=True, exist_ok=True)
    status_path = COMPARE_JOB_DIR / f"{video_id}.json"
    status_path.write_text(
        json.dumps(
            {"video_id": video_id, "status": "starting", "step": "spawn"},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    log_path = COMPARE_JOB_DIR / f"{video_id}.log"
    log_f = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
    subprocess.Popen(
        [sys.executable, str(job_script), video_id],
        cwd=str(ROOT),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return {"status": "starting", "video_id": video_id}


def _kick_verify_jobs(video_id: str, *, force_compare: bool = False) -> dict[str, Any]:
    """After Analyze: auto screen frames + ASR/WhisperX/screen compare."""
    vision = _start_vision_job(video_id)
    compare = _start_asr_compare_job(video_id, force=force_compare)
    return {"vision": vision, "compare": compare}


def _attach_speech_audit(packed: AnalyzeResponse) -> AnalyzeResponse:
    from .speech_audit import TICKER_FROM_EXEC, audit_summary

    if not packed.markdown:
        return packed
    report = audit_summary(packed.video_id, packed.markdown)
    packed.speech_audit = {
        "suspect_count": report.get("suspect_count") or 0,
        "ok_count": report.get("ok_count") or 0,
        "suspects": report.get("suspects") or [],
    }
    n = packed.speech_audit["suspect_count"]
    keys = {(s["t"], str(s["ticker"]).upper()) for s in (report.get("suspects") or [])}
    verified: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []
    for row in packed.exec_zh or []:
        t = str(row.get("t") or "")
        text = str(row.get("text") or "")
        m = TICKER_FROM_EXEC.search(text)
        if not m:
            verified.append(row)
            continue
        tick = re.sub(r"（.*?）|\(.*?\)", "", m.group(1)).strip().upper()
        tick = tick.split("/")[0].split("／")[0].strip()
        if (t, tick) in keys:
            unverified.append(row)
        else:
            verified.append(row)
    packed.exec_zh = verified
    packed.exec_unverified = unverified
    if n:
        warn = (
            f"語音核對：{n} 行 ticker 附近語音未見過，"
            "已從主表拎走（唔使一條條自己睇）；詳情喺左邊核對欄。"
        )
        packed.hint = f"{packed.hint} {warn}".strip() if packed.hint else warn
    # #region agent log
    _dbg(
        "D",
        "main.py:_attach_speech_audit",
        "gate_filter",
        {
            "video_id": packed.video_id,
            "suspect_count": n,
            "ok_count": packed.speech_audit["ok_count"],
            "exec_kept": len(verified),
            "exec_hidden": len(unverified),
            "hidden_tickers": [
                {"t": r.get("t"), "text": (r.get("text") or "")[:80]} for r in unverified[:20]
            ],
        },
    )
    # #endregion
    return packed


def _attach_verify(packed: AnalyzeResponse, *, kick: bool = True, force_compare: bool = False) -> AnalyzeResponse:
    from .triple_check import load_report

    if kick and packed.video_id and packed.status in {"ok", "cached"}:
        jobs = _kick_verify_jobs(packed.video_id, force_compare=force_compare)
    else:
        jobs = {
            "vision": _vision_status(packed.video_id) or {},
            "compare": _asr_compare_status(packed.video_id) or {},
        }
    report = load_report(packed.video_id) if packed.video_id else None
    compare_job = _asr_compare_status(packed.video_id) or jobs.get("compare") or {}
    packed.verify = {
        "jobs": jobs,
        "report": report,
        "compare_job": compare_job,
        "vision_job": _vision_status(packed.video_id),
    }
    hint_bits = []
    if packed.hint:
        hint_bits.append(packed.hint)
    hint_bits.append("已自動開畫面核對＋ASR/畫面對比（Whisper↔WhisperX↔畫面）。")
    cj = (compare_job or {}).get("status") or ""
    if cj in {"running", "starting"}:
        hint_bits.append(f"三重對比跑緊：{compare_job.get('step') or cj}（WhisperX 轉寫要啲時間，唔係未裝）。")
    elif report and report.get("summary"):
        hint_bits.append(str(report["summary"].get("hint") or ""))
    packed.hint = " ".join(x for x in hint_bits if x).strip()
    # #region agent log
    _dbg(
        "A",
        "main.py:_attach_verify",
        "verify_attach",
        {
            "video_id": packed.video_id,
            "compare_status": cj,
            "compare_step": (compare_job or {}).get("step"),
            "has_report": bool(report),
            "report_hint": ((report or {}).get("summary") or {}).get("hint"),
            "used_running_hint": cj in {"running", "starting"},
        },
    )
    # #endregion
    return packed


def _pack_from_md(video_id: str, md: str, provider: str, title: str | None = None) -> AnalyzeResponse:
    parsed = parse_summary_markdown(md)
    bullets_zh = parsed.get("bullets_zh") or []
    bullets_en = parsed.get("bullets_en") or []
    bullets = bullets_zh or bullets_en
    packed = AnalyzeResponse(
        video_id=video_id,
        title=parsed.get("title") or title or video_id,
        provider=provider,
        bullet_count=len(bullets),
        bullets=bullets,
        bullets_en=bullets_en,
        bullets_zh=bullets_zh,
        digest_zh=parsed.get("digest_zh") or parsed.get("exec_zh") or [],
        exec_zh=parsed.get("digest_zh") or parsed.get("exec_zh") or [],
        markdown=md,
        url=f"https://www.youtube.com/watch?v={video_id}",
        status="ok",
    )
    # #region agent log
    try:
        import time as _time

        from .config import ROOT as _ROOT

        with (_ROOT / "debug-ec629f.log").open("a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "ec629f",
                        "hypothesisId": "A",
                        "location": "main.py:_pack_from_md",
                        "message": "api_pack_counts",
                        "data": {
                            "video_id": video_id,
                            "exec_n": len(packed.exec_zh),
                            "digest_n": len(packed.digest_zh),
                            "zh_n": len(packed.bullets_zh),
                            "en_n": len(packed.bullets_en),
                            "exec_pipe": sum(1 for x in packed.exec_zh if "|" in str(x.get("text") or "")),
                            "zh_pipe": sum(1 for x in packed.bullets_zh if "|" in str(x.get("text") or "")),
                            "md_digest": "真正摘要" in (md or ""),
                            "md_content": "時間軸內容" in (md or ""),
                            "md_old_exec": "重點摘要" in (md or ""),
                        },
                        "timestamp": int(_time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion
    return packed


def _whisper_status(video_id: str) -> dict[str, Any] | None:
    path = WHISPER_JOB_DIR / f"{video_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _start_whisper_job(video_id: str) -> dict[str, Any]:
    st = _whisper_status(video_id)
    if st and st.get("status") == "running":
        return st
    if load_transcript(video_id) and (not st or st.get("status") == "done"):
        return {"status": "done", "video_id": video_id, "note": "transcript already cached"}

    job_script = ROOT / "scripts" / "whisper_job.py"
    status_path = WHISPER_JOB_DIR / f"{video_id}.json"
    status_path.write_text(
        json.dumps({"video_id": video_id, "status": "starting", "step": "spawn"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log_path = WHISPER_JOB_DIR / f"{video_id}.log"
    log_f = open(log_path, "a", encoding="utf-8")  # noqa: SIM115 — kept open for subprocess lifetime
    subprocess.Popen(
        [sys.executable, str(job_script), video_id],
        cwd=str(ROOT),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return {"status": "starting", "video_id": video_id}


def _vision_status(video_id: str) -> dict[str, Any] | None:
    path = VISION_JOB_DIR / f"{video_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _start_vision_job(video_id: str) -> dict[str, Any]:
    st = _vision_status(video_id)
    if st and st.get("status") in {"running", "starting"}:
        return st
    job_script = ROOT / "scripts" / "vision_job.py"
    status_path = VISION_JOB_DIR / f"{video_id}.json"
    status_path.write_text(
        json.dumps({"video_id": video_id, "status": "starting", "step": "spawn"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log_path = VISION_JOB_DIR / f"{video_id}.log"
    log_f = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
    subprocess.Popen(
        [sys.executable, str(job_script), video_id],
        cwd=str(ROOT),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return {"status": "starting", "video_id": video_id}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "llm_provider": settings.llm_provider,
        "ollama_model": settings.ollama_model,
        "providers": ["cursor-agent", "offline", "ollama", "openai"],
        "asr_provider": settings.asr_provider,
        "whisper_model": settings.whisper_model,
        "deepgram_model": settings.deepgram_model,
    }


@app.get("/api/meta")
def api_meta(url: str) -> dict[str, Any]:
    try:
        video_id = extract_video_id(url)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return fetch_video_meta(video_id)


@app.get("/api/whisper/{video_id}")
def api_whisper_status(video_id: str) -> dict[str, Any]:
    st = _whisper_status(video_id) or {}
    cached = load_transcript(video_id)
    return {
        "video_id": video_id,
        "job": st,
        "transcript_ready": bool(cached),
        "source": (cached or {}).get("source"),
        "snippet_count": len((cached or {}).get("snippets") or []),
    }


@app.post("/api/vision/{video_id}")
def api_vision_start(video_id: str) -> dict[str, Any]:
    job = _start_vision_job(video_id)
    return {"video_id": video_id, "job": job}


@app.get("/api/vision/{video_id}")
def api_vision_status(video_id: str) -> dict[str, Any]:
    from .video_check import load_report

    st = _vision_status(video_id) or {}
    report = load_report(video_id)
    items = (report or {}).get("items") or []
    by_t = {str(x.get("t")): x for x in items if x.get("t")}
    return {
        "video_id": video_id,
        "job": st,
        "ready": bool(report),
        "ocr_engine": (report or {}).get("ocr_engine"),
        "frame_count": (report or {}).get("frame_count") or len(items),
        "mismatch_count": (report or {}).get("mismatch_count"),
        "by_t": by_t,
        "items": items,
    }


@app.get("/api/compare/{video_id}")
def api_compare_status(video_id: str) -> dict[str, Any]:
    from .triple_check import load_report

    st = _asr_compare_status(video_id) or {}
    report = load_report(video_id)
    job_st = st.get("status") or ""
    # ready only when job finished (old report must not stop polling mid-run)
    ready = job_st == "done" or (bool(report) and job_st not in {"running", "starting"})
    # #region agent log
    _dbg(
        "B",
        "main.py:api_compare_status",
        "compare_poll",
        {
            "video_id": video_id,
            "job_status": job_st,
            "job_step": st.get("step"),
            "progress_pct": st.get("progress_pct"),
            "elapsed_sec": st.get("elapsed_sec"),
            "eta_sec": st.get("eta_sec"),
            "heartbeat_age_sec": st.get("heartbeat_age_sec"),
            "status_file_age_sec": st.get("status_file_age_sec"),
            "has_report": bool(report),
            "ready": ready,
            "whisperx_error": (st.get("whisperx_error") or "")[:160],
        },
    )
    # #endregion
    return {
        "video_id": video_id,
        "job": st,
        "ready": ready,
        "report": report,
        "summary": (report or {}).get("summary"),
    }


@app.post("/api/compare/{video_id}")
def api_compare_start(video_id: str) -> dict[str, Any]:
    job = _start_asr_compare_job(video_id, force=True)
    return {"video_id": video_id, "job": job}


@app.post("/api/reconcile/{video_id}")
def api_reconcile(video_id: str) -> dict[str, Any]:
    """Re-verify exec vs dual ASR and rewrite summary (no Chat)."""
    from .summary_reconcile import reconcile_summary_from_compare
    from .triple_check import load_report

    report = load_report(video_id)
    patch = reconcile_summary_from_compare(video_id, report)
    return {"video_id": video_id, "patch": patch, "job": _asr_compare_status(video_id)}


@app.get("/api/summaries")
def api_list_summaries() -> list[dict[str, Any]]:
    return list_summaries()


@app.get("/api/summaries/{video_id}")
def api_get_summary(video_id: str) -> dict[str, Any]:
    data = load_summary(video_id)
    md = get_markdown(video_id)
    if not data and not md:
        raise HTTPException(404, "Summary not found")
    if md:
        packed = _attach_verify(
            _attach_speech_audit(
                _pack_from_md(video_id, md, provider=(data or {}).get("provider") or "cached")
            ),
            kick=False,
        )
        out = packed.model_dump()
        if data:
            out["provider"] = data.get("provider") or out["provider"]
            if data.get("speech_audit") and not out.get("speech_audit"):
                out["speech_audit"] = data["speech_audit"]
        # #region agent log
        _dbg_align_axti_twlo(video_id, out, "get_summary")
        # #endregion
        return out
    data["url"] = f"https://www.youtube.com/watch?v={video_id}"
    return data


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def api_analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    try:
        video_id = extract_video_id(req.url)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    provider = (req.provider or settings.llm_provider).lower()
    meta = fetch_video_meta(video_id)
    title = (req.title or "").strip() or meta.get("title") or video_id
    url = meta.get("url") or f"https://www.youtube.com/watch?v={video_id}"

    existing_md = get_markdown(video_id)
    # #region agent log
    _dbg(
        "A",
        "main.py:api_analyze",
        "analyze_entry",
        {
            "video_id": video_id,
            "provider": provider,
            "force": bool(req.force),
            "has_existing_md": bool(existing_md),
            "will_return_cache": bool(
                existing_md and not req.force and provider in {"offline", "cursor-agent", "cached"}
            ),
        },
    )
    # #endregion
    if existing_md and not req.force and provider in {"offline", "cursor-agent", "cached"}:
        parsed = parse_summary_markdown(existing_md)
        if parsed.get("bullets_en") or parsed.get("bullets_zh"):
            packed = _pack_from_md(video_id, existing_md, provider="cached", title=title)
            packed.title = parsed.get("title") or title
            packed.status = "cached"
            packed.hint = (
                f"已顯示磁碟上最新摘要（{video_id}），Analyze 冇重跑 Whisper／Agent。"
                "要重新轉寫先勾 Force。"
            )
            # #region agent log
            _dbg_align_axti_twlo(video_id, packed.model_dump(), "analyze_cached")
            # #endregion
            return _attach_verify(_attach_speech_audit(packed), kick=True)

    cached = load_transcript(video_id)
    source = "captions"
    if cached and not req.force:
        snippets = cached["snippets"]
        chunks = cached.get("chunks") or chunk_transcript(snippets, settings.chunk_seconds)
        source = cached.get("source") or "captions"
    else:
        try:
            snippets = fetch_captions(video_id)
            chunks = chunk_transcript(snippets, settings.chunk_seconds)
            save_transcript(video_id, snippets, chunks, source="captions")
        except Exception as e:
            msg = str(e)
            captions_off = (
                "TranscriptsDisabled" in type(e).__name__
                or "Subtitles are disabled" in msg
                or "Could not retrieve a transcript" in msg
                or isinstance(e, CaptionsDisabledError)
            )
            if not captions_off:
                raise HTTPException(502, f"Failed to fetch transcript: {e}") from e

            # Caption-disabled -> background Whisper (do not block HTTP for hours)
            job = _start_whisper_job(video_id)
            st = job.get("status") or "starting"
            hint = (
                f"「{title}」關咗 YouTube 字幕（連 auto-caption 都冇），"
                f"已開本地 Whisper 轉寫（model={settings.whisper_model}，狀態：{st}）。"
                "約 3 小時片喺 CPU 可能要好耐。"
                f"完成後會自動再試，或你再撳 Analyze／Chat 講：請總結 {video_id}。"
                f"進度：/api/whisper/{video_id}"
            )
            return AnalyzeResponse(
                video_id=video_id,
                title=title,
                provider=provider,
                bullet_count=0,
                bullets=[],
                markdown="",
                url=url,
                status="whisper_running",
                hint=hint,
            )

    if provider == "cursor-agent":
        # One-click: build speech-grounded summary here — no Chat 「請總結」 step.
        from .auto_summary import build_and_save_summary

        build_and_save_summary(
            video_id,
            title=title,
            source=source,
            snippets=snippets,
            chunks=chunks,
        )
        pending_path = PENDING_DIR / f"{video_id}.json"
        if pending_path.exists():
            pending_path.unlink()
        md2 = get_markdown(video_id) or ""
        packed = _attach_speech_audit(
            _pack_from_md(video_id, md2, provider="auto-summary", title=title)
        )
        packed.status = "ok"
        packed.hint = (
            f"已自動總結（{len(chunks)} chunks，來源：{source}）；"
            "語音閘已跑——未核實 ticker 會從主表拎走。"
        )
        # #region agent log
        _dbg(
            "E",
            "main.py:api_analyze",
            "auto_summary_done",
            {
                "video_id": video_id,
                "chunk_count": len(chunks),
                "source": source,
                "suspect_count": (packed.speech_audit or {}).get("suspect_count"),
                "ok_count": (packed.speech_audit or {}).get("ok_count"),
            },
        )
        # #endregion
        return _attach_verify(packed, kick=True, force_compare=bool(req.force))

    try:
        bullets = await summarize_chunks_llm(chunks, provider=provider)
    except Exception as e:
        raise HTTPException(502, f"Summarizer failed ({provider}): {e}") from e

    md = bullets_to_markdown(
        video_id=video_id,
        title=title,
        bullets=bullets,
        source=f"local-{provider}",
    )
    md = md.replace("## Timestamped notes", "## Timestamped notes (EN)", 1)
    save_summary(
        video_id,
        md,
        meta={"title": title, "provider": provider, "chunk_count": len(chunks), "source": source},
    )
    # Re-read — save_summary may have appended ⚠語音未核實
    md2 = get_markdown(video_id) or md
    return _attach_verify(
        _attach_speech_audit(_pack_from_md(video_id, md2, provider=provider, title=title)),
        kick=True,
        force_compare=bool(req.force),
    )


@app.middleware("http")
async def _no_store_ui(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static") or path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index() -> FileResponse:
    return FileResponse(
        STATIC / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


app.mount("/frames", StaticFiles(directory=str(FRAMES_DIR)), name="frames")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
