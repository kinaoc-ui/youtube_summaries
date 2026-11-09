from pathlib import Path

p = Path("app/watchlist_extract.py")
text = p.read_text(encoding="utf-8")

# Replace sample_sidebar_seconds with last-second / -10s only
old = '''def sample_sidebar_seconds(
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

new = '''def sample_sidebar_seconds(
    duration: float,
    *,
    video_id: str | None = None,
    last_minutes: float = 8.0,
    interval_sec: float = 45.0,
    max_frames: int = 12,
) -> list[float]:
    """Only last second of VOD, then -10s steps. No whole-stream scan."""
    if duration <= 0:
        return []
    # last frame ~1s before end (avoid black), then walk back 10s
    end = max(0.0, duration - 1.0)
    times = [end]
    t = end - 10.0
    # keep a few backups only (default still tiny)
    n = max(1, int(max_frames))
    while t >= 0 and len(times) < n:
        times.append(t)
        t -= 10.0
    return times
'''

if old not in text:
    raise SystemExit("sample_sidebar_seconds block missing")
text = text.replace(old, new, 1)

# Lower early-stop threshold: any sidebar with >=3 symbols
text2 = text.replace(
    "if prefer_sidebar and n_sym >= 5 and n_hdr >= 1:",
    "if prefer_sidebar and n_sym >= 3:",
    1,
)
p.write_text(text2, encoding="utf-8")

# martin_daily: max-frames 3 only
md = Path("scripts/martin_daily.py")
mdt = md.read_text(encoding="utf-8")
mdt = mdt.replace('"--max-frames", "12"', '"--max-frames", "3"', 1)
mdt = mdt.replace('"--last-minutes", "8"', '"--last-minutes", "1"', 1)
md.write_text(mdt, encoding="utf-8")

wj = Path("scripts/watchlist_job.py")
wjt = wj.read_text(encoding="utf-8")
wjt = wjt.replace("max_frames: int = 12,", "max_frames: int = 3,", 1)
wjt = wjt.replace('p.add_argument("--max-frames", type=int, default=12)', 'p.add_argument("--max-frames", type=int, default=3)')
wj.write_text(wjt, encoding="utf-8")
print("patched last-1s / -10s")
