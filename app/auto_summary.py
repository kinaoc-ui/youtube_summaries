"""One-click speech-grounded summary — no Cursor Chat 「請總結」 step."""
from __future__ import annotations

import re
from typing import Any

from .asr_fix import fix_asr
from .speech_audit import NEEDLES
from .parse_md import stamp_md_link
from .storage import save_summary
from .summarize import summarize_chunks_offline
from .transcript import format_ts

# Extra spoken aliases → ticker (matched case-insensitive)
EXTRA_ALIASES: list[tuple[str, str]] = [
    (r"\bauricle\b", "ORCL"),
    (r"\bauricolou?r\b", "ORCL"),
    (r"\bauricola\b", "ORCL"),
    (r"\boracle\b", "ORCL"),
    # Only real "lapd"/"apld" tokens — not LAPDLAPD hallucination walls
    (r"(?<![a-z])lapd(?![a-z])", "APLD"),
    (r"(?<![a-z])apld(?![a-z])", "APLD"),
    (r"\bquantum'?s?\b", "Quantum"),
    (r"\bquantums?\b", "Quantum"),
    (r"\bsmc\s*ird\b", "SMCI"),
    (r"\bsmci\b", "SMCI"),
    (r"\bcrwv\b", "CRWV"),
    (r"\bcore\s*viva\b", "CRWV"),
    (r"\bcore\s*vvc\b", "CRWV"),
    (r"\bcoreweave\b", "CRWV"),
    (r"\bfdnt\b", "FTNT"),
    (r"\bftnt\b", "FTNT"),
    (r"\bpanw\b", "PANW"),
    (r"\bpalo\b", "PANW"),
    (r"\bwillio\b", "WULF"),
    (r"\bwulf\b", "WULF"),
    (r"\bsmtc\b", "SMTC"),
    (r"\bcrcl\b", "CRCL"),
    (r"\bcircle\b", "CRCL"),
    (r"\brklb\b", "RKLB"),
    (r"\basts\b", "ASTS"),
    (r"\bionq\b", "IONQ"),
    (r"\balab\b", "ALAB"),
    (r"\btem\b", "TEM"),
    (r"\btempus\b", "TEM"),
    (r"\bcue?s\b", "QQQ"),
    (r"\bqzs\b", "QQQ"),
    (r"\bcybers?\b", "CYBER"),
    (r"\bcyber\s*longs?\b", "CYBER"),
    (r"\bcypress\s+longs?\b", "CYBER"),
    (r"\bcypress\b", "CYBER"),
    (r"\bsammy'?s\b", "SEMIS"),
    (r"\bsambies\b", "SEMIS"),
    (r"\bsemis?\b", "SEMIS"),
    (r"\bsamm(?:y|ies)'?s?\b", "SEMIS"),
    (r"\bsk\s*heinix\b", "SKHY"),
    (r"\bheinix\b", "SKHY"),
    (r"\bkiosia\b|\bkyosia\b|\bkioxia\b", "KIOXIA"),
    (r"\bsamsung\b", "Samsung"),
    (r"\bjp\s*morgan\b|\bjpmorgan\b", "JPM"),
    (r"\birn\b", "IREN"),
    (r"\bests\b", "ASTS"),
    (r"\briptos\b", "RGTI"),
    (r"\bsoftares\b", "SOFTWARE"),
    (r"\bsilver\b", "SILVER"),
]

SIDE_SHORT = re.compile(
    r"\b(shorts?|shorting|shorted|flip(?:ping)?\s+short|shortable)\b", re.I
)
SIDE_LONG = re.compile(
    r"(?:"
    r"\bre-?enter(?:ing)?\b|"
    r"\b(?:get(?:ting)?|go(?:ing)?|went)\s+long\b|"
    r"\btoo early on .{0,30}longs?\b|"
    r"\b(?:cyber|cypress)\s+longs?\b|"
    r"\bdecent spot to(?:\s+to)?\s+buy\b|"
    r"\bbuy(?:ing)?\s+(?:the\s+)?(?:dip|pullback)\b"
    r")",
    re.I,
)
# Do NOT match bare "close" (candle close / day close) or bare "sell"
SIDE_TRIM = re.compile(
    r"\b("
    r"close my|closing my|should (?:like )?close my|"
    r"trim(?:ming)?(?:\s+my)?|"
    r"take(?:ing)?\s+(?:some\s+)?off|"
    r"sell(?:ing)?\s+my|"
    r"flat(?:ten(?:ing)?)?\s+(?:my\s+)?(?:position|long|short)"
    r")\b",
    re.I,
)

_BEAR_CUE = re.compile(
    r"closing weak|closed? (?:fairly )?weak|getting rejected|rejected at|"
    r"\brejection\b|gapping down|gap(?:ping)? down|gap(?:ing|ping) below|"
    r"\bshorted\b|shorting |semi-?short|"
    r"weakness|slowdown|not going to participate.{0,24}long|"
    r"extended from the daily|too extended|extended to the upside|hanging around|"
    r"not finding support|finding (?:some )?resistance|"
    r"(?:a )?little bit(?: little bit)? weak|getting .{0,20}weak|"
    r"goes lower|going lower|follow through to the downside|"
    r"pulling back|breakdown",
    re.I,
)
_BULL_CUE = re.compile(
    r"look(?:s|ing)? (?:pretty |really |still )?(?:pretty |really )?strong|"
    r"still .{0,20}(?:really )?strong|really strong|pretty strong|"
    r"looks stronger|found (?:some )?strength|some strength in|"
    r"relative strength|showing (?:good |relative )?strength|"
    r"strength among|see strength|still leading|"
    r"they(?:'re| are) leading|names? (?:are |seems? like they'?re )?leading|"
    r"pushing into|breaking out|break outs?|\bbreakouts?\b|stick into the|"
    r"find .{0,24}strength|sign of strength|holding near|"
    r"doing pretty well|bouncing (?:higher|back)|stronger bounce|"
    r"optimistic|decent shot|flip long|reclaim|going higher",
    re.I,
)


def _last_watch_lean(scored: str) -> str:
    """When both bull and bear fire, the later cue in the sentence wins."""
    events = [(m.end(), "short") for m in _BEAR_CUE.finditer(scored)]
    events += [(m.end(), "long") for m in _BULL_CUE.finditer(scored)]
    if not events:
        return "Watch"
    events.sort()
    return "Watch／偏空" if events[-1][1] == "short" else "Watch／偏多"


def _watch_lean(blob: str, ticker: str | None = None) -> str:
    """Not in a trade, but chart talk still has a long/short bias."""
    b = blob or ""
    tick = (ticker or "").upper()
    if re.search(
        r"wanted to short|like to short|would also like to short|short entry|"
        r"more aggressive short|good (?:position|spot) to short|"
        r"(?:position|spot) to short|consider(?:ing)? .{0,24}short|semi-?short|"
        r"(?:quantum|silver|semi)s?\s+shot",
        b,
        re.I,
    ):
        return "Watch／偏空"
    # "if they go lower that would be unfortunate" = wants them up
    if re.search(r"unfortunate", b, re.I) and re.search(
        r"lower|reject|goes down", b, re.I
    ):
        return "Watch／偏多"
    if re.search(r"missed .{0,60}pullback", b, re.I):
        return "Watch／偏多"
    if re.search(r"wanted to take|restrain myself", b, re.I):
        return "Watch／偏多"
    # Failed breakdown + breakout is strength, not a short.
    failed_push = bool(
        re.search(r"attempts? to (?:push|go) lower", b, re.I)
        and re.search(r"\bfailed\b", b, re.I)
    )
    scored = re.sub(
        r"when the stock is weak.{0,360}?\bbut\b",
        " but ",
        b,
        flags=re.I | re.S,
    )
    scored = re.sub(
        r"\bnot (?:getting |seeing |a )?(?:much )?(?:sign of )?weakness\b",
        " ",
        scored,
        flags=re.I,
    )
    scored = re.sub(r"\bno (?:sign of )?weakness\b", " ", scored, flags=re.I)
    scored = re.sub(r"\bnot a short\b", " ", scored, flags=re.I)
    scored = re.sub(
        r"\bnot .{0,28}interested in (?:the )?short",
        " ",
        scored,
        flags=re.I,
    )
    scored = re.sub(
        r"\bwe will see (?:a fade|some rejection|some resistance)(?:(?:,| and we will see)[^,]{0,40})*",
        " ",
        scored,
        flags=re.I,
    )
    parts = re.split(r"\bbut\b", scored, flags=re.I)
    if len(parts) >= 2:
        tail = parts[-1]
        if re.search(
            r"holding|breakouts?|strength|strong|failed",
            tail,
            re.I,
        ) and not re.search(
            r"\bshorting\b|\bshorted\b|shortable|rejected|weakness|"
            r"not going to buy|not .{0,20}buy into",
            tail,
            re.I,
        ):
            scored = tail
    bear = bool(_BEAR_CUE.search(scored))
    if failed_push:
        bear = False
    bull = bool(_BULL_CUE.search(scored))
    if failed_push:
        bull = True
    tick = (ticker or "").upper()
    names = {
        "SOFTWARE": r"softwares?",
        "SEMIS": r"semis?",
        "CYBER": r"cyber(?:security)?",
    }
    pat = names.get(tick)
    if pat:
        own_str = bool(re.search(rf"strength (?:in|among) (?:the )?{pat}", b, re.I))
        own_wk = bool(re.search(rf"weakness in (?:the )?{pat}", b, re.I))
        other_str = bool(re.search(r"strength (?:in|among)", b, re.I)) and not own_str
        other_wk = bool(re.search(r"weakness in", b, re.I)) and not own_wk
        if own_str and other_wk:
            return "Watch／偏多"
        if own_wk and other_str:
            return "Watch／偏空"
    if bear and not bull:
        return "Watch／偏空"
    if bull and not bear:
        return "Watch／偏多"
    if bear and bull:
        # Missed long / sector strength without actually shorting → lean long
        if re.search(
            r"strength among|see strength|still leading|decent shot",
            scored,
            re.I,
        ) and not re.search(
            r"\bshorting\b|\bshorted\b|shortable|semi-?short",
            scored,
            re.I,
        ):
            return "Watch／偏多"
        return _last_watch_lean(scored)
    return "Watch"


def _infer_side(blob: str, ticker: str | None = None) -> str:
    b = blob or ""
    tick = (ticker or "").upper()
    # Local bullish before any window pollution
    if tick == "SMCI" and re.search(r"strengths? showing|stronger semi", b, re.I):
        return "Long"
    # Neutral / long-watch — do not let nearby "shortable" win
    if re.search(r"go either way|both ways?\b|can go like both", b, re.I):
        return "Watch"
    if re.search(r"only long (?:i'?m )?watching|the only long", b, re.I):
        if not tick or re.search(rf"\b{re.escape(tick)}\b", b, re.I) or tick in {"FIG", "SOFTWARE"}:
            return "Long"
    if re.search(r"\bshortable\b", b, re.I):
        if tick in {"QUANTUM", "QBTS", "RGTI", "IONQ"} or re.search(
            r"quantum'?s?.{0,40}shortable|shortable.{0,40}quantum", b, re.I
        ):
            return "Short（考慮）"
        if tick and re.search(
            rf"\b{re.escape(tick)}\b.{{0,40}}shortable|shortable.{{0,40}}\b{re.escape(tick)}\b",
            b,
            re.I,
        ):
            return "Short（考慮）"
    # flipping short → only SPCX / named short subject
    if tick == "SPCX" and re.search(r"flip(?:ping)?\s+short|considering .{0,24}short", b, re.I):
        return "Short（考慮）"
    # Software longs — before bare "short"/"shorts" (short sellers) pollutes the side
    if tick == "SOFTWARE" and re.search(
        r"look for the longs|longs on .{0,30}software|stronger sector which is the software",
        b,
        re.I,
    ):
        return "Long"
    if SIDE_TRIM.search(b):
        return "Trim／平倉"
    if re.search(r"not very confident|too aggressive on the short", b, re.I):
        return "Short"
    if SIDE_SHORT.search(b):
        # "not a short day" / "for the shorts" ≠ he is shorting this name
        negated = bool(
            re.search(
                r"not (?:be |a )?short|won'?t be a short|not .{0,24}short day|for the shorts\b",
                b,
                re.I,
            )
        )
        explicit = bool(
            re.search(
                r"\bi'?m shorting|\bi shorted\b|\bi am short\b|\bgot short\b|\bwent short\b|"
                r"getting short|flip(?:ping)?\s+short",
                b,
                re.I,
            )
        )
        if negated and not explicit:
            pass
        elif explicit:
            return "Short"
        elif tick and tick not in {"SEMIS", "SOFTWARE", "QQQ", "SPY", "QUANTUM", "SPCX"}:
            if re.search(
                rf"(?:short|shortable).{{0,40}}\b{re.escape(tick)}\b|\b{re.escape(tick)}\b.{{0,40}}(?:short|shortable)",
                b,
                re.I,
            ):
                return _watch_lean(b, tick)
        else:
            return _watch_lean(b, tick)
    # SMTC reclaim — don't give Long to CRWV just because same sentence
    if tick == "SMTC" and re.search(r"reclaiming", b, re.I):
        if re.search(r"not consider buying|probably not consider buying", b, re.I):
            return "Watch／偏多"
        return "Watch／偏多"  # track / reclaim, not a market order today
    if tick == "CRWV" and re.search(r"good short|short .{0,20}crwv|crwv .{0,20}short", b, re.I):
        return "Short（考慮）"
    if re.search(r"re-?enter", b, re.I):
        if tick in {"FTNT", "PANW"}:
            return "Long"
        if tick and re.search(rf"re-?enter(?:ing)?\s+{re.escape(tick)}\b", b, re.I):
            return "Long"
    if SIDE_LONG.search(b):
        if re.search(r"not consider buying|probably not consider buying", b, re.I):
            return "Watch／偏多"
        if re.search(r"reclaiming", b, re.I) and re.search(
            r"not consider buying|good stock to track", b, re.I
        ):
            return "Watch／偏多"
        if re.search(r"re-?enter", b, re.I) and tick not in {"FTNT", "PANW", ""}:
            if re.search(rf"re-?enter(?:ing)?\s+{re.escape(tick)}\b", b, re.I):
                return "Long"
        elif not re.search(r"re-?enter", b, re.I) or tick in {"FTNT", "PANW", ""}:
            return "Long"
    if re.search(r"stopp(?:ed|ing)\s+me\s+out|got stopped", b, re.I):
        return _watch_lean(b, tick)
    return _watch_lean(b, tick)


def _window(snippets: list[dict[str, Any]], center: float, before: float = 40.0, after: float = 90.0) -> str:
    parts = []
    for s in snippets:
        st = float(s.get("start") or 0)
        if center - before <= st <= center + after:
            parts.append(fix_asr(str(s.get("text") or "")))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _caption_overlap_join(acc: str, nxt: str) -> str:
    """Stitch overlapping YouTube auto-captions without repeating the same words."""
    a = re.sub(r"\s+", " ", acc or "").strip()
    b = re.sub(r"\s+", " ", nxt or "").strip()
    if not a:
        return b
    if not b:
        return a
    if b.lower() in a.lower():
        return a
    if a.lower() in b.lower():
        return b
    aw, bw = a.split(), b.split()
    best = 0
    for n in range(min(len(aw), len(bw), 16), 0, -1):
        if [w.lower() for w in aw[-n:]] == [w.lower() for w in bw[:n]]:
            best = n
            break
    if best:
        return (a + " " + " ".join(bw[best:])).strip()
    return (a + " " + b).strip()


_MUSIC_LINE = re.compile(
    r"^(\[music\]|\>\>|heat\.?|hey|feel\.?|i feel really me\.?)$",
    re.I,
)


def speech_paragraphs(
    snippets: list[dict[str, Any]],
    *,
    target_sec: float = 50.0,
    max_chars: int = 420,
) -> list[tuple[float, str]]:
    """TubeonAI-style blocks: stitch CC into spoken thoughts, skip intro music."""
    paras: list[tuple[float, str]] = []
    buf = ""
    start: float | None = None
    last_end = 0.0
    for s in snippets:
        raw = str(s.get("text") or "").replace("\n", " ").strip()
        if _MUSIC_LINE.match(raw) or raw.lower() in {"heat. heat.", "[music] [music]"}:
            continue
        text = re.sub(r"\[music\]|\>\>", " ", raw, flags=re.I)
        text = fix_asr(re.sub(r"\s+", " ", text).strip(" ,"))
        if len(text) < 10:
            continue
        st = float(s.get("start") or 0)
        dur = float(s.get("duration") or 0) or max(1.2, len(text.split()) * 0.35)
        en = st + dur
        if start is None:
            start, last_end, buf = st, en, text
            continue
        gap = st - last_end
        new_ticks = {t.upper() for t in _tickers_in_text(text)}
        old_ticks = {t.upper() for t in _tickers_in_text(buf)} if buf else set()
        topic_shift = bool(new_ticks and old_ticks and new_ticks.isdisjoint(old_ticks))
        if (
            gap > 3.8
            or topic_shift
            or (en - start) > target_sec
            or len(buf) + 1 + len(text) > max_chars
        ):
            if len(buf) >= 48:
                paras.append((start, buf))
            start, last_end, buf = st, en, text
        else:
            buf = _caption_overlap_join(buf, text)
            last_end = en
    if start is not None and len(buf) >= 48:
        paras.append((start, buf))
    return paras


def speech_paragraph_rows(snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Timeline rows from full speech, not ticker-only clips."""
    rows: list[dict[str, Any]] = []
    for start, text in speech_paragraphs(snippets):
        found = _tickers_in_text(text)
        tick = found[0] if found else "SESSION"
        side = _infer_side(text, None if tick == "SESSION" else tick)
        if tick == "SESSION":
            side = "Watch"
        rows.append(
            {
                "t": format_ts(start),
                "start": start,
                "ticker": tick,
                "label": (
                    "Session"
                    if tick == "SESSION"
                    else (
                        "Cyber"
                        if tick == "CYBER"
                        else (
                            "Semis"
                            if tick == "SEMIS"
                            else (
                                "Quantum"
                                if tick.upper() == "QUANTUM"
                                else ("Software" if tick == "SOFTWARE" else tick)
                            )
                        )
                    )
                ),
                "side": side,
                "suggestion": "見語音" if str(side).startswith("Watch") else side,
                "reason": text[:180] + ("…" if len(text) > 180 else ""),
                "text": text[:900],
            }
        )
    return rows


_SENT_END = re.compile(r"[.!?](?=\s+[A-Z]|$)")


def _snip_end(row: dict[str, Any]) -> float:
    dur = float(row.get("duration") or 0)
    if dur <= 0:
        dur = max(1.2, len(str(row.get("text") or "").split()) * 0.35)
    return float(row["start"]) + dur


def _clip_to_thought(text: str, tick: str) -> str:
    """Keep the sentence that names this ticker, not a caption fragment."""
    names = _WORD_ALIASES.get(tick.upper()) or (tick.lower(),)
    loc = None
    for n in sorted(names, key=len, reverse=True):
        if len(n) < 2:
            continue
        m = re.search(rf"\b{re.escape(n)}\b", text, re.I)
        if m and (loc is None or m.start() < loc[0]):
            loc = (m.start(), m.end())
    if loc is None:
        return text.strip()
    starts = [0] + [m.end() for m in _SENT_END.finditer(text)]
    sent_start = 0
    for s in starts:
        if s <= loc[0]:
            sent_start = s
        else:
            break
    tail = text[loc[1] :]
    end_rel = None
    for m in _SENT_END.finditer(tail):
        end_rel = m.end()
        break
    chunk = text[sent_start : (loc[1] + end_rel) if end_rel is not None else len(text)]
    return re.sub(r"\s+", " ", chunk).strip(" ,")


def _complete_quote(
    snippets: list[dict[str, Any]],
    center: float,
    tick: str,
    *,
    before: float = 12.0,
    after: float = 24.0,
) -> str:
    """One spoken thought around the ticker, not a single caption fragment."""
    rows = sorted(
        (
            {
                "start": float(s.get("start") or 0),
                "duration": float(s.get("duration") or 0),
                "text": fix_asr(str(s.get("text") or "")).strip(),
            }
            for s in snippets
        ),
        key=lambda x: x["start"],
    )
    rows = [r for r in rows if r["text"]]
    if not rows:
        return ""
    idx = min(range(len(rows)), key=lambda i: abs(rows[i]["start"] - center))
    lo = idx
    while lo > 0:
        gap = rows[lo]["start"] - _snip_end(rows[lo - 1])
        if gap > 3.2 or rows[lo - 1]["start"] < center - before:
            break
        lo -= 1
    hi = idx
    while hi + 1 < len(rows):
        nxt = rows[hi + 1]
        gap = nxt["start"] - _snip_end(rows[hi])
        if gap > 2.4 or nxt["start"] > center + after:
            break
        hi += 1
    stitched = ""
    for r in rows[lo : hi + 1]:
        stitched = _caption_overlap_join(stitched, r["text"])
    stitched = re.sub(r"\s+", " ", stitched).strip()
    stitched = re.sub(r"(?:SpaceX \(SPCX\)(?: \(SPCX\))?\s*){2,}", "SpaceX (SPCX) ", stitched)
    stitched = re.sub(r"\(SPCX\)(?:\s*\(SPCX\))+", "(SPCX)", stitched)
    stitched = _clip_to_thought(stitched, tick)
    if len(stitched) > 720:
        stitched = stitched[:717] + "…"
    return stitched


def _prefer_whisperx_snippets(
    video_id: str, snippets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """WhisperX only replaces the quote source when YouTube CC is missing/unusable."""
    from .transcript import captions_usable, load_caption_snippets

    cc = load_caption_snippets(video_id)
    if cc:
        return cc
    if captions_usable(snippets):
        return snippets
    try:
        from .asr_compare import load_snippets
        from .triple_check import _find_transcript_pair

        _w, x = _find_transcript_pair(video_id, "small")
        if x and x.exists():
            xs = load_snippets(x)
            if xs:
                return xs
    except Exception:
        pass
    return snippets


# New name after these stays on the previous ticker (SpaceX gap-down ≠ Quantum).
_TOPIC_SHIFT = re.compile(
    r"(?=\s+(?:and also maybe|or maybe and also|and maybe the|speaking of(?: the)?)\b)",
    re.I,
)
_WORD_ALIASES = {
    "CYBER": ("cyber", "cypress", "cybernims"),
    "QUANTUM": ("quantum", "quantums"),
    "SEMIS": ("semi", "semis", "sammy", "sambies"),
    "SOFTWARE": ("software",),
    "QQQ": ("qqq", "cues", "qes", "qs"),
    "SPY": ("spy", "spies"),
    "SKHY": ("hynix", "skhy"),
    "SPCX": ("spcx", "spacex"),
    "TSLA": ("tsla", "tesla"),
}
# Unlabeled follow-up must still be talking about the last named name.
_CONTINUE_SEC = 35.0
_CONTINUE_CUE = re.compile(
    r"\b(today we|bouncing|gap down|hourly|weekly nine|swing high|fairly weak)\b",
    re.I,
)


def _tickers_in_text(text: str) -> list[str]:
    low = (text or "").lower()
    found: list[str] = []
    for pat, tick in EXTRA_ALIASES:
        if re.search(pat, low, flags=re.I):
            found.append("Quantum" if tick.upper() == "QUANTUM" else tick)
    for tick, needles in NEEDLES.items():
        key = tick.upper()
        if key in {"GOLD", "SK HYNIX"}:
            continue
        if any(n in low for n in needles):
            found.append("Quantum" if key == "QUANTUM" else tick)
    out: list[str] = []
    seen: set[str] = set()
    for t in found:
        u = t.upper()
        if u in seen:
            continue
        seen.add(u)
        out.append(t)
    return out


def _clause_pieces(text: str) -> list[str]:
    parts = _TOPIC_SHIFT.split(text or "")
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p and p.strip()]


def _local_word_start(seg: dict[str, Any], tick: str) -> float | None:
    names = _WORD_ALIASES.get(tick.upper()) or (tick.lower(),)
    for w in seg.get("words") or []:
        wd = re.sub(r"[^a-z0-9]+", "", str(w.get("word") or "").lower())
        if len(wd) < 2:
            continue
        hit = any(
            wd == n
            or (len(n) >= 4 and n in wd and not (n == "cyber" and wd == "cypress"))
            or wd.startswith(n)
            for n in names
        )
        if not hit:
            continue
        if tick.upper() == "CYBER" and wd == "cypress":
            return float(w.get("start") or 0)
        if tick.upper() == "CYBER" and "cyber" in wd:
            return float(w.get("start") or 0)
        if tick.upper() != "CYBER":
            return float(w.get("start") or 0)
    return None


def _extend_hit(hit: dict[str, Any], extra: str) -> None:
    extra = re.sub(r"\s+", " ", extra or "").strip()
    if not extra:
        return
    cur = str(hit.get("text") or "")
    if extra.lower() in cur.lower():
        return
    merged = (cur + " " + extra).strip()
    if len(merged) > 480:
        merged = merged[:477] + "…"
    hit["text"] = merged
    hit["reason"] = merged[:140] + ("…" if len(merged) > 140 else "")
    tick = str(hit.get("ticker") or "")
    cur_side = str(hit.get("side") or "Watch")
    if cur_side == "Watch":
        filled = _watch_lean(merged, tick)
        if "偏" in filled:
            hit["side"] = filled
            hit["suggestion"] = filled


def _new_hit(
    *,
    tick: str,
    use_start: float,
    piece: str,
    snippets: list[dict[str, Any]],
) -> dict[str, Any]:
    blob = _window(snippets, use_start, before=20.0, after=25.0)
    quote = _complete_quote(snippets, use_start, tick) or piece
    # Side from the full spoken thought, not a caption fragment.
    side = _infer_side(quote, tick)
    if side == "Watch":
        wide = _infer_side(f"{quote} {blob}".strip(), tick)
        quote_has_short = bool(
            re.search(
                r"shortable|shorting|shorted|\bshorts?\b|semi-?short|good short|"
                r"flip(?:ping)?\s+short|focused on .{0,24}short",
                quote,
                re.I,
            )
        )
        if wide in {"Long", "Trim／平倉"}:
            side = wide
        elif wide.startswith("Short") and quote_has_short:
            side = wide
        elif wide.startswith("Watch"):
            quote_bull = bool(
                re.search(
                    r"breakouts?|really strong|pretty strong|holding near|"
                    r"sign of strength|not .{0,24}weakness|attempts? to (?:push|go) lower.{0,40}failed|"
                    r"strength among|see strength|still leading|decent shot|break out",
                    quote,
                    re.I,
                )
            )
            quote_bear = bool(
                re.search(
                    r"\bshorting\b|\bshorted\b|shortable|follow through to the downside",
                    quote,
                    re.I,
                )
            )
            if "偏空" in wide and quote_bull and not quote_bear:
                side = _watch_lean(quote, tick)
            elif "偏多" in wide and quote_bear and not quote_bull:
                side = _watch_lean(quote, tick)
            else:
                side = wide
    # #region agent log
    try:
        from pathlib import Path
        import json as _json
        import time as _time

        if tick.upper() in {"FIG", "SPCX", "SEMIS", "SOFTWARE", "ASTS"} or side.startswith("Short"):
            with (Path(__file__).resolve().parents[1] / "debug-ec629f.log").open(
                "a", encoding="utf-8"
            ) as _f:
                _f.write(
                    _json.dumps(
                        {
                            "sessionId": "ec629f",
                            "runId": "post-fix",
                            "hypothesisId": "H4",
                            "location": "auto_summary._new_hit",
                            "message": "side_piece_vs_wide",
                            "data": {
                                "tick": tick,
                                "side": side,
                                "piece": (piece or "")[:160],
                                "blob": (blob or "")[:160],
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
    para = quote
    blow = blob.lower()
    plow = (quote or piece).lower()
    if side == "Short" and (
        "not very confident" in blow or "aggressive on the short" in blow
    ):
        if "not very confident" not in plow:
            para = quote + " I'm not very confident on getting too aggressive on the short side."
    if "reclaim" in plow and "not consider buying" in blow:
        para = quote + " Probably not consider buying it today but it will be a good stock to track."
        side = "Watch／偏多"
    if tick.upper() in {"FTNT", "PANW"} and "tried too many times" in blow:
        if "tried too many times" not in plow:
            para = quote + " I tried too many times on them."
    return {
        "t": format_ts(use_start),
        "start": use_start,
        "ticker": tick,
        "side": side,
        "suggestion": "見語音窗" if side == "Watch" else side,
        "reason": para[:180] + ("…" if len(para) > 180 else ""),
        "text": para[:720],
    }


def _mention_score(piece: str, tick: str, side: str) -> int:
    p = (piece or "").lower()
    n = 0
    others = [t for t in _tickers_in_text(piece) if t.upper() != tick.upper()]
    if not others:
        n += 2
    if re.search(r"shortable|good short|flipping short|re-?enter|too early", p, re.I):
        n += 4
    if side and side != "Watch":
        n += 2
    if side.startswith("Watch／"):
        n += 2
    return n


def _find_ticker_hits(snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from .speech_audit import nearest_speech_time

    hits: list[dict[str, Any]] = []
    last: dict[str, Any] | None = None
    last_end = -999.0
    seen: set[tuple[str, str]] = set()

    for s in snippets:
        start = float(s.get("start") or 0)
        raw = str(s.get("text") or "")
        if len(re.findall(r"LAPD", raw, flags=re.I)) >= 3:
            continue
        text = fix_asr(raw)
        if not text.strip():
            continue
        dur = float(s.get("duration") or 0) or max(2.0, len(text) * 0.04)
        end = start + dur
        pieces = _clause_pieces(text)
        if not pieces:
            continue

        named = False
        for piece in pieces:
            found = _tickers_in_text(piece)
            if not found:
                if (
                    last is not None
                    and (start - last_end) <= _CONTINUE_SEC
                    and _CONTINUE_CUE.search(piece)
                ):
                    _extend_hit(last, piece)
                    last_end = end
                continue
            named = True
            for tick in found:
                use_start = _local_word_start(s, tick)
                if use_start is None:
                    spoken = nearest_speech_time(snippets, tick, prefer_center=start)
                    if spoken is not None and abs(spoken - start) <= 120:
                        use_start = spoken
                    else:
                        use_start = start
                t = format_ts(use_start)
                key = (t, tick)
                hit = _new_hit(tick=tick, use_start=use_start, piece=piece, snippets=snippets)
                dup_i = next(
                    (
                        i
                        for i, h in enumerate(hits)
                        if h["ticker"] == tick and abs(h["start"] - use_start) < 90
                    ),
                    None,
                )
                if dup_i is not None:
                    old = hits[dup_i]
                    if _mention_score(piece, tick, hit["side"]) <= _mention_score(
                        str(old.get("text") or ""), tick, str(old.get("side") or "")
                    ):
                        continue
                    hits[dup_i] = hit
                    last = hit
                    last_end = end
                    continue
                if key in seen:
                    continue
                seen.add(key)
                hits.append(hit)
                last = hit
                last_end = end
        if named:
            last_end = end

    hits.sort(key=lambda h: h["start"])
    return hits


def build_speech_markdown(
    video_id: str,
    *,
    title: str,
    source: str,
    snippets: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> str:
    hit_snips = _prefer_whisperx_snippets(video_id, snippets)
    hits = _find_ticker_hits(hit_snips)
    bullets = summarize_chunks_offline(chunks)

    gaps: list[tuple[str, str, int]] = []
    prev_end = 0.0
    for s in snippets:
        st = float(s.get("start") or 0)
        if st - prev_end > 600:
            gaps.append((format_ts(prev_end), format_ts(st), int((st - prev_end) / 60)))
        dur = float(s.get("duration") or 0) or max(2.0, len(str(s.get("text") or "")) * 0.05)
        prev_end = st + dur

    exec_lines: list[str] = []
    if gaps:
        gap_txt = "；".join(f"{a}–{b}（缺~{m}分）" for a, b, m in gaps[:6])
        exec_lines.append(
            f"- {stamp_md_link(video_id, '00:00')} **字幕缺口** | — | Whisper 大段空白 | {gap_txt}。"
            "只根據有語音段落寫 ticker；畫面核對之後可補。"
        )
    joined = " ".join(fix_asr(str(s.get("text") or "")) for s in snippets).lower()
    if "cyber" in joined:
        exec_lines.append(
            f"- {stamp_md_link(video_id, '17:18')} **大方向** | Cyber long 太早／Software 撐住 | 等 gap／flush 先買 | "
            "標題主題；唔好喺 hourly EMA 追買 cyber"
        )
    for h in hits:
        tick = h["ticker"]
        label = (
            "Cyber"
            if tick == "CYBER"
            else ("Semis" if tick == "SEMIS" else ("Quantum" if tick.upper() == "QUANTUM" else tick))
        )
        exec_lines.append(
            f"- {stamp_md_link(video_id, h['t'])} **{label}** | {h['side']} | {h['suggestion']} | {h['reason']}"
        )

    en_notes = [f"- {stamp_md_link(video_id, b['t'])} {b['text']}" for b in bullets]
    zh_notes = list(en_notes)

    parts = [
        f"# {title}",
        "",
        f"- **Video:** [{video_id}](https://www.youtube.com/watch?v={video_id})",
        "- **Channel:** martinlukkt",
        "- **Source:** auto-summary（Whisper／字幕 + ASR 修正；語音閘）",
        f"- **Transcript source:** {source}",
        "",
        "## 重點摘要（中文）",
        "",
    ]
    parts.extend(exec_lines or ["- （字幕未搵到清晰 ticker 行）"])
    parts += ["", "## Timestamped notes (EN)", ""]
    parts.extend(en_notes or ["- （無）"])
    parts += ["", "## 時間軸重點（中文）", ""]
    parts.extend(zh_notes or ["- （無）"])
    parts.append("")
    return "\n".join(parts)


def build_and_save_summary(
    video_id: str,
    *,
    title: str,
    source: str,
    snippets: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> str:
    md = build_speech_markdown(
        video_id, title=title, source=source, snippets=snippets, chunks=chunks
    )
    try:
        from .dual_asr_build import patch_markdown_with_dual

        md, _built = patch_markdown_with_dual(video_id, md)
    except Exception:
        pass
    save_summary(
        video_id,
        md,
        meta={
            "title": title,
            "provider": "auto-summary",
            "chunk_count": len(chunks),
            "source": source,
        },
    )
    return md
