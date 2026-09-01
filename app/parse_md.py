from __future__ import annotations

import re
from typing import Any


# Backtick stamps or GitHub-clickable [mm:ss](youtube&t=Ns)
BULLET_RE = re.compile(
    r"^-\s+(?:`([^`]+)`|\[(\d{1,2}:\d{2}(?::\d{2})?)\]\([^)]+\))\s+(.+)$"
)
_BARE_STAMP_LINE = re.compile(r"^(\s*-\s+)`(\d{1,2}:\d{2}(?::\d{2})?)`")
_DIGEST_STAMP_STRIP = re.compile(
    r"^(-\s+\*\*(?:做多|做空|減倉|觀望偏空|觀望偏多|觀望|實際操作)｜[^*]+\*\*)\s+\[[^\]]+\]\([^)]+\)(\s+[—–-]\s+.*)$"
)
_DIGEST_HEAD = re.compile(
    r"^(-\s+\*\*(?:做多|做空|減倉|觀望偏空|觀望偏多|觀望|實際操作)｜([^*]+)\*\*)"
    r"(?!\s+\[)"
    r"(\s+[—–-]\s+.*)$"
)


def time_to_seconds(stamp: str) -> int | None:
    parts = (stamp or "").strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    return None


def yt_watch_url(video_id: str, stamp: str | None = None) -> str:
    url = f"https://www.youtube.com/watch?v={video_id}"
    sec = time_to_seconds(stamp or "")
    if sec is not None:
        url += f"&t={int(sec)}s"
    return url


def stamp_md_link(video_id: str, stamp: str) -> str:
    """Markdown timestamp that GitHub / phone can tap to that second on YouTube."""
    t = (stamp or "").strip()
    if not video_id or time_to_seconds(t) is None:
        return f"`{t}`" if t else "`00:00`"
    return f"[{t}]({yt_watch_url(video_id, t)})"


def split_bullet(line: str) -> tuple[str, str] | None:
    m = BULLET_RE.match((line or "").strip())
    if not m:
        return None
    return ((m.group(1) or m.group(2) or "").strip(), (m.group(3) or "").strip())


def linkify_markdown(video_id: str, md: str) -> str:
    """Turn bare `mm:ss` bullets into YouTube links; add digest stamp links."""
    if not video_id or not md:
        return md
    out_lines: list[str] = []
    for line in md.splitlines():
        m = _BARE_STAMP_LINE.match(line)
        if m:
            line = f"{m.group(1)}{stamp_md_link(video_id, m.group(2))}{line[m.end():]}"
        out_lines.append(line)
    text = "\n".join(out_lines)
    pick: dict[str, str] = {}
    for line in text.splitlines():
        got = split_bullet(line)
        if not got:
            continue
        t, rest = got
        tm = re.search(r"\*\*(.+?)\*\*", rest)
        if not tm:
            continue
        label = tm.group(1).strip()
        if label in {"字幕缺口", "Mute gap"}:
            continue
        cells = [c.strip() for c in rest.split("|")]
        side = cells[1] if len(cells) > 1 else ""
        actionable = bool(re.search(r"\b(Long|Short|Trim)\b|減倉|平倉|做空|做多", side, re.I))
        if label not in pick or actionable:
            pick[label] = t

    stripped = [_DIGEST_STAMP_STRIP.sub(r"\1\2", line) for line in text.splitlines()]

    def _digest_stamp(m: re.Match[str]) -> str:
        raw_label = (m.group(2) or "").strip()
        ticker = raw_label.split("—")[0].strip()
        ticker = re.sub(r"（.*?）|\(.*?\)", "", ticker).strip()
        t = pick.get(ticker) or pick.get(ticker.split()[0] if ticker else "")
        if not t:
            for k, v in pick.items():
                if k.lower() == ticker.lower():
                    t = v
                    break
        if not t:
            return m.group(0)
        return f"{m.group(1)} {stamp_md_link(video_id, t)}{m.group(3)}"

    return "\n".join(
        _DIGEST_HEAD.sub(_digest_stamp, line) for line in stripped
    ) + ("\n" if md.endswith("\n") else "")


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
        got = split_bullet(line)
        if got:
            out.append({"t": got[0], "text": got[1], "start": "0"})
            continue
        dm = re.match(
            r"^-\s+\*\*(.+?)\*\*(?:\s+\[(\d{1,2}:\d{2}(?::\d{2})?)\]\([^)]+\))?(?:\s*[—–-]\s*(.*))?$",
            line,
        )
        if dm and line.startswith("- "):
            head, stamp, rest = dm.group(1).strip(), dm.group(2) or "", (dm.group(3) or "").strip()
            text = f"{head} — {rest}" if rest else head
            out.append({"t": stamp, "text": text, "start": "0"})
            continue
        if line.startswith("- "):
            out.append({"t": "", "text": line[2:].replace("**", "").strip(), "start": "0"})
    return out


def parse_bullets_block(body: str | None) -> list[dict[str, str]]:
    if not body:
        return []
    out: list[dict[str, str]] = []
    for line in body.splitlines():
        got = split_bullet(line)
        if got:
            out.append({"t": got[0], "text": got[1], "start": "0"})
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
                got = split_bullet(line)
                if got:
                    bullets_en.append({"t": got[0], "text": got[1], "start": "0"})

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
