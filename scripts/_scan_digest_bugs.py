# -*- coding: utf-8 -*-
"""Scan digest contradictions across cached videos (debug session)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))

from app.auto_summary import _infer_side  # noqa: E402
from app.dual_asr_build import build_dual_confirmed_rows  # noqa: E402
from app.zh_digest import build_zh_digest  # noqa: E402

DBG = ROOT / "debug-ec629f.log"
VIDS = ["G3oc-Dv6Izs", "EhTGyU44w9M", "WjAbgRQCHZ8", "5ACCeRUiR2k", "ufN4u_ncWZg"]
BULL = re.compile(
    r"look for the longs|only long|stronger sector|showing (?:good )?strength|strengths? showing",
    re.I,
)
BEAR = re.compile(
    r"\bi'?m shorting|shorting after|semi-?short|focused on .{0,20}short|shortable|good short",
    re.I,
)


def main() -> None:
    for vid in VIDS:
        try:
            built = build_dual_confirmed_rows(vid)
        except Exception as e:
            print(vid, "BUILD_FAIL", e)
            continue
        rows = built.get("rows") or []
        lines = build_zh_digest(rows)
        h4: list[dict] = []
        for r in rows:
            if r.get("confidence") == "gap":
                continue
            text = str(r.get("text") or "")
            side = str(r.get("side") or "")
            lab = str(r.get("label") or r.get("ticker") or "")
            if BULL.search(text) and re.search(r"short", side, re.I):
                h4.append(
                    {
                        "label": lab,
                        "t": r.get("t"),
                        "side": side,
                        "text": text[:140],
                        "kind": "bull_text_short_side",
                    }
                )
            if BEAR.search(text) and re.search(r"long", side, re.I) and not re.search(
                r"short", side, re.I
            ):
                h4.append(
                    {
                        "label": lab,
                        "t": r.get("t"),
                        "side": side,
                        "text": text[:140],
                        "kind": "bear_text_long_side",
                    }
                )
            inferred = _infer_side(text, lab)
            if inferred != side and (
                BULL.search(text) or BEAR.search(text) or lab.upper() in {"FIG", "SOFTWARE", "SEMIS"}
            ):
                h4.append(
                    {
                        "label": lab,
                        "t": r.get("t"),
                        "side": side,
                        "reinfer": inferred,
                        "text": text[:140],
                        "kind": "side_drift",
                    }
                )
        with DBG.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "ec629f",
                        "hypothesisId": "H4",
                        "location": "scan_all",
                        "message": "speech_side_mismatch",
                        "data": {
                            "video_id": vid,
                            "h4": h4,
                            "h4_count": len(h4),
                            "quote": built.get("quote_source"),
                            "n_rows": len(rows),
                        },
                        "timestamp": int(time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        lede = next((x for x in lines if "今日總覽" in x), "")
        print(vid, "rows", len(rows), "h4", len(h4), "lede", lede[:100])
        for x in h4[:10]:
            print(" ", x)


if __name__ == "__main__":
    main()
