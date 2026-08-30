"""Heartbeat + estimated % for long ASR jobs (detect hang in WebUI)."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable


class JobProgress:
    def __init__(
        self,
        status_path: Path,
        *,
        video_id: str,
        audio_sec: float = 0.0,
        interval: float = 3.0,
    ) -> None:
        self.status_path = status_path
        self.video_id = video_id
        self.audio_sec = max(0.0, float(audio_sec or 0))
        self.interval = interval
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.t0 = time.time()
        self.phase = "prepare"
        self.phase_lo = 0.0
        self.phase_hi = 5.0
        self.phase_t0 = self.t0
        # Expected wall seconds for current phase (for ETA / %)
        self.phase_expect = 30.0
        self.detail = ""
        self.extra: dict[str, Any] = {}

    def set_phase(
        self,
        phase: str,
        *,
        lo: float,
        hi: float,
        expect_sec: float | None = None,
        detail: str = "",
    ) -> None:
        with self._lock:
            self.phase = phase
            self.phase_lo = lo
            self.phase_hi = hi
            self.phase_t0 = time.time()
            if expect_sec is not None:
                self.phase_expect = max(5.0, float(expect_sec))
            self.detail = detail
        self.flush()

    def _estimate_pct(self) -> float:
        elapsed_phase = max(0.0, time.time() - self.phase_t0)
        # Ease toward phase_hi but never reach it until phase completes
        span = max(0.1, self.phase_hi - self.phase_lo)
        frac = min(0.92, elapsed_phase / self.phase_expect)
        return round(self.phase_lo + span * frac, 1)

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            pct = self._estimate_pct()
            elapsed = round(now - self.t0, 1)
            remain_phase = max(0.0, self.phase_expect - (now - self.phase_t0))
            # Rough total ETA: remaining in phase + tail after phase_hi
            tail = max(0.0, (100.0 - self.phase_hi) / 100.0 * max(self.audio_sec, 60.0) * 0.15)
            eta = round(remain_phase + tail, 0)
            extra = {k: v for k, v in self.extra.items() if k not in {
                "status", "step", "progress_pct", "elapsed_sec", "eta_sec",
                "heartbeat_ts", "heartbeat_age_sec", "detail", "audio_sec",
            }}
            return {
                **extra,
                "video_id": self.video_id,
                "status": "running",
                "step": self.phase,
                "progress_pct": pct,
                "elapsed_sec": elapsed,
                "eta_sec": eta,
                "audio_sec": round(self.audio_sec, 1),
                "heartbeat_ts": int(now),
                "heartbeat_age_sec": 0,
                "detail": self.detail,
            }

    def flush(self) -> None:
        snap = self.snapshot()
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        cur: dict[str, Any] = {}
        if self.status_path.exists():
            try:
                cur = json.loads(self.status_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                cur = {}
        cur.update(snap)
        self.status_path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        # #region agent log
        try:
            from .config import ROOT

            dbg = ROOT / "debug-ec629f.log"
            with dbg.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "ec629f",
                            "hypothesisId": "P",
                            "location": "job_progress.flush",
                            "message": "progress",
                            "data": {
                                "step": snap.get("step"),
                                "pct": snap.get("progress_pct"),
                                "elapsed": snap.get("elapsed_sec"),
                                "eta": snap.get("eta_sec"),
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

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self.flush()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="job-progress", daemon=True)
        self._thread.start()
        self.flush()

    def stop(self, *, final_pct: float | None = None) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if final_pct is not None:
            with self._lock:
                self.phase_lo = final_pct
                self.phase_hi = final_pct
                self.phase_expect = 1.0
        self.flush()


def audio_duration_sec(path: Path) -> float:
    """Best-effort duration; whisperx audio is 16k mono float."""
    try:
        import wave

        if path.suffix.lower() == ".wav":
            with wave.open(str(path), "rb") as w:
                return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        pass
    try:
        from mutagen.mp3 import MP3

        return float(MP3(path).info.length)
    except Exception:
        pass
    # Fallback: file size heuristic for 96kbps mp3
    try:
        return max(60.0, path.stat().st_size / (96000 / 8))
    except Exception:
        return 0.0
