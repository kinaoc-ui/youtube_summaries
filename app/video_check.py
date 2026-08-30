from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import DATA_DIR, OUTPUT_DIR, SUMMARY_DIR, ensure_dirs, settings
from .parse_md import parse_summary_markdown
from .transcript import format_ts, load_transcript

VIDEO_DIR = DATA_DIR / "video"
FRAMES_DIR = DATA_DIR / "frames"
VISION_JOB_DIR = DATA_DIR / "vision_jobs"

TICKER_RE = re.compile(r"\b([A-Z]{2,5})\b")
# Only trust these as on-screen / spoken tickers (avoid LONG/WAIT/INTO false positives)
KNOWN_TICKERS = {
    "SPCX", "AXTI", "TWLO", "OKTA", "CRM", "CRWD", "DDOG", "PATH", "IGV",
    "RDDT", "CRWV", "BE", "AOI", "SNDK", "MU", "APLD", "IREN", "SMCI",
    "HOOD", "SMR", "USAR", "HPQ", "QBTS", "RGTI", "IONQ", "ONDS", "ALAB",
    "AMD", "TSLA", "NVDA", "ARM", "SOXX", "MSTR", "RKLB", "ASTS", "QQQ",
    "SPY", "IWM", "HIMS", "OSK", "GLW", "IBM", "FTNT", "RBRK", "CRCL",
    "XYZ", "NVTS", "QUBT", "SMTK", "SNTK", "AVGO", "TSM", "PLTR", "META",
    "AMZN", "MSFT", "AAPL", "GOOGL", "GOOG", "BABA", "COIN", "MARA", "RIOT",
    "FIG", "FROG", "OKLO", "CLS", "TEM", "WDC", "ORCL", "SKHY", "DOGEUSD",
}

ASR_ALIASES = {
    "SAPCE": "SPCX",
    "SPACEX": "SPCX",
    "SPACE": "SPCX",
    "SPACES": "SPCX",
    "CORVIF": "CRWV",
    "SMTK": "SNDK",
    "SNTK": "SNDK",
    "SNK": "SNDK",
}


def parse_ts(t: str) -> float:
    parts = [int(x) for x in str(t).strip().split(":") if x != ""]
    if not parts:
        return 0.0
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return float(parts[0])


def stamp_name(seconds: float) -> str:
    return format_ts(seconds).replace(":", "-")


def ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found on PATH")
    return exe


def download_video(video_id: str, max_height: int | None = None) -> Path:
    """Download a small video (default 360p) for frame grabs — not just audio."""
    ensure_dirs()
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    dest = VIDEO_DIR / f"{video_id}.mp4"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    max_height = max_height or int(getattr(settings, "video_max_height", 360))
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        from yt_dlp import YoutubeDL
    except ImportError as e:
        raise RuntimeError("yt-dlp not installed") from e

    opts = {
        "format": (
            f"bestvideo[height<={max_height}][ext=mp4]"
            f"/bestvideo[height<={max_height}]"
            f"/best[height<={max_height}]"
            "/worstvideo[ext=mp4]/worst"
        ),
        "outtmpl": str(VIDEO_DIR / f"{video_id}.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": False,
        "overwrites": False,
    }
    with YoutubeDL(opts) as ydl:
        ydl.download([url])
    if dest.exists():
        return dest
    matches = sorted(VIDEO_DIR.glob(f"{video_id}.*"), key=lambda p: p.stat().st_size, reverse=True)
    if matches:
        return matches[0]
    raise RuntimeError(f"Video download failed for {video_id}")


def extract_frame(video_path: Path, seconds: float, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, seconds):.2f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-vf",
        "scale=960:-2",
        "-q:v",
        "4",
        "-y",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    if not out_path.exists():
        raise RuntimeError(f"ffmpeg did not write {out_path}")
    return out_path


def crop_ticker_strip(frame_path: Path, crop_path: Path) -> Path | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    im = Image.open(frame_path)
    w, h = im.size
    # Top bar (symbol title) + right watchlist — Martin’s TV layout
    top = im.crop((0, 0, int(w * 0.62), int(h * 0.12)))
    right = im.crop((int(w * 0.72), int(h * 0.08), w, int(h * 0.92)))
    # Stack into one image for OCR
    pad = 8
    out_w = max(top.width, right.width)
    out_h = top.height + pad + right.height
    canvas = Image.new("RGB", (out_w, out_h), (20, 20, 20))
    canvas.paste(top, (0, 0))
    canvas.paste(right, (0, top.height + pad))
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(crop_path, quality=92)
    return crop_path


def _ocr_rapidocr(image_path: Path) -> str:
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    result, _ = engine(str(image_path))
    if not result:
        return ""
    return " ".join(str(row[1]) for row in result if len(row) > 1)


def _ocr_tesseract(image_path: Path) -> str:
    import pytesseract
    from PIL import Image

    im = Image.open(image_path)
    return pytesseract.image_to_string(im) or ""


def ocr_image(image_path: Path) -> tuple[str, str]:
    """Return (text, engine_name)."""
    try:
        return _ocr_rapidocr(image_path), "rapidocr"
    except Exception:
        pass
    try:
        return _ocr_tesseract(image_path), "tesseract"
    except Exception:
        pass
    return "", "none"


def tickers_from_text(text: str) -> list[str]:
    found: list[str] = []
    upper = (text or "").upper()
    for raw, canon in ASR_ALIASES.items():
        if re.search(rf"\b{re.escape(raw)}\b", upper):
            if canon not in found:
                found.append(canon)
    # SpaceX company name on chart header
    if "SPACE EXPLORATION" in upper or "SPACEX" in upper.replace(" ", ""):
        if "SPCX" not in found:
            found.append("SPCX")
    for m in TICKER_RE.findall(upper):
        canon = ASR_ALIASES.get(m, m)
        if canon not in KNOWN_TICKERS:
            continue
        if canon not in found:
            found.append(canon)
    return found


def timestamps_from_summary(video_id: str) -> list[tuple[str, str]]:
    """(timestamp, bullet text) unique by time, exec first then timeline."""
    md_path = SUMMARY_DIR / f"{video_id}.md"
    if not md_path.exists():
        alt = OUTPUT_DIR / f"{video_id}.md"
        md_path = alt if alt.exists() else md_path
    rows: list[tuple[str, str]] = []
    texts: dict[str, list[str]] = {}
    if md_path.exists():
        parsed = parse_summary_markdown(md_path.read_text(encoding="utf-8"))
        for bucket in (parsed.get("exec_zh") or [], parsed.get("bullets_en") or [], parsed.get("bullets_zh") or []):
            for b in bucket:
                t = str(b.get("t") or "").strip()
                if not t or t == "00:00":
                    continue
                texts.setdefault(t, []).append(str(b.get("text") or ""))
        rows = [(t, " | ".join(v)) for t, v in texts.items()]
    if not rows:
        cached = load_transcript(video_id) or {}
        seen: set[str] = set()
        for c in cached.get("chunks") or []:
            t = str(c.get("t") or "")
            if t and t not in seen:
                seen.add(t)
                rows.append((t, str(c.get("text") or "")[:200]))
    return rows


def check_video(
    video_id: str,
    *,
    status_cb: Any | None = None,
) -> dict[str, Any]:
    def note(**kw: Any) -> None:
        if status_cb:
            status_cb(**kw)

    frames_root = FRAMES_DIR / video_id
    frames_root.mkdir(parents=True, exist_ok=True)
    note(step="download_video", status="running")
    video_path = download_video(video_id)
    times = timestamps_from_summary(video_id)
    note(step="extract_frames", status="running", frame_targets=len(times), video=str(video_path))
    items: list[dict[str, Any]] = []
    engine = "none"
    # Speech often lands while he is still switching charts — probe +8s / +16s
    # and keep the offset whose OCR overlaps claimed tickers (else keep t+0).
    probe_offsets = (0, 8, 16)
    for i, (t, claimed_text) in enumerate(times):
        seconds = parse_ts(t)
        claimed = tickers_from_text(claimed_text)
        best: dict[str, Any] | None = None
        try:
            candidates: list[dict[str, Any]] = []
            for off in probe_offsets:
                sec = seconds + off
                stamp = stamp_name(sec)
                jpg = frames_root / f"{stamp}.jpg"
                crop = frames_root / f"{stamp}_hdr.jpg"
                if not jpg.exists() or jpg.stat().st_size < 2000:
                    extract_frame(video_path, sec, jpg)
                if crop.exists():
                    crop.unlink()
                crop_ticker_strip(jpg, crop)
                ocr_src = crop if crop.exists() else jpg
                ocr_text, engine = ocr_image(ocr_src)
                ocr_tickers = tickers_from_text(ocr_text)
                overlap = set(ocr_tickers) & set(claimed)
                candidates.append(
                    {
                        "t": t,
                        "offset": off,
                        "seconds": sec,
                        "frame": f"/frames/{video_id}/{jpg.name}",
                        "header": f"/frames/{video_id}/{crop.name}" if crop.exists() else None,
                        "ocr": ocr_text.strip()[:240],
                        "ocr_tickers": ocr_tickers,
                        "claimed": claimed,
                        "mismatch": bool(ocr_tickers and claimed and not overlap),
                        "overlap": sorted(overlap),
                    }
                )
            # Prefer a probe that matches claimed speech tickers
            matched = [c for c in candidates if c["overlap"]]
            best = matched[0] if matched else candidates[0]
            # #region agent log
            try:
                import time as _time

                _log = Path(__file__).resolve().parents[1] / "debug-ec629f.log"
                with _log.open("a", encoding="utf-8") as _f:
                    _f.write(
                        json.dumps(
                            {
                                "sessionId": "ec629f",
                                "hypothesisId": "F",
                                "location": "video_check.py:check_video",
                                "message": "frame_probe",
                                "data": {
                                    "note_t": t,
                                    "claimed": claimed,
                                    "picked_offset": best.get("offset"),
                                    "picked_t": best.get("t"),
                                    "candidates": [
                                        {
                                            "offset": c["offset"],
                                            "ocr_tickers": c["ocr_tickers"],
                                            "overlap": c["overlap"],
                                        }
                                        for c in candidates
                                    ],
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
            items.append(best)
        except Exception as e:
            items.append({"t": t, "seconds": seconds, "error": str(e), "claimed": claimed})
        if i % 5 == 0:
            note(step="extract_frames", status="running", done=i + 1, total=len(times))

    mismatches = [x for x in items if x.get("mismatch")]
    report = {
        "video_id": video_id,
        "video_path": str(video_path),
        "ocr_engine": engine,
        "frame_count": len(items),
        "mismatch_count": len(mismatches),
        "items": items,
    }
    report_path = frames_root / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    note(step="done", status="done", frame_count=len(items), mismatch_count=len(mismatches), ocr_engine=engine)
    return report


def load_report(video_id: str) -> dict[str, Any] | None:
    path = FRAMES_DIR / video_id / "report.json"
    labels_path = FRAMES_DIR / video_id / "labels.json"
    report: dict[str, Any] | None = None
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
    if labels_path.exists():
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        by = labels.get("by_t") or {}
        if report is None:
            report = {"video_id": video_id, "items": []}
        items = report.get("items") or []
        idx = {x.get("t"): i for i, x in enumerate(items)}
        for t, lab in by.items():
            sym = lab.get("symbol")
            tickers = [sym] if sym else []
            stamp = str(t).replace(":", "-")
            patch = {
                "t": t,
                "frame": f"/frames/{video_id}/{stamp}.jpg",
                "ocr_tickers": tickers,
                "screen_symbol": sym,
                "screen_name": lab.get("name"),
                "screen_price": lab.get("price"),
                "label_source": labels.get("source") or "cursor-agent",
            }
            if t in idx:
                old = items[idx[t]]
                claimed = old.get("claimed") or []
                patch["claimed"] = claimed
                patch["mismatch"] = bool(tickers and claimed and not (set(tickers) & set(claimed)))
                items[idx[t]] = {**old, **patch}
            else:
                items.append({**patch, "claimed": [], "mismatch": False})
        report["items"] = items
        report["label_source"] = labels.get("source") or "cursor-agent"
        report["ocr_engine"] = report.get("label_source")
        report["labeled"] = len(by)
        report["by_t"] = {str(x.get("t")): x for x in items if x.get("t")}
    return report
