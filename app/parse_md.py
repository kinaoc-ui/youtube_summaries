from __future__ import annotations

import re
from typing import Any


BULLET_RE = re.compile(r"^-\s+`([^`]+)`\s+(.+)$")


def _section(md: str, heading: str) -> str | None:
    """Return body under a ## heading until next ##."""
    pat = rf"^##\s+{re.escape(heading)}\s*\n([\s\S]*?)(?=^##\s|\Z)"
    m = re.search(pat, md, flags=re.MULTILINE)
    return m.group(1) if m else None


def parse_mixed_bullets(body: str | None) -> list[dict[str, str]]:
    """Timestamped `- `t` text` plus untimed `- **總覽**` lines, in order."""
    if not body:
        return []
    out: list[dict[str, str]] = []
    for line in body.splitlines():
        line = line.strip()
        m = BULLET_RE.match(line)
        if m:
            out.append({"t": m.group(1), "text": m.group(2).strip(), "start": "0"})
            continue
        if line.startswith("- "):
            out.append({"t": "", "text": line[2:].replace("**", "").strip(), "start": "0"})
    return out


def parse_bullets_block(body: str | None) -> list[dict[str, str]]:
    if not body:
        return []
    out: list[dict[str, str]] = []
    for line in body.splitlines():
        m = BULLET_RE.match(line.strip())
        if m:
            out.append({"t": m.group(1), "text": m.group(2).strip(), "start": "0"})
    return out


def parse_summary_markdown(md: str) -> dict[str, Any]:
    title_m = re.match(r"^#\s+(.+)$", md.splitlines()[0]) if md else None
    title = title_m.group(1).strip() if title_m else ""

    digest_body = _section(md, "真正摘要（中文）")
    digest_items = parse_mixed_bullets(digest_body)

    # Prefer Chinese exec; fall back to English heading
    exec_body = (
        digest_body
        or _section(md, "重點摘要（中文）")
        or _section(md, "Executive summary")
    )
    exec_items = parse_mixed_bullets(exec_body)
    # If exec is theme-only, lift ticker-board markdown table into the same list
    if not any("|" in (x.get("text") or "") for x in exec_items):
        board = _section(md, "Ticker board（提及）") or _section(md, "Ticker board")
        if board:
            for line in board.splitlines():
                line = line.strip()
                if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", ":"}:
                    continue
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) < 2 or cells[0].lower() in {"ticker", "股票"}:
                    continue
                extra = " | ".join(cells[2:]) if len(cells) > 2 else ""
                text = f"{cells[0]} | {cells[1]}" + (f" | {extra}" if extra else " | 見時間軸 | 見時間軸")
                exec_items.append({"t": "", "text": text, "start": "0"})

    bullets_en = parse_bullets_block(
        _section(md, "Timeline content (EN)")
        or _section(md, "Timestamped notes")
        or _section(md, "Timestamped notes (EN)")
    )
    content_body = _section(md, "時間軸內容")
    content_items = parse_bullets_block(content_body)
    bullets_zh = parse_bullets_block(
        content_body
        or _section(md, "時間軸重點（中文）")
        or _section(md, "Timestamped notes (ZH)")
    )
    # Legacy single-list fallback
    if not bullets_en and not bullets_zh:
        bullets_en = parse_bullets_block(_section(md, "Timestamped notes"))
        if not bullets_en:
            # whole-file scrape
            bullets_en = []
            for line in md.splitlines():
                m = BULLET_RE.match(line.strip())
                if m:
                    bullets_en.append({"t": m.group(1), "text": m.group(2).strip(), "start": "0"})

    out = {
        "title": title,
        "digest_zh": digest_items or exec_items,
        "content_zh": content_items,
        "exec_zh": digest_items or exec_items,
        "bullets_en": bullets_en,
        "bullets_zh": bullets_zh,
        "bullets": bullets_zh or bullets_en,
    }
    # #region agent log
    try:
        import json
        import time
        from pathlib import Path

        from .config import ROOT

        heads = [ln for ln in (md or "").splitlines() if ln.startswith("## ")]
        with (ROOT / "debug-ec629f.log").open("a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "ec629f",
                        "hypothesisId": "A",
                        "location": "parse_md.py:parse_summary_markdown",
                        "message": "parsed_section_counts",
                        "data": {
                            "heads": heads[:12],
                            "digest_n": len(digest_items),
                            "exec_n": len(exec_items),
                            "content_n": len(content_items),
                            "zh_n": len(bullets_zh),
                            "en_n": len(bullets_en),
                            "digest_has_pipe": any("|" in (x.get("text") or "") for x in (digest_items or [])),
                            "content_has_pipe": any("|" in (x.get("text") or "") for x in (content_items or [])),
                            "has_digest_h": bool(digest_body),
                            "has_content_h": bool(content_body),
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
    return out
