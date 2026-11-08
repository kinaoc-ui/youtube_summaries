# -*- coding: utf-8 -*-
"""Check Martin Luk streams for new VODs and run the local analyze pipeline.

Usage:
  python scripts/martin_daily.py
  python scripts/martin_daily.py --playlist-end 12
  python scripts/martin_daily.py --bootstrap   # seed known ids, do not analyze
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.auto_summary import build_and_save_summary  # noqa: E402
from app.config import DATA_DIR, SUMMARY_DIR, OUTPUT_DIR, ensure_dirs, settings  # noqa: E402
from app.meta import fetch_video_meta  # noqa: E402
from app.transcript import (  # noqa: E402
    CaptionsDisabledError,
    chunk_transcript,
    fetch_captions,
    load_transcript,
    save_transcript,
)

STREAMS_URL = "https://www.youtube.com/@martinlukkt/streams"
STATE_PATH = DATA_DIR / "martin_state.json"
WHISPER_JOB_DIR = DATA_DIR / "whisper_jobs"
COMPARE_JOB_DIR = DATA_DIR / "asr_compare_jobs"
WATCHLIST_JOB_DIR = DATA_DIR / "watchlist_jobs"

# Set False via --skip-watchlist so analyze_video / pending finish skip OCR jobs.
_WATCHLIST_ENABLED = True


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"known_ids": [], "pending_whisper": [], "last_check": None}


def _save_state(state: dict[str, Any]) -> None:
    ensure_dirs()
    state["last_check"] = int(time.time())
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def list_recent_streams(playlist_end: int = 10) -> list[dict[str, str]]:
    """Return newest Martin Luk livestream VODs via yt-dlp."""
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--playlist-end",
        str(playlist_end),
        "--print",
        "%(id)s\t%(title)s\t%(upload_date)s",
        STREAMS_URL,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {(r.stderr or r.stdout or '')[:500]}")
    out: list[dict[str, str]] = []
    for line in (r.stdout or "").splitlines():
        parts = line.strip().split("\t")
        if len(parts) < 2:
            continue
        vid, title = parts[0].strip(), parts[1].strip()
        if not vid or len(vid) != 11:
            continue
        out.append(
            {
                "id": vid,
                "title": title,
                "upload_date": parts[2].strip() if len(parts) > 2 else "",
            }
        )
    return out


def _summary_exists(video_id: str) -> bool:
    return (SUMMARY_DIR / f"{video_id}.md").exists()


def _win_job_flags() -> int:
    """Survive Task Scheduler killing children when the parent .bat exits."""
    if sys.platform != "win32":
        return 0
    return (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
    )


def _start_job(
    script_name: str,
    video_id: str,
    status_dir: Path,
    *,
    extra_args: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    status_dir.mkdir(parents=True, exist_ok=True)
    status_path = status_dir / f"{video_id}.json"
    payload = {
        "video_id": video_id,
        "status": "starting",
        "step": "spawn",
        "source": "martin_daily",
    }
    if meta:
        payload.update(meta)
    status_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log_path = status_dir / f"{video_id}.log"
    log_f = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
    cmd = [sys.executable, str(ROOT / "scripts" / script_name), video_id]
    if extra_args:
        cmd.extend(extra_args)
    subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        close_fds=False,
        creationflags=_win_job_flags(),
    )


def _wait_for_whisper_jobs(
    video_ids: list[str],
    *,
    timeout_sec: int = 5400,
    poll_sec: int = 20,
) -> None:
    """Block until spawned Whisper jobs finish so git push includes the summary."""
    remaining = [vid for vid in video_ids if vid]
    if not remaining:
        return
    deadline = time.time() + timeout_sec
    _log(f"waiting up to {timeout_sec}s for {len(remaining)} whisper job(s)")
    while remaining and time.time() < deadline:
        nxt: list[str] = []
        for vid in remaining:
            job_path = WHISPER_JOB_DIR / f"{vid}.json"
            job: dict[str, Any] = {}
            if job_path.exists():
                try:
                    job = json.loads(job_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    job = {}
            status = str(job.get("status") or "")
            if status == "done":
                _log(f"  whisper {vid}: done")
                continue
            if status == "error":
                _log(f"  whisper {vid}: error — {job.get('error') or 'see log'}")
                continue
            nxt.append(vid)
        remaining = nxt
        if remaining:
            time.sleep(poll_sec)
    if remaining:
        _log(f"whisper still running after {timeout_sec}s: {', '.join(remaining)}")


def _kick_asr_compare(video_id: str) -> None:
    st_path = COMPARE_JOB_DIR / f"{video_id}.json"
    if st_path.exists():
        try:
            st = json.loads(st_path.read_text(encoding="utf-8"))
            if st.get("status") in {"running", "starting"}:
                _log(f"  asr_compare already {st.get('status')}: {video_id}")
                return
        except json.JSONDecodeError:
            pass
    _log(f"  kick asr_compare: {video_id}")
    _start_job("asr_compare_job.py", video_id, COMPARE_JOB_DIR)


def _kick_watchlist(
    video_id: str,
    *,
    force: bool = False,
    upload_date: str | None = None,
) -> None:
    """OCR/vision E_Main sidebar → TradingView Upload .txt (dated list name)."""
    if not _WATCHLIST_ENABLED and not force:
        return
    st_path = WATCHLIST_JOB_DIR / f"{video_id}.json"
    if not force and st_path.exists():
        try:
            st = json.loads(st_path.read_text(encoding="utf-8"))
            status = st.get("status")
            # Stale running/starting (crash / interrupted) — allow retry after 20 min
            if status in {"running", "starting"}:
                age = time.time() - st_path.stat().st_mtime
                if age < 20 * 60:
                    _log(f"  watchlist already {status}: {video_id}")
                    return
                _log(f"  watchlist stale {status} ({int(age)}s) — retry: {video_id}")
            elif status == "done":
                _log(f"  watchlist already done: {video_id}")
                return
        except json.JSONDecodeError:
            pass
    # If dated E_Main already on disk, skip (unless force)
    wl_dir = OUTPUT_DIR / "watchlists"
    if not force and wl_dir.is_dir():
        has_emain = (wl_dir / f"{video_id}.E_Main.txt").exists() or any(
            wl_dir.glob(f"*{video_id}*E_Main*.txt")
        )
        if has_emain:
            _log(f"  E_Main txt exists: {video_id}")
            return
    slim = SUMMARY_DIR / f"{video_id}.watchlist.json"
    if not force and slim.exists():
        _log(f"  watchlist summary exists: {video_id}")
        return
    # Primary: E_Main sidebar (auto). Potent screener is secondary-only.
    extra: list[str] = ["--mode", "auto"]
    from app.config import settings as _settings

    if getattr(_settings, "watchlist_vision", True) and (
        (_settings.openai_api_key or "").strip()
        or (getattr(_settings, "vision_ollama_model", "") or "").strip()
    ):
        extra.append("--vision")
    if upload_date:
        extra.extend(["--upload-date", str(upload_date)])
    if force:
        extra.append("--force")
    _log(f"  kick watchlist: {video_id} {' '.join(extra)}")
    _start_job(
        "watchlist_job.py",
        video_id,
        WATCHLIST_JOB_DIR,
        extra_args=extra,
        meta={"upload_date": upload_date} if upload_date else None,
    )


def analyze_video(
    video_id: str,
    title: str | None = None,
    *,
    upload_date: str | None = None,
) -> str:
    """Build speech summary; kick dual-ASR verify + classified watchlist. Returns status tag."""
    meta = fetch_video_meta(video_id)
    title = (title or meta.get("title") or video_id).strip()
    _log(f"Analyze {video_id} — {title}")

    tr = load_transcript(video_id)
    if tr and tr.get("snippets"):
        snippets = list(tr["snippets"])
        source = str(tr.get("source") or "cached")
        chunks = tr.get("chunks") or chunk_transcript(snippets, settings.chunk_seconds)
        _log(f"  reuse transcript ({source}, {len(snippets)} snips)")
    else:
        try:
            snippets = fetch_captions(video_id)
            chunks = chunk_transcript(snippets, settings.chunk_seconds)
            save_transcript(video_id, snippets, chunks, source="captions")
            source = "captions"
            _log(f"  YouTube CC OK ({len(snippets)} snips)")
        except Exception as e:
            msg = str(e)
            captions_off = (
                isinstance(e, CaptionsDisabledError)
                or "TranscriptsDisabled" in type(e).__name__
                or "Subtitles are disabled" in msg
                or "Could not retrieve a transcript" in msg
                or "No transcripts were found" in msg
            )
            if not captions_off:
                raise
            _log(f"  no CC — start whisper_job: {e}")
            _start_job("whisper_job.py", video_id, WHISPER_JOB_DIR)
            return "whisper_started"

    build_and_save_summary(
        video_id,
        title=title,
        source=source,
        snippets=snippets,
        chunks=chunks,
    )
    _log(f"  summary written → data/summaries/{video_id}.md")
    _kick_asr_compare(video_id)
    _kick_watchlist(video_id, upload_date=upload_date)
    return "summarized"


def finish_pending_whisper(state: dict[str, Any]) -> None:
    pending = list(state.get("pending_whisper") or [])
    if not pending:
        return
    still: list[str] = []
    for video_id in pending:
        tr = load_transcript(video_id)
        job_path = WHISPER_JOB_DIR / f"{video_id}.json"
        job: dict[str, Any] = {}
        if job_path.exists():
            try:
                job = json.loads(job_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                job = {}
        if not tr or not tr.get("snippets"):
            if job.get("status") == "error":
                _log(f"pending {video_id}: whisper error — drop from queue")
                continue
            _log(f"pending {video_id}: whisper still {job.get('status') or 'waiting'}")
            still.append(video_id)
            continue
        if _summary_exists(video_id):
            _log(f"pending {video_id}: summary already exists — kick compare/watchlist if needed")
            _kick_asr_compare(video_id)
            _kick_watchlist(video_id)
            continue
        meta = fetch_video_meta(video_id)
        tag = analyze_video(video_id, title=str(meta.get("title") or video_id))
        if tag == "whisper_started":
            still.append(video_id)
    state["pending_whisper"] = still


def main() -> int:
    p = argparse.ArgumentParser(description="Martin Luk daily new-stream check")
    p.add_argument("--playlist-end", type=int, default=10)
    p.add_argument(
        "--bootstrap",
        action="store_true",
        help="Seed known_ids from current playlist; do not analyze",
    )
    p.add_argument(
        "--force-id",
        action="append",
        default=[],
        help="Force-analyze this video id (can repeat)",
    )
    p.add_argument(
        "--watchlist-id",
        action="append",
        default=[],
        help="Force-run on-screen watchlist OCR for this video id (can repeat)",
    )
    p.add_argument(
        "--skip-watchlist",
        action="store_true",
        help="Do not spawn watchlist_job after analyze",
    )
    args = p.parse_args()
    global _WATCHLIST_ENABLED
    _WATCHLIST_ENABLED = not bool(args.skip_watchlist)
    ensure_dirs()
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

    state = _load_state()
    known = set(state.get("known_ids") or [])

    try:
        items = list_recent_streams(args.playlist_end)
    except Exception as e:
        _log(f"FATAL list streams: {e}")
        return 1

    _log(f"playlist: {len(items)} streams from @martinlukkt/streams")
    for it in items[:5]:
        _log(f"  {it['id']}  {it.get('upload_date') or '?'}  {it['title'][:60]}")

    if args.bootstrap or not known:
        if not known:
            _log("first run — bootstrap known_ids (no analyze of old VODs)")
        else:
            _log("bootstrap requested — refresh known_ids only")
        for it in items:
            known.add(it["id"])
        state["known_ids"] = sorted(known)
        _save_state(state)
        if args.bootstrap or not (args.force_id or args.watchlist_id):
            _log("done (bootstrap)")
            return 0

    for wid in args.watchlist_id:
        try:
            _kick_watchlist(wid, force=True)
        except Exception as e:
            _log(f"watchlist {wid} failed: {e}")

    finish_pending_whisper(state)

    for fid in args.force_id:
        try:
            meta = fetch_video_meta(fid)
            tag = analyze_video(fid, title=str(meta.get("title") or fid))
            if tag == "whisper_started":
                pw = set(state.get("pending_whisper") or [])
                pw.add(fid)
                state["pending_whisper"] = sorted(pw)
            known.add(fid)
        except Exception as e:
            _log(f"force {fid} failed: {e}")

    new_items = [it for it in items if it["id"] not in known]
    if not new_items:
        _log("no new streams")
    else:
        _log(f"{len(new_items)} new stream(s)")

    # Local auto-backfill: playlist recent + has digest but no E_Main → OCR/TV without bot
    for it in items[:8]:
        vid = it["id"]
        wl_dir = OUTPUT_DIR / "watchlists"
        has = False
        if wl_dir.is_dir():
            has = (wl_dir / f"{vid}.E_Main.txt").exists() or any(
                wl_dir.glob(f"*{vid}*E_Main*.txt")
            )
            ud = (it.get("upload_date") or "").strip()
            if len(ud) == 8 and ud.isdigit():
                dated = wl_dir / f"Martin_Luk_{ud[:4]}-{ud[4:6]}-{ud[6:8]}_E_Main.txt"
                if dated.exists():
                    has = True
        jobp = WATCHLIST_JOB_DIR / f"{vid}.json"
        job_done = False
        if jobp.exists():
            try:
                job_done = json.loads(jobp.read_text(encoding="utf-8")).get("status") == "done"
            except json.JSONDecodeError:
                pass
        if has or job_done:
            continue
        if not _summary_exists(vid):
            continue
        _log(f"backfill E_Main (local auto): {vid}")
        try:
            _kick_watchlist(vid, upload_date=it.get("upload_date") or None)
        except Exception as e:
            _log(f"backfill {vid} failed: {e}")
        for it in new_items:
            vid = it["id"]
            try:
                if _summary_exists(vid):
                    _log(f"  {vid}: summary exists — mark known + kick compare/watchlist")
                    _kick_asr_compare(vid)
                    _kick_watchlist(vid, upload_date=it.get("upload_date") or None)
                    known.add(vid)
                    continue
                tag = analyze_video(
                    vid,
                    title=it.get("title"),
                    upload_date=it.get("upload_date") or None,
                )
                known.add(vid)
                if tag == "whisper_started":
                    pw = set(state.get("pending_whisper") or [])
                    pw.add(vid)
                    state["pending_whisper"] = sorted(pw)
            except Exception as e:
                _log(f"  {vid} FAILED: {e}")
                # keep unknown so next run retries
                continue

    # Also remember ids we saw (even skipped) so playlist churn doesn't re-queue
    for it in items:
        known.add(it["id"])
    state["known_ids"] = sorted(known)

    pending = list(state.get("pending_whisper") or [])
    if pending:
        _wait_for_whisper_jobs(pending)
        finish_pending_whisper(state)

    _save_state(state)
    _log(
        f"done | known={len(known)} pending_whisper={len(state.get('pending_whisper') or [])}"
    )
    from app.side_audit import scan_outputs_gate

    hits = scan_outputs_gate()
    if hits:
        _log(f"SIDE GATE FAIL {len(hits)} — fix digest before push")
        for h in hits[:15]:
            _log(f"  {h}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
