#!/usr/bin/env python3
"""Phone reader for Martin Luk summaries — reads outputs/*.md only. No Whisper."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "outputs"

SIDE_COLORS = {
    "long": ("#14532d", "#86efac", "做多"),
    "short": ("#7f1d1d", "#fca5a5", "做空"),
    "watch_short": ("#7f1d1d", "#fca5a5", "觀望偏空"),
    "watch_long": ("#14532d", "#86efac", "觀望偏多"),
    "watch": ("#1e3a5f", "#93c5fd", "觀望"),
    "trim": ("#713f12", "#fde047", "減倉"),
    "action": ("#3f3f46", "#e4e4e7", "實際操作"),
    "mute": ("#27272a", "#a1a1aa", "字幕缺口"),
}

_ROW = re.compile(
    r"^- (?:`([^`]+)`|\[(\d{1,2}:\d{2}(?::\d{2})?)\]\(([^)]+)\)) "
    r"\*\*(.+?)\*\* \| ([^|]+) \| ([^|]+) \| (.*)$"
)
_DIGEST = re.compile(
    r"^- \*\*(.+?)\*\*"
    r"(?:\s+\[(\d{1,2}:\d{2}(?::\d{2})?)\]\(([^)]+)\))?"
    r"(?:\s*[—–-]\s*(.*))?$"
)


@dataclass
class DigestItem:
    key: str
    ticker: str
    rest: str
    stamp: str = ""
    url: str = ""


@dataclass
class Row:
    stamp: str
    ticker: str
    side: str
    side_key: str
    quote: str
    url: str


@dataclass
class Summary:
    video_id: str
    path: Path
    title: str
    youtube: str
    digest_items: list[DigestItem] = field(default_factory=list)
    rows_zh: list[Row] = field(default_factory=list)
    rows_en: list[Row] = field(default_factory=list)


def _time_to_seconds(stamp: str) -> int | None:
    parts = stamp.strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    return None


def _yt(video_id: str, stamp: str = "") -> str:
    url = f"https://www.youtube.com/watch?v={video_id}"
    sec = _time_to_seconds(stamp) if stamp else None
    if sec is not None:
        url += f"&t={int(sec)}s"
    return url


def _side_key(raw: str) -> str:
    t = (raw or "").strip().lower()
    if "字幕缺口" in raw or "mute" in t or raw.strip() in {"—", "-", ""}:
        return "mute"
    if "觀望偏空" in raw or "Watch／偏空" in raw or "Watch/偏空" in raw:
        return "watch_short"
    if "觀望偏多" in raw or "Watch／偏多" in raw or "Watch/偏多" in raw:
        return "watch_long"
    if "trim" in t or "減倉" in raw or "實際操作" in raw:
        return "trim" if "實際" not in raw else "action"
    if "short" in t or "做空" in raw:
        return "short"
    if "long" in t or "做多" in raw:
        return "long"
    if "偏空" in raw:
        return "watch_short"
    if "偏多" in raw:
        return "watch_long"
    return "watch"


def _parse_digest(block: str, video_id: str) -> list[DigestItem]:
    items: list[DigestItem] = []
    for line in block.splitlines():
        m = _DIGEST.match(line.strip())
        if not m:
            continue
        head, stamp, url, rest = (
            m.group(1).strip(),
            m.group(2) or "",
            m.group(3) or "",
            (m.group(4) or "").strip(),
        )
        if head.startswith("今日總覽"):
            items.append(DigestItem("overview", head, rest, stamp, url))
            continue
        if "｜" in head:
            kind, ticker = head.split("｜", 1)
            ticker = ticker.strip()
            key = "action" if kind.startswith("實際") else _side_key(kind)
        else:
            kind, ticker, key = head, head, _side_key(head + rest)
        if stamp and not url:
            url = _yt(video_id, stamp)
        items.append(DigestItem(key, ticker, rest or kind, stamp, url))
    return items


def _parse_rows(block: str, video_id: str) -> list[Row]:
    rows: list[Row] = []
    for line in (block or "").splitlines():
        m = _ROW.match(line.strip())
        if not m:
            continue
        stamp = (m.group(1) or m.group(2) or "").strip()
        url = (m.group(3) or "").strip() or _yt(video_id, stamp)
        ticker, side, _src, quote = (g.strip() for g in m.group(4, 5, 6, 7))
        rows.append(
            Row(
                stamp=stamp,
                ticker=ticker,
                side=side,
                side_key=_side_key(side + ticker),
                quote=quote,
                url=url,
            )
        )
    return rows


def _section(text: str, heading: str) -> str:
    pat = rf"^##\s+{re.escape(heading)}\s*\n([\s\S]*?)(?=^##\s|\Z)"
    m = re.search(pat, text, flags=re.M)
    return m.group(1) if m else ""


def load_summary(path: Path) -> Summary:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else path.stem
    vid_m = re.search(r"youtube\.com/watch\?v=([\w-]{6,})", text)
    video_id = vid_m.group(1) if vid_m else path.stem
    digest = _section(text, "真正摘要（中文）") or _section(text, "重點摘要（中文）")
    zh = _section(text, "時間軸內容") or _section(text, "時間軸重點（中文）")
    en = _section(text, "Timeline content (EN)") or _section(text, "Timestamped notes (EN)") or _section(
        text, "Timestamped notes"
    )
    rows_zh = _parse_rows(zh, video_id) or _parse_rows(digest, video_id)
    return Summary(
        video_id=video_id,
        path=path,
        title=title,
        youtube=_yt(video_id),
        digest_items=_parse_digest(digest, video_id),
        rows_zh=rows_zh,
        rows_en=_parse_rows(en, video_id),
    )


def list_summaries() -> list[Summary]:
    if not OUT_DIR.is_dir():
        return []
    loaded = [load_summary(p) for p in OUT_DIR.glob("*.md")]
    loaded.sort(key=_episode_sort_key, reverse=True)
    return loaded


_MON = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _episode_sort_key(s: Summary) -> tuple:
    """Newest episode first — do not use file mtime (Streamlit Cloud clone is same time)."""
    title = s.title or s.path.stem
    m = re.search(
        r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{4})",
        title,
        re.I,
    )
    ep = re.search(r"\bEP\s*(\d+)", title, re.I)
    epn = int(ep.group(1)) if ep else 0
    if m:
        mon = _MON.get(m.group(2)[:3].lower(), 0)
        return (int(m.group(3)), mon, int(m.group(1)), epn)
    return (0, 0, 0, epn)


def _badge(key: str, label: str) -> str:
    bg, fg, _ = SIDE_COLORS.get(key, SIDE_COLORS["watch"])
    return (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
        f"background:{bg};color:{fg};font-size:0.78rem;font-weight:600;"
        f'">{html.escape(label)}</span>'
    )


def _card(inner: str, cls: str = "row-card") -> None:
    st.markdown(f'<div class="{cls}">{inner}</div>', unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(
        page_title="Martin Luk",
        page_icon="▶",
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
        .block-container { padding-top: 0.8rem; padding-bottom: 4rem; max-width: 42rem; }
        .digest-card, .row-card {
            border: 1px solid #2a303c; border-radius: 14px;
            padding: 0.85rem 0.95rem; margin-bottom: 0.55rem;
            background: #171a21;
        }
        .row-card a.t, .digest-card a.t {
            color: #7aa2ff; text-decoration: none; font-variant-numeric: tabular-nums;
            font-weight: 700; font-size: 1.05rem; min-height: 44px; display: inline-flex;
            align-items: center;
        }
        .quote { color: #e8eaed; margin-top: 0.3rem; line-height: 1.5; }
        .muted { color: #9aa3b2; font-size: 0.8rem; }
        .sec-h { font-size: 0.82rem; letter-spacing: 0.04em; color: #9aa3b2;
                 text-transform: uppercase; margin: 1rem 0 0.4rem; }
        div[data-testid="stLinkButton"] a { min-height: 44px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    summaries = list_summaries()
    if not summaries:
        st.title("Martin Luk")
        st.warning("未有 outputs/*.md。等每日 pipeline push 之後呢度會自動出現。")
        return

    by_id = {s.video_id: s for s in summaries}
    latest_id = summaries[0].video_id
    q = st.query_params.get("v")
    default_id = q if q in by_id else latest_id
    if not q:
        st.query_params["v"] = latest_id
        default_id = latest_id
    labels = {s.video_id: s.title for s in summaries}
    ids = [s.video_id for s in summaries]

    with st.sidebar:
        st.markdown("**Martin Luk**")
        st.caption("撳時間跳 YouTube 該秒")
        side_pick = st.radio(
            "場次",
            options=ids,
            index=ids.index(default_id),
            format_func=lambda vid: labels[vid],
            label_visibility="collapsed",
        )

    pick = st.selectbox(
        "場次",
        options=ids,
        index=ids.index(side_pick),
        format_func=lambda vid: labels[vid],
    )
    if pick != q:
        st.query_params["v"] = pick

    s = by_id[pick]
    st.title(s.title)
    top_l, top_r = st.columns([2, 1])
    with top_l:
        st.link_button("開 YouTube", s.youtube, use_container_width=True)
    with top_r:
        lang = st.radio("語言", ["中文", "EN"], horizontal=True, label_visibility="collapsed")

    overview = next((it for it in s.digest_items if it.key == "overview"), None)
    st.markdown('<div class="sec-h">真正摘要</div>', unsafe_allow_html=True)
    if overview and overview.rest:
        st.info(overview.rest)

    groups = [
        ("action", "實際操作"),
        ("long", "做多"),
        ("short", "做空"),
        ("watch_short", "觀望偏空"),
        ("watch_long", "觀望偏多"),
        ("trim", "減倉"),
        ("watch", "觀望"),
    ]
    for key, title in groups:
        chunk = [it for it in s.digest_items if it.key == key]
        if not chunk:
            continue
        st.markdown(f'<div class="sec-h">{html.escape(title)}</div>', unsafe_allow_html=True)
        _, _, fallback = SIDE_COLORS.get(key, SIDE_COLORS["watch"])
        for it in chunk:
            stamp_html = (
                f'<a class="t" href="{html.escape(it.url)}" target="_blank" rel="noreferrer">'
                f"{html.escape(it.stamp)}</a> "
                if it.url and it.stamp
                else ""
            )
            _card(
                f"{stamp_html}{_badge(key, fallback)} <b>{html.escape(it.ticker)}</b>"
                f'<div class="quote">{html.escape(it.rest)}</div>',
                "digest-card",
            )

    rows = s.rows_en if lang == "EN" and s.rows_en else (s.rows_zh or s.rows_en)
    st.markdown('<div class="sec-h">時間軸</div>', unsafe_allow_html=True)
    st.caption("撳時間 → YouTube 跳去該秒")
    show_mute = st.toggle("顯示字幕缺口", value=False)
    for row in rows:
        if not show_mute and row.side_key == "mute":
            continue
        badge = _badge(row.side_key, row.side)
        _card(
            f'<a class="t" href="{html.escape(row.url)}" target="_blank" rel="noreferrer">'
            f"{html.escape(row.stamp)}</a> "
            f"<b>{html.escape(row.ticker)}</b> {badge}"
            f'<div class="quote">{html.escape(row.quote)}</div>'
        )

    if not s.digest_items and not rows:
        st.markdown(s.path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
