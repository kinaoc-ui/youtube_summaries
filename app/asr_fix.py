from __future__ import annotations

import json
import re
from pathlib import Path

# Common ASR fixes for Martin Luk / trading streams.
# Do not map generic "fake" → FIG (he also says "fake out").
ASR_FIXES = [
    (r"\bKims\b", "HIMS"),
    (r"\bhim is\b", "HIMS is"),
    (r"\bIron Yen\b", "IREN"),
    (r"\bhour yen\b", "IREN"),
    (r"\bHour yen\b", "IREN"),
    (r"\bSKH Highix\b", "SK Hynix"),
    (r"\bSK highix\b", "SK Hynix"),
    (r"\bSK hidings\b", "SK Hynix"),
    (r"\bskex\b", "SK Hynix"),
    (r"\bSNTK\b", "SNDK"),
    (r"\bSNK\b", "SNDK"),
    (r"\bSN indicated SKY\b", "SNDK and SK Hynix"),
    (r"\bSKHY\b", "SK Hynix"),
    (r"\bsock case\b", "SOXX"),
    (r"\bSock case\b", "SOXX"),
    (r"\brubric\b", "Rubrik (RBRK)"),
    (r"\bRubric\b", "Rubrik (RBRK)"),
    (r"\bcircle\b", "CRCL"),
    (r"\bCircle\b", "CRCL"),
    (r"\bAli 9\b", "hourly 9"),
    (r"\bKill and spice\b", "QQQ and SPY"),
    (r"\bkills at the spies\b", "QQQ and SPY"),
    (r"\bon form payrolls\b", "non-farm payrolls"),
    (r"\bangle up\b", "anchored VWAP"),
    (r"\banchor up\b", "anchored VWAP"),
    (r"\breal break\b", "CoreWeave"),
    (r"\bHUDs\b", "HOOD"),
    (r"\bhuts\b", "HOOD"),
    (r"\bfor hot\b", "for HOOD"),
    (r"\bcorning\b", "Corning (GLW)"),
    (r"\bCorning\b", "Corning (GLW)"),
    (r"\bbasics\b", "ASTS"),
    (r"\bOllo\b", "OLLI"),
    (r"\bQQQM\b", "QQQ / IWM"),
    (r"\bsep ETF\b", "sector ETF"),
    (r"\bMalcolm Mini\b", "Mark Minervini"),
    (r"\bsapce\s*x\b", "SpaceX (SPCX)"),
    (r"\bsapce\b", "SpaceX (SPCX)"),
    (r"\bspace\s*x\b", "SpaceX (SPCX)"),
    (r"\bspace\s*six\b", "SpaceX (SPCX)"),
    (r"\bspaces\b", "SpaceX (SPCX)"),
    (r"\bspace exists\b", "SpaceX (SPCX) is"),
    (r"\bhold fake\b", "hold FIG"),
    (r"\bthis fake\b", "this FIG"),
    (r"\bfake after\b", "FIG after"),
    (r"\bfigma\b", "FIG"),
    (r"\bfrog\b", "FROG"),
    (r"\bjfrog\b", "FROG"),
    (r"\bamd\b", "AMD"),
    # Whisper often mangles "this coin is" / COIN as "octaves" — never promote to OKTA
    (r"\bthis octaves\b", "this COIN is"),
    (r"\boctaves pulling\b", "COIN pulling"),
    (r"\bCall Vith\b", "CRWV"),
    (r"\bCorvif\b", "CRWV"),
    (r"\bcore bit\b", "CRWV"),
    (r"\bVE is going\b", "BE is going"),
    (r"\bSMTK\b", "SNDK"),
    (r"\bHBQ\b", "HPQ"),
    (r"\bhour and a cube\b", "IREN"),
    (r"\bthis IAF\b", "this IGV"),
    (r"\bWODF\b", "HOOD"),
    (r"\bUSA are looking\b", "USAR are looking"),
    (r"\bTASTA\b", "TSLA"),
    (r"\bArmels\b", "ARM is"),
    (r"\bthis crowd is\b", "this CRWD is"),
    (r"\bD-talk\b", "DDOG"),
    (r"\bAll NDS\b", "ONDS"),
    (r"\bSK Heinz\b", "SK Hynix"),
    (r"\bsocket is still\b", "SOXX is still"),
    (r"\bred ditch\b", "RDDT"),
    (r"\band videos continuing\b", "and NVDA continuing"),
    (r"\bauricle\b", "ORCL"),
    (r"\bauricolou?r\b", "ORCL"),
    (r"\bauricola\b", "ORCL"),
    # Single tokens only — never expand LAPDLAPD spam loops into fake APLD walls
    (r"\bLAPDOWN\b", "APLD gap down"),
    (r"\bLAPDT\b", "APLD"),
    (r"(?<![A-Z])\bLAPD\b(?![A-Z])", "APLD"),
    (r"\bSMC\s*IRD\b", "SMCI"),
    (r"\bCORE\s*VIVA\b", "CRWV"),
    (r"\bFDNT\b", "FTNT"),
    (r"\bWillio\b", "WULF"),
    (r"\bwillio\b", "WULF"),
    (r"\bSammy'?s\b", "semis"),
    (r"\bSambies\b", "semis"),
    (r"\bcofee web\b", "CRWV"),
    (r"\bcoffee web\b", "CRWV"),
    (r"\b21nm\b", "21 EMA"),
    (r"\bthen field gap\b", "unfilled gap"),
    (r"\bcybernims\b", "cyber names"),
]

WHISPER_HOTWORDS = (
    "FIG Figma FROG JFrog SPCX SpaceX AMD NVDA QQQ QQQM SPY IWM "
    "OKTA CRWD DDOG PATH CRM CRWV SNDK MU APLD HOOD "
    "TSLA TSLA RKLB ASTS HIMS IREN SOXX MSTR QBTS RGTI IONQ ALAB "
    "OKLO CLS TEM WDC ORCL AXTI HPQ BE RDDT COIN ARM IGV"
)

WHISPER_INITIAL_PROMPT = (
    "US stock trading livestream. Tickers: FIG Figma, FROG JFrog, "
    "SPCX SpaceX, AMD, NVDA, QQQ, OKTA, CRWD, SNDK, CRWV, TSLA, "
    "HOOD, QBTS, RGTI. Not 'fake' when he means FIG; not 'space' for SpaceX."
)


def fix_asr(text: str) -> str:
    out = text or ""
    # faster-whisper sometimes emits LAPDLAPDLAPD… walls — do NOT map those to APLD
    if len(re.findall(r"LAPD", out, flags=re.I)) >= 3:
        out = re.sub(r"(?:LAPD(?:OWN|T)?\s*)+", " ", out, flags=re.I)
        out = re.sub(r"\s+", " ", out).strip()
        if len(out) < 8:
            return ""
    for pat, repl in ASR_FIXES:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    return out


def rewrite_transcript_file(path: Path) -> int:
    """Apply ticker ASR fixes in-place to a cached transcript JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    if isinstance(data, list):
        rows = data
        for s in rows:
            if isinstance(s, dict) and "text" in s:
                t2 = fix_asr(s["text"])
                if t2 != s["text"]:
                    n += 1
                    s["text"] = t2
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return n
    for key in ("snippets", "chunks"):
        for s in data.get(key) or []:
            if isinstance(s, dict) and "text" in s:
                t2 = fix_asr(s["text"])
                if t2 != s["text"]:
                    n += 1
                    s["text"] = t2
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return n
