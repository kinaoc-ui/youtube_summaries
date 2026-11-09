from pathlib import Path

p = Path("app/watchlist_extract.py")
text = p.read_text(encoding="utf-8")

old_sample = '''def sample_screener_seconds(
    duration: float,
    *,
    video_id: str | None = None,
    coarse_interval: float = 45.0,
    dense_interval: float = 12.0,
    dense_radius: float = 90.0,
    tail_minutes: float = 12.0,
    max_frames: int = 90,
) -> list[float]:
    """Whole-VOD coarse grid + densify around speech hints + modest tail densify."""
'''

if "def sample_sidebar_seconds(" not in text:
    insert = '''def sample_sidebar_seconds(
    duration: float,
    *,
    video_id: str | None = None,
    last_minutes: float = 8.0,
    interval_sec: float = 45.0,
    max_frames: int = 12,
) -> list[float]:
    """Cheap E_Main path: a few speech-hint snaps + sparse tail. Stop early elsewhere."""
    if duration <= 0:
        return []
    times: list[float] = []
    centers = speech_hint_seconds(video_id) if video_id else []
    for c in centers[-6:]:
        times.append(max(0.0, min(duration - 2.0, float(c))))
    times.extend(
        sample_tail_seconds(
            duration,
            last_minutes=last_minutes,
            interval_sec=max(20.0, float(interval_sec)),
        )
    )
    times.append(max(0.0, duration - 5.0))
    times = _dedupe_times(times)
    times = sorted(times, reverse=True)
    return times[: max(1, int(max_frames))]


'''
    if old_sample not in text:
        raise SystemExit("sample_screener_seconds header not found")
    text = text.replace(old_sample, insert + old_sample, 1)

old_sig = '''def extract_watchlist(
    video_id: str,
    *,
    mode: str = "auto",
    last_minutes: float = 10.0,
    interval_sec: float = 20.0,
    coarse_interval: float = 45.0,
    dense_interval: float = 12.0,
    max_frames: int = 90,
'''
new_sig = '''def extract_watchlist(
    video_id: str,
    *,
    mode: str = "auto",
    last_minutes: float = 8.0,
    interval_sec: float = 45.0,
    coarse_interval: float = 45.0,
    dense_interval: float = 12.0,
    max_frames: int = 12,
'''
if old_sig not in text:
    raise SystemExit("extract_watchlist signature not found")
text = text.replace(old_sig, new_sig, 1)

old_dl = '''    note(step="download_video", status="running", mode=mode)
    video_path = download_video(video_id)

    duration = video_duration_sec(video_path)
    if duration <= 0:
        duration = duration_from_transcript(video_id)
    if duration <= 0:
        raise RuntimeError(f"Cannot determine duration for {video_id}")

    if prefer_sidebar:
        # Dense tail + modest whole-VOD sample — E_Main lives on chart frames
        times = sample_screener_seconds(
            duration,
            video_id=video_id,
            coarse_interval=max(coarse_interval, 60.0),
            dense_interval=dense_interval,
            tail_minutes=max(last_minutes, 15.0),
            max_frames=max_frames,
        )
    else:
        times = sample_screener_seconds(
            duration,
            video_id=video_id,
            coarse_interval=coarse_interval,
            dense_interval=dense_interval,
            tail_minutes=max(last_minutes, 12.0),
            max_frames=max_frames,
        )
'''
new_dl = '''    from .video_check import VIDEO_DIR

    cached = VIDEO_DIR / f"{video_id}.mp4"
    reuse = cached.exists() and cached.stat().st_size > 1_000_000
    note(
        step="reuse_video" if reuse else "download_video",
        status="running",
        mode=mode,
        reuse=reuse,
    )
    video_path = download_video(video_id)

    duration = video_duration_sec(video_path)
    if duration <= 0:
        duration = duration_from_transcript(video_id)
    if duration <= 0:
        raise RuntimeError(f"Cannot determine duration for {video_id}")

    if prefer_sidebar:
        # Cap a few end/speech frames — do NOT scan whole VOD for E_Main list
        times = sample_sidebar_seconds(
            duration,
            video_id=video_id,
            last_minutes=max(last_minutes, 6.0),
            interval_sec=max(interval_sec, 30.0),
            max_frames=max_frames,
        )
    else:
        times = sample_screener_seconds(
            duration,
            video_id=video_id,
            coarse_interval=coarse_interval,
            dense_interval=dense_interval,
            tail_minutes=max(last_minutes, 12.0),
            max_frames=max_frames,
        )
'''
if old_dl not in text:
    raise SystemExit("download/sample block not found")
text = text.replace(old_dl, new_dl, 1)

needle = '''            if side.get("sidebar") and (side.get("symbols") or side.get("headers")):
                sidebar_candidates.append(row)
        except Exception as e:
            frame_rows.append({"t": format_ts(sec), "seconds": sec, "error": str(e)})
        if i % 3 == 0:
            note(step="extract_frames", status="running", done=i + 1, total=len(times), mode=mode)
'''
repl = '''            if side.get("sidebar") and (side.get("symbols") or side.get("headers")):
                sidebar_candidates.append(row)
                # Good enough list capture — stop; no need to watch the whole VOD
                n_sym = len(side.get("symbols") or [])
                n_hdr = len(side.get("headers") or [])
                if prefer_sidebar and n_sym >= 5 and n_hdr >= 1:
                    note(
                        step="extract_frames",
                        status="early_stop",
                        done=i + 1,
                        total=len(times),
                        mode=mode,
                        symbols=n_sym,
                        headers=n_hdr,
                    )
                    break
        except Exception as e:
            frame_rows.append({"t": format_ts(sec), "seconds": sec, "error": str(e)})
        if i % 3 == 0:
            note(step="extract_frames", status="running", done=i + 1, total=len(times), mode=mode)
'''
if needle not in text:
    raise SystemExit("early-exit needle not found")
text = text.replace(needle, repl, 1)

p.write_text(text, encoding="utf-8")
print("patched watchlist_extract.py")

wj = Path("scripts/watchlist_job.py")
wjt = wj.read_text(encoding="utf-8")
wjt2 = wjt.replace("max_frames: int = 90,", "max_frames: int = 12,", 1)
wjt2 = wjt2.replace("last_minutes: float = 10.0,", "last_minutes: float = 8.0,", 1)
wjt2 = wjt2.replace("interval_sec: float = 20.0,", "interval_sec: float = 45.0,", 1)
wjt2 = wjt2.replace(
    'p.add_argument("--max-frames", type=int, default=90)',
    'p.add_argument("--max-frames", type=int, default=12)',
)
wjt2 = wjt2.replace(
    'p.add_argument("--last-minutes", type=float, default=10.0, help="Tail densify window")',
    'p.add_argument("--last-minutes", type=float, default=8.0, help="Tail window for E_Main snaps")',
)
wjt2 = wjt2.replace(
    'p.add_argument("--interval", type=float, default=20.0, help="Tail-mode interval seconds")',
    'p.add_argument("--interval", type=float, default=45.0, help="Seconds between tail snaps")',
)
if wjt2 == wjt:
    raise SystemExit("watchlist_job patch no-op")
wj.write_text(wjt2, encoding="utf-8")
print("patched watchlist_job.py")

md = Path("scripts/martin_daily.py")
mdt = md.read_text(encoding="utf-8")
old = '''    # Primary: E_Main sidebar (auto). Potent screener is secondary-only.
    extra: list[str] = ["--mode", "auto"]
'''
new = '''    # Primary: E_Main sidebar (auto). Cheap: few end frames, stop when list captured.
    extra: list[str] = [
        "--mode", "auto",
        "--max-frames", "12",
        "--last-minutes", "8",
        "--interval", "45",
        "--no-vision",
    ]
'''
if old not in mdt:
    raise SystemExit("martin_daily kick block not found")
mdt = mdt.replace(old, new, 1)
old_vis = '''    from app.config import settings as _settings

    if getattr(_settings, "watchlist_vision", True) and (
        (_settings.openai_api_key or "").strip()
        or (getattr(_settings, "vision_ollama_model", "") or "").strip()
    ):
        extra.append("--vision")
    if upload_date:
'''
new_vis = '''    if upload_date:
'''
if old_vis not in mdt:
    raise SystemExit("vision block not found")
mdt = mdt.replace(old_vis, new_vis, 1)
md.write_text(mdt, encoding="utf-8")
print("patched martin_daily.py")

Path("run_martin_daily.bat").write_text(
    """@echo off
setlocal EnableExtensions
cd /d \"%~dp0\"

REM Ensure TV auto-upload even if .env has BOM / missing keys
if not defined TUBEON_TV_UPLOAD set \"TUBEON_TV_UPLOAD=1\"
if not defined TUBEON_TV_SCREENING_ROOT set \"TUBEON_TV_SCREENING_ROOT=%~dp0..\\screening\"
if not defined TUBEON_TV_CDP_PORT set \"TUBEON_TV_CDP_PORT=9222\"
if not defined TUBEON_TV_AUTO_LAUNCH set \"TUBEON_TV_AUTO_LAUNCH=1\"
REM Default: no pause popup. Set MARTIN_DAILY_PAUSE=1 only if you want to read the window.
set \"MARTIN_DAILY_NOPAUSE=1\"

set \"PYTHON_EXE=\"
where py >nul 2>&1 && set \"PYTHON_EXE=py\"
if not defined PYTHON_EXE (
  where python >nul 2>&1 && set \"PYTHON_EXE=python\"
)
if not defined PYTHON_EXE (
  if exist \"%LOCALAPPDATA%\\Programs\\Python\\Python311\\python.exe\" (
    set \"PYTHON_EXE=%LOCALAPPDATA%\\Programs\\Python\\Python311\\python.exe\"
  )
)

if not defined PYTHON_EXE (
  echo [ERROR] Python not found.
  exit /b 1
)

if exist \"C:\\Program Files\\Git\\cmd\" set \"PATH=C:\\Program Files\\Git\\cmd;%PATH%\"

echo [%date% %time%] Martin Luk daily check...
\"%PYTHON_EXE%\" \"%~dp0scripts\\martin_daily.py\" %*
set \"RC=%ERRORLEVEL%\"
echo [%date% %time%] exit %RC%
if defined MARTIN_DAILY_PAUSE pause
exit /b %RC%
""",
    encoding="ascii",
)
print("patched bat")
print("OK")
