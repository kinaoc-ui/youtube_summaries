# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(video_id: str) -> None:
    root = ROOT / "data" / "frames" / video_id
    labels = json.loads((root / "labels.json").read_text(encoding="utf-8"))
    report_path = root / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {"video_id": video_id, "items": []}
    by = labels["by_t"]
    verify_by: dict = {}
    try:
        from app.ticker_verify import verify_labels

        v = verify_labels(video_id)
        verify_by = {x["t"]: x for x in v.get("items") or []}
        report["verify_counts"] = v.get("counts")
        report["verify_asof"] = v.get("asof")
    except Exception as e:
        report["verify_error"] = str(e)
    items = report.get("items") or []
    idx = {x.get("t"): i for i, x in enumerate(items)}
    for t, lab in by.items():
        sym = lab.get("symbol")
        tickers = [sym] if sym else []
        stamp = t.replace(":", "-")
        entry = {
            "t": t,
            "frame": f"/frames/{video_id}/{stamp}.jpg",
            "header": f"/frames/{video_id}/{stamp}_hdr.jpg",
            "ocr": "",
            "ocr_tickers": tickers,
            "screen_symbol": sym,
            "screen_name": lab.get("name"),
            "screen_price": lab.get("price"),
            "label_source": "cursor-agent",
            "claimed": [],
            "mismatch": False,
        }
        vrow = verify_by.get(t) or {}
        entry["verify"] = vrow.get("verdict")
        entry["verify_note"] = vrow.get("note")
        entry["speech_tickers"] = vrow.get("speech") or []
        entry["price_suggest"] = vrow.get("suggest")
        if vrow.get("verdict") == "fail":
            entry["mismatch"] = True
            entry["price_fail"] = True
        elif vrow.get("verdict") == "split":
            entry["speech_split"] = True
        if t in idx:
            old = items[idx[t]]
            claimed = old.get("claimed") or []
            entry["claimed"] = claimed
            entry["seconds"] = old.get("seconds")
            if tickers and claimed and not (set(tickers) & set(claimed)):
                entry["mismatch"] = True
            items[idx[t]] = {**old, **entry}
        else:
            items.append(entry)
    mm = sum(1 for x in items if x.get("mismatch"))
    report.update(
        {
            "items": items,
            "frame_count": len(items),
            "mismatch_count": mm,
            "ocr_engine": "cursor-agent",
            "label_source": "cursor-agent",
            "labeled": len(by),
        }
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK {video_id}: labeled={len(by)} mismatches={mm}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "5ACCeRUiR2k")
