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
    "long": ("#14532d", "#86efac", "做多／long"),
    "short": ("#7f1d1d", "#fca5a5", "做空／short"),
    "watch_short": ("#7f1d1d", "#fca5a5", "觀望偏空／lean short"),
    "watch_long": ("#14532d", "#86efac", "觀望偏多／lean long"),
    "watch": ("#1e3a5f", "#93c5fd", "觀望／watch"),
    "trim": ("#713f12", "#fde047", "減倉／trim"),
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


def _split_en_zh(quote: str) -> tuple[str, str]:
    q = (quote or "").strip()
    if "‖" not in q:
        zh = len(re.findall(r"[\u4e00-\u9fff]", q))
        en = len(re.findall(r"[A-Za-z]", q))
        return (q, "") if en >= zh else ("", q)
    a, b = (p.strip() for p in q.split("‖", 1))
    zh_a = len(re.findall(r"[\u4e00-\u9fff]", a))
    zh_b = len(re.findall(r"[\u4e00-\u9fff]", b))
    if zh_b > zh_a:
        return a, b
    if zh_a > zh_b:
        return b, a
    return a, b


def _side_key(raw: str) -> str:
    t = (raw or "").strip().lower()
    if "字幕缺口" in raw or "mute" in t or raw.strip() in {"—", "-", ""}:
        return "mute"
    if "觀望偏空" in raw or "Watch／偏空" in raw or "Watch/偏空" in raw or "lean short" in t:
        return "watch_short"
    if "觀望偏多" in raw or "Watch／偏多" in raw or "Watch/偏多" in raw or "lean long" in t:
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
                side_key=_side_key(side + " " + ticker),
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


def _qp_one(name: str) -> str:
    v = st.query_params.get(name)
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return str(v[0] or "")
    return str(v)


def _tl_anchor(stamp: str, ticker: str) -> str:
    s = re.sub(r"[^0-9]+", "-", stamp or "").strip("-")
    t = re.sub(r"[^A-Za-z0-9]+", "", ticker or "")
    return f"tl-{s}-{t}"


def _scroll_app_top() -> None:
    """After a digest tap, Streamlit often keeps the old scroll offset."""
    import streamlit.components.v1 as components

    components.html(
        """<!DOCTYPE html><html><body><script>
(function () {
  const w = window.parent || window;
  const doc = w.document;
  const go = () => {
    const el = doc.getElementById("jump-quote");
    if (el) {
      el.scrollIntoView({behavior: "smooth", block: "start"});
      return;
    }
    const main = doc.querySelector("section.main")
      || doc.querySelector('[data-testid="stAppViewContainer"]');
    if (main && main.scrollTo) main.scrollTo({top: 0, behavior: "smooth"});
    else w.scrollTo(0, 0);
  };
  go();
  setTimeout(go, 200);
  setTimeout(go, 600);
})();
</script></body></html>""",
        height=1,
        scrolling=False,
    )


def _badge(key: str, label: str) -> str:
    bg, fg, _ = SIDE_COLORS.get(key, SIDE_COLORS["watch"])
    return (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
        f"background:{bg};color:{fg};font-size:0.78rem;font-weight:600;"
        f'">{html.escape(label)}</span>'
    )


def _card(inner: str, cls: str = "row-card", anchor: str = "") -> None:
    aid = f' id="{html.escape(anchor, quote=True)}"' if anchor else ""
    dtl = f' data-tl="{html.escape(anchor, quote=True)}"' if anchor else ""
    st.markdown(f'<div class="{cls}"{aid}{dtl}>{inner}</div>', unsafe_allow_html=True)


def _put_timeline_row(
    row: Row,
    *,
    en_by: dict[tuple[str, str], str],
    highlight: bool = False,
    with_anchor: bool = True,
) -> None:
    tl = _tl_anchor(row.stamp, row.ticker)
    badge = _badge(row.side_key, row.side)
    en_q, zh_q = _split_en_zh(row.quote)
    if not en_q:
        en_q = en_by.get((row.stamp, row.ticker), "")
    quote_html = ""
    if en_q:
        quote_html += f'<div class="quote">{html.escape(en_q)}</div>'
    if zh_q and zh_q != en_q:
        quote_html += f'<div class="muted">{html.escape(zh_q)}</div>'
    cls = "row-card jump-hit" if highlight else "row-card"
    _card(
        f'<a class="t" href="{html.escape(row.url)}" target="_blank" rel="noreferrer">'
        f"{html.escape(row.stamp)}</a> "
        f"<b>{html.escape(row.ticker)}</b> {badge}"
        f"{quote_html}",
        cls,
        tl if with_anchor else "",
    )


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
            scroll-margin-top: 12px;
        }
        .row-card.jump-hit {
            outline: 2px solid #7aa2ff;
            outline-offset: 2px;
        }
        h3[id^="tl-"] {
            height: 0 !important; margin: 0 !important; padding: 0 !important;
            overflow: hidden !important; font-size: 0 !important; line-height: 0 !important;
        }
        #jump-quote { scroll-margin-top: 8px; }
        div[data-testid="stHeading"]:has(h3[id^="tl-"]) {
            height: 0; margin: 0; padding: 0; overflow: hidden;
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
    q = _qp_one("v")
    jump = _qp_one("tl")
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
        if "tl" in st.query_params:
            del st.query_params["tl"]
        jump = ""

    s = by_id[pick]
    en_by = {(r.stamp, r.ticker): r.quote for r in s.rows_en}
    rows = s.rows_zh or s.rows_en
    jumped = next((r for r in rows if _tl_anchor(r.stamp, r.ticker) == jump), None) if jump else None
    st.title(s.title)
    top_l, top_r = st.columns([2, 1])
    with top_l:
        st.link_button("開 YouTube", s.youtube, use_container_width=True)
    with top_r:
        st.caption("先英文原文，再中文")

    overview = next((it for it in s.digest_items if it.key == "overview"), None)
    st.markdown('<div class="sec-h">真正摘要</div>', unsafe_allow_html=True)
    st.caption("撳摘要時間，即刻喺上面出時間軸該行原文；時間軸時間戳先跳 YouTube")
    if overview and overview.rest:
        st.info(overview.rest)
    if jumped:
        st.markdown(
            '<div id="jump-quote" class="sec-h">時間軸該行</div>',
            unsafe_allow_html=True,
        )
        _put_timeline_row(jumped, en_by=en_by, highlight=True, with_anchor=False)

    groups = [
        ("action", "實際操作"),
        ("long", "做多／long"),
        ("short", "做空／short"),
        ("watch_short", "觀望偏空／lean short"),
        ("watch_long", "觀望偏多／lean long"),
        ("trim", "減倉／trim"),
        ("watch", "觀望／watch"),
    ]
    for key, title in groups:
        chunk = [it for it in s.digest_items if it.key == key]
        if not chunk:
            continue
        st.markdown(f'<div class="sec-h">{html.escape(title)}</div>', unsafe_allow_html=True)
        _, _, fallback = SIDE_COLORS.get(key, SIDE_COLORS["watch"])
        for i, it in enumerate(chunk):
            tl = _tl_anchor(it.stamp, it.ticker)
            if it.stamp:
                if st.button(
                    f"{it.stamp}  {it.ticker}",
                    key=f"jump-{s.video_id}-{key}-{i}-{tl}",
                    use_container_width=True,
                ):
                    st.query_params["v"] = s.video_id
                    st.query_params["tl"] = tl
                    st.rerun()
            _card(
                f"{_badge(key, fallback)} <b>{html.escape(it.ticker)}</b>"
                f'<div class="quote">{html.escape(it.rest)}</div>',
                "digest-card",
            )

    st.markdown('<div class="sec-h">時間軸（英→中）</div>', unsafe_allow_html=True)
    st.caption("撳時間 → YouTube 跳去該秒")
    show_mute = st.toggle("顯示字幕缺口", value=False)
    for row in rows:
        is_jump = bool(jump) and _tl_anchor(row.stamp, row.ticker) == jump
        if not show_mute and row.side_key == "mute" and not is_jump:
            continue
        _put_timeline_row(row, en_by=en_by, highlight=is_jump, with_anchor=True)

    if jump:
        _scroll_app_top()
        if jumped is None:
            st.caption("搵唔到對應時間軸行")

    if not s.digest_items and not rows:
        st.markdown(s.path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
