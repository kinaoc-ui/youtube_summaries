"""Gate summary tickers against Whisper windows + screen labels.

Used on every Analyze / save_summary so the next video cannot silently invent
tickers the way OKTA@11:31 / SOXX@2:14 did.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .config import DATA_DIR, ROOT, SUMMARY_DIR
from .parse_md import parse_summary_markdown
from .transcript import format_ts, load_transcript
from .video_check import parse_ts

# #region agent log
_DBG = ROOT / "debug-ec629f.log"
# #endregion

NEEDLES: dict[str, list[str]] = {
    "OKTA": ["okta"],
    "TWLO": ["twilio", "twlo"],
    "AXTI": ["axti"],
    "COIN": ["coinbase", "this coin", "coin is"],
    "RDDT": ["reddit", "rddt", "red ditch"],
    "CRWV": ["crwv", "coreweave", "corvif", "call vith", "core bit", "core viva", "core vvc"],
    "BE": ["bloom", "be is going"],
    "AOI": ["aoi"],
    "SNDK": ["sndk", "sandisk", "smtk", "sntk"],
    "MU": [" micron", " mu ", "m-u", "and mu"],
    "SKHY": ["hynix", "skhy", "sk heinz", "high-nix"],
    "SK HYNIX": ["hynix", "sk heinz"],
    "APLD": ["apld"],
    "IREN": ["iren", "iron yen", "hour and a cube", "hour yen"],
    "SMCI": ["smci", "super micro"],
    "IGV": ["igv", "this iaf"],
    "PATH": ["uipath", " path ", "like path"],
    "CRWD": ["crwd", "crowdstrike", "this crowd"],
    "CRM": ["crm", "salesforce"],
    "TSLA": ["tsla", "tesla", "tasta"],
    "DDOG": ["ddog", "datadog", "d-talk"],
    "ARM": ["arm is", "armels", "this arm", " arm "],
    "ONDS": ["onds", "all nds"],
    "NVDA": ["nvda", "nvidia", "and nvda", "videos continuing"],
    "QBTS": ["qbts", "qps", "d-wave"],
    "RGTI": ["rgti", "rigetti"],
    "IONQ": ["ionq"],
    "Quantum": ["quantum", "quantum's", "quantums"],
    "HPQ": ["hpq", "hbq"],
    "FIG": ["figma", "hold fig", "this fig", "fig after", "hold fake", "this fake"],
    "FROG": ["frog", "jfrog"],
    "AMD": [" amd", "amd "],
    "SPCX": ["spcx", "spacex", "space x", "sapce"],
    "HOOD": ["hood", "wodf", "robinhood"],
    "ALAB": ["alab", "astera", "a lap"],
    "MSTR": ["mstr", "microstrategy"],
    "SOXX": ["soxx", "socket is", "sock case"],
    "SMR": ["smr"],
    "USAR": ["usar", "usa are"],
    "QQQ": ["qqq"],
    "SPY": ["spy"],
    "OKLO": ["oklo"],
    "CLS": ["cls", "celestica"],
    "ORCL": ["orcl", "oracle", "auricle", "auricolour", "auricolor", "auricola"],
    "TEM": ["tempus", " tem "],
    "WDC": ["wdc", "western digital"],
    "DOGEUSD": ["doge"],
    "GOLD": ["gold", "silver"],
    "FTNT": ["ftnt", "fdnt", "fortinet"],
    "PANW": ["panw", "palo"],
    "WULF": ["wulf", "willio"],
    "CRCL": ["crcl", "circle"],
    "SMTC": ["smtc"],
    "RKLB": ["rklb"],
    "ASTS": ["asts"],
    "CYBER": ["cyber", "cypress", "cybernims"],
    "SEMIS": ["semi", "sammy", "sambies"],
    "SOFTWARE": ["software"],
}

TICKER_FROM_EXEC = re.compile(r"\*\*([^*]+)\*\*")
SKIP_LABELS = {"大方向", "買力", "主題", "執行紀律", "收結感覺", "字幕缺口", "Software", "Cyber", "Semis"}


def window_text(snippets: list[dict[str, Any]], center: float, before: float = 45.0, after: float = 45.0) -> str:
    """Tight local window — wide windows falsely attribute later speech (e.g. SpaceX@05:00 → 04:28)."""
    parts = []
    for s in snippets:
        st = float(s.get("start") or 0)
        dur = float(s.get("duration") or 0) or 2.0
        end = st + dur
        # include segment if it overlaps the window (not only if start is inside)
        if end < center - before or st > center + after:
            continue
        from .asr_fix import fix_asr

        parts.append(fix_asr(str(s.get("text") or "")))
    return " ".join(parts).lower()


def speech_hit(ticker: str, blob: str) -> bool:
    key = ticker.upper().strip()
    key = re.sub(r"（.*?）|\(.*?\)", "", key).strip()
    needles = NEEDLES.get(key)
    if needles:
        return any(n in blob for n in needles)
    return bool(re.search(rf"\b{re.escape(key.lower())}\b", blob))


def _ticker_needles(ticker: str) -> list[str]:
    key = ticker.upper().strip()
    key = re.sub(r"（.*?）|\(.*?\)", "", key).strip()
    if key.startswith("Quantum"):
        return ["quantum", "qbts", "rgti", "ionq"]
    if key in {"金／銀", "金", "銀"}:
        return NEEDLES.get("GOLD") or ["gold"]
    return list(NEEDLES.get(key) or [key.lower()])


def nearest_speech_time(
    snippets: list[dict[str, Any]],
    ticker: str,
    *,
    prefer_center: float | None = None,
) -> float | None:
    """True spoken time for ticker — WhisperX word ts, else char-offset inside long segments.

    Fixes: Whisper segment starts 04:28 but SpaceX word is at 05:00.
    """
    from .asr_fix import fix_asr

    needles = _ticker_needles(ticker)
    if not needles or not snippets:
        return None
    candidates: list[float] = []
    for s in snippets:
        st0 = float(s.get("start") or 0)
        dur = float(s.get("duration") or 0) or 2.0
        words = s.get("words") or []
        if words:
            for w in words:
                wd = re.sub(r"[^a-z0-9]+", "", str(w.get("word") or "").lower())
                if len(wd) < 2:
                    continue
                hit_w = False
                for n in needles:
                    nc = re.sub(r"[^a-z0-9]+", "", n)
                    if not nc or len(nc) < 2:
                        continue
                    # needle inside word, or word equals needle — NEVER short wd ⊂ needle ("a"∈"oracle")
                    # also NEVER match needle "cyber" as substring of "cypress" unless needle is cypress
                    if nc == "cyber" and wd.startswith("cypress"):
                        if n.strip() == "cypress" or "cypress" in needles:
                            pass
                        else:
                            continue
                    if nc in wd or wd == nc or (len(wd) >= 4 and wd in nc):
                        hit_w = True
                        break
                if hit_w:
                    candidates.append(float(w.get("start") or st0))
            # multi-word needles across adjacent words
            joined = " ".join(str(w.get("word") or "") for w in words).lower()
            if speech_hit(ticker, joined) and not any(st0 <= c <= st0 + dur for c in candidates):
                low = joined
                pos = min((low.find(n) for n in needles if n in low), default=-1)
                if pos >= 0 and words:
                    acc = 0
                    for w in words:
                        tok = str(w.get("word") or "")
                        if acc <= pos < acc + len(tok) + 1:
                            candidates.append(float(w.get("start") or st0))
                            break
                        acc += len(tok) + 1
            continue
        text = fix_asr(str(s.get("text") or ""))
        low = text.lower()
        if not speech_hit(ticker, low):
            continue
        pos = min((low.find(n) for n in needles if n in low), default=0)
        frac = min(0.95, max(0.0, pos / max(len(low), 1)))
        candidates.append(st0 + frac * dur)
    if not candidates:
        return None
    if prefer_center is None:
        return min(candidates)
    return min(candidates, key=lambda c: abs(c - prefer_center))


def _screen_symbol(by_t: dict[str, Any], t: str) -> str | None:
    lab = by_t.get(t) or {}
    sym = lab.get("symbol")
    return str(sym).upper() if sym else None


def _dual_snippets(video_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Main/faster-whisper + WhisperX snippets when available."""
    from .asr_compare import load_snippets
    from .triple_check import _find_transcript_pair

    tr = load_transcript(video_id) or {}
    a = list(tr.get("snippets") or [])
    w_path, x_path = _find_transcript_pair(video_id, "small")
    if w_path and w_path.exists():
        try:
            a = load_snippets(w_path) or a
        except Exception:
            pass
    b: list[dict[str, Any]] = []
    if x_path and x_path.exists():
        try:
            b = load_snippets(x_path)
        except Exception:
            b = []
    return a, b


def audit_summary(video_id: str, md: str | None = None) -> dict[str, Any]:
    if md is None:
        path = SUMMARY_DIR / f"{video_id}.md"
        if not path.exists():
            return {"video_id": video_id, "suspects": [], "ok": [], "error": "no markdown"}
        md = path.read_text(encoding="utf-8")
    parsed = parse_summary_markdown(md)
    snips_a, snips_b = _dual_snippets(video_id)
    from .transcript import load_caption_snippets

    cc_snips = load_caption_snippets(video_id)
    labels_path = DATA_DIR / "frames" / video_id / "labels.json"
    by_t: dict[str, Any] = {}
    if labels_path.exists():
        by_t = (json.loads(labels_path.read_text(encoding="utf-8")).get("by_t") or {})

    suspects: list[dict[str, Any]] = []
    ok: list[dict[str, Any]] = []
    for row in parsed.get("content_zh") or parsed.get("exec_zh") or []:
        t = str(row.get("t") or "")
        text = str(row.get("text") or "")
        # Already moved under dual-ASR dump section — skip
        if "雙ASR未見" in text:
            continue
        m = TICKER_FROM_EXEC.search(text)
        if not m:
            continue
        raw = m.group(1).strip()
        if raw in SKIP_LABELS:
            continue
        center = parse_ts(t) if t else 0.0
        blob_a = window_text(snips_a, center) if snips_a else ""
        blob_b = window_text(snips_b, center) if snips_b else ""
        blob_cc = window_text(cc_snips, center) if cc_snips else ""
        blob = (blob_cc + " " + blob_a + " " + blob_b).strip()
        screen = _screen_symbol(by_t, t)
        parts = re.split(r"\s*/\s*|\s*／\s*", raw)
        for part in parts:
            part = re.sub(r"（.*?）|\(.*?\)", "", part).strip()
            if not part or part in SKIP_LABELS:
                continue
            if part.startswith("Quantum"):
                hit = "quantum" in blob or any(speech_hit(x, blob) for x in ("QBTS", "RGTI", "IONQ"))
            elif part in {"金／銀", "金", "銀"}:
                hit = speech_hit("GOLD", blob)
            else:
                hit = speech_hit(part, blob)
            screen_ok = bool(screen and (screen == part.upper() or part.upper().startswith(screen)))
            hit_cc = bool(blob_cc) and (
                ("quantum" in blob_cc.lower() or any(speech_hit(x, blob_cc) for x in ("QBTS", "RGTI", "IONQ")))
                if part.startswith("Quantum")
                else speech_hit(part, blob_cc)
            )
            entry = {
                "t": t,
                "ticker": part,
                "speech_hit": hit or hit_cc,
                "hit_a": speech_hit(part, blob_a) if blob_a else False,
                "hit_b": speech_hit(part, blob_b) if blob_b else False,
                "hit_cc": hit_cc,
                "screen": screen,
                "screen_ok": screen_ok,
                "text": text[:160],
            }
            # YouTube CC is the quote source — not an unverified row
            if hit_cc:
                ok.append(entry)
            # With WhisperX present: faster-only hits are not "ok"
            elif snips_b and entry.get("hit_a") and not entry.get("hit_b") and not screen_ok:
                entry["faster_only"] = True
                suspects.append(entry)
            elif hit or screen_ok:
                ok.append(entry)
            else:
                suspects.append(entry)

    # #region agent log
    try:
        with _DBG.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "ec629f",
                        "hypothesisId": "H",
                        "location": "speech_audit.audit_summary",
                        "message": "audit",
                        "data": {
                            "video_id": video_id,
                            "suspect_count": len(suspects),
                            "ok_count": len(ok),
                            "suspects": suspects[:40],
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

    return {
        "video_id": video_id,
        "suspect_count": len(suspects),
        "ok_count": len(ok),
        "suspects": suspects,
        "ok": ok,
        "asof": format_ts(0),
    }


def flag_unverified_in_markdown(md: str, suspects: list[dict[str, Any]]) -> str:
    """Append ⚠語音未核實 on exec lines that failed the speech/screen gate."""
    if not suspects:
        return md
    keys = {(s["t"], s["ticker"].upper()) for s in suspects}
    out: list[str] = []
    in_exec = False
    for line in md.splitlines():
        if line.startswith("## "):
            in_exec = "時間軸內容" in line or "重點摘要" in line or line.strip() == "## Executive summary"
            out.append(line)
            continue
        if in_exec and line.startswith("- `"):
            m = re.match(r"^- `([^`]+)`\s+(.+)$", line)
            if m:
                t, rest = m.group(1), m.group(2)
                tm = TICKER_FROM_EXEC.search(rest)
                if tm:
                    tick = re.sub(r"（.*?）|\(.*?\)", "", tm.group(1)).strip().upper()
                    tick = tick.split("/")[0].split("／")[0].strip()
                    if (t, tick) in keys and "語音未核實" not in rest:
                        line = f"- `{t}` {rest} ｜⚠語音未核實"
        out.append(line)
    return "\n".join(out)


def audit_and_gate_markdown(video_id: str, md: str) -> tuple[str, dict[str, Any]]:
    report = audit_summary(video_id, md)
    flagged = flag_unverified_in_markdown(md, report.get("suspects") or [])
    report["flagged"] = flagged != md
    return flagged, report
