from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import OUTPUT_DIR, SUMMARY_DIR, ensure_dirs
from .parse_md import parse_summary_markdown


def save_summary(
    video_id: str,
    markdown: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Path]:
    ensure_dirs()
    from .speech_audit import audit_and_gate_markdown

    markdown, audit = audit_and_gate_markdown(video_id, markdown)
    # #region agent log
    try:
        from .config import ROOT as _ROOT
        import json as _json
        import time as _time

        with (_ROOT / "debug-ec629f.log").open("a", encoding="utf-8") as _f:
            _f.write(
                _json.dumps(
                    {
                        "sessionId": "ec629f",
                        "hypothesisId": "E",
                        "location": "storage.save_summary",
                        "message": "gated_save",
                        "data": {
                            "video_id": video_id,
                            "suspect_count": audit.get("suspect_count") or 0,
                            "ok_count": audit.get("ok_count") or 0,
                            "flagged": bool(audit.get("flagged")),
                            "suspects": [
                                {"t": s.get("t"), "ticker": s.get("ticker")}
                                for s in (audit.get("suspects") or [])[:20]
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
    md_path = SUMMARY_DIR / f"{video_id}.md"
    out_path = OUTPUT_DIR / f"{video_id}.md"
    meta_path = SUMMARY_DIR / f"{video_id}.json"
    md_path.write_text(markdown, encoding="utf-8")
    out_path.write_text(markdown, encoding="utf-8")
    parsed = parse_summary_markdown(markdown)
    payload = {
        "video_id": video_id,
        "markdown_path": str(md_path),
        "title": parsed.get("title") or (meta or {}).get("title") or video_id,
        "exec_zh": parsed.get("exec_zh") or [],
        "bullets_en": parsed.get("bullets_en") or [],
        "bullets_zh": parsed.get("bullets_zh") or [],
        "bullets": parsed.get("bullets_zh") or parsed.get("bullets_en") or [],
        "speech_audit": {
            "suspect_count": audit.get("suspect_count") or 0,
            "ok_count": audit.get("ok_count") or 0,
            "suspects": audit.get("suspects") or [],
        },
        **(meta or {}),
    }
    # keep parsed title authoritative if present
    if parsed.get("title"):
        payload["title"] = parsed["title"]
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"md": md_path, "output": out_path, "meta": meta_path}


def load_summary(video_id: str) -> dict[str, Any] | None:
    meta_path = SUMMARY_DIR / f"{video_id}.json"
    md_path = SUMMARY_DIR / f"{video_id}.md"
    md = md_path.read_text(encoding="utf-8") if md_path.exists() else None
    if meta_path.exists():
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        if md:
            data["markdown"] = md
            parsed = parse_summary_markdown(md)
            data.update({k: parsed[k] for k in ("exec_zh", "bullets_en", "bullets_zh", "title") if parsed.get(k)})
            data["bullets"] = parsed.get("bullets_zh") or parsed.get("bullets_en") or data.get("bullets") or []
        return data
    if md:
        parsed = parse_summary_markdown(md)
        return {"video_id": video_id, "markdown": md, **parsed}
    return None


def list_summaries() -> list[dict[str, Any]]:
    ensure_dirs()
    items: list[dict[str, Any]] = []
    for path in sorted(SUMMARY_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        video_id = path.stem
        md = path.read_text(encoding="utf-8")
        parsed = parse_summary_markdown(md)
        count = len(parsed.get("bullets_zh") or parsed.get("bullets_en") or [])
        items.append(
            {
                "video_id": video_id,
                "title": parsed.get("title") or video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "bullet_count": count,
            }
        )
    return items


def get_markdown(video_id: str) -> str | None:
    path = SUMMARY_DIR / f"{video_id}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    out = OUTPUT_DIR / f"{video_id}.md"
    if out.exists():
        return out.read_text(encoding="utf-8")
    return None
