# -*- coding: utf-8 -*-
"""Snap all exec timestamps to true speech time + dual-ASR/screen verify."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.parse_md import parse_summary_markdown  # noqa: E402
from app.speech_audit import TICKER_FROM_EXEC, SKIP_LABELS  # noqa: E402
from app.summary_reconcile import (  # noqa: E402
    build_exec_actions,
    reconcile_summary_from_compare,
)
from app.triple_check import build_full_report  # noqa: E402


def _sync_timeline(md: str, moves: list[dict]) -> str:
    """Update EN/ZH timeline bullets when exec ticker time moved."""
    if not moves:
        return md
    # ticker -> new_t (last wins)
    tick_new: dict[str, str] = {}
    for a in moves:
        for tick in a.get("tickers") or []:
            tick_new[tick.upper()] = a["new_t"]

    out: list[str] = []
    in_tl = False
    for line in md.splitlines():
        if line.startswith("## "):
            in_tl = "Timestamped notes" in line or "時間軸" in line
            out.append(line)
            continue
        if in_tl and line.startswith("- `"):
            m = re.match(r"^- `([^`]+)`\s+(.+)$", line)
            if m:
                t, rest = m.group(1), m.group(2)
                # find any known ticker mention in rest
                up = rest.upper()
                for tick, new_t in tick_new.items():
                    if tick in up and t != new_t:
                        # only move if this line looks about that ticker
                        line = f"- `{new_t}` {rest}"
                        break
        out.append(line)
    return "\n".join(out)


def run(video_id: str, *, model: str = "small") -> None:
    report = build_full_report(video_id, model=model)
    plan = build_exec_actions(video_id, report=report, model=model)
    print("HINT", plan.get("hint"))
    print("--- ALL EXEC ---")
    for a in plan.get("actions") or []:
        moved = "MOVED" if a["t"] != a["new_t"] else ""
        ticks = ",".join(a["tickers"])
        print(
            f"{a['t']:>8} -> {a['new_t']:<8} {a['status']:<14} "
            f"ticks={ticks:<22} speech={a.get('speech_at') or '-':<8} "
            f"screen={a.get('screen') or '-':<6} {moved}"
        )

    patch = reconcile_summary_from_compare(video_id, report, model=model)
    moves = [a for a in (patch.get("actions") or []) if a["t"] != a["new_t"]]
    print("CHANGED", patch.get("changed"), "MOVES", len(moves))

    md_path = ROOT / "data" / "summaries" / f"{video_id}.md"
    md = md_path.read_text(encoding="utf-8")
    md2 = _sync_timeline(md, moves)
    # Also sync timeline for rows already snapped in prior runs:
    # rebuild map from current actions speech_at vs timeline
    plan2 = build_exec_actions(video_id, report=build_full_report(video_id, model=model), model=model)
    # Force timeline times to match exec new_t for each ticker
    tick_to_t: dict[str, str] = {}
    for a in plan2.get("actions") or []:
        for tick in a["tickers"]:
            tick_to_t[tick.upper()] = a["new_t"]

    out: list[str] = []
    in_tl = False
    for line in md2.splitlines():
        if line.startswith("## "):
            in_tl = "Timestamped notes" in line or "時間軸" in line
            out.append(line)
            continue
        if in_tl and line.startswith("- `"):
            m = re.match(r"^- `([^`]+)`\s+(.+)$", line)
            if m:
                t, rest = m.group(1), m.group(2)
                up = rest.upper()
                for tick, new_t in tick_to_t.items():
                    if re.search(rf"\b{re.escape(tick)}\b", up) and t != new_t:
                        line = f"- `{new_t}` {rest}"
                        break
        out.append(line)
    md3 = "\n".join(out)
    if md3 != md:
        from app.storage import save_summary

        save_summary(video_id, md3, meta={"provider": "reconcile-all"})
        print("timeline synced + saved")
    else:
        print("timeline already in sync")

    # Final dump
    parsed = parse_summary_markdown(md_path.read_text(encoding="utf-8"))
    print("--- FINAL EXEC ---")
    for row in parsed.get("exec_zh") or []:
        text = row.get("text") or ""
        tm = TICKER_FROM_EXEC.search(text)
        if not tm:
            continue
        raw = tm.group(1).strip()
        if raw in SKIP_LABELS:
            continue
        print(f"  {row.get('t')}  {raw}  |  {text[:100]}")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("video_id")
    p.add_argument("--model", default="small")
    args = p.parse_args()
    run(args.video_id, model=args.model)


if __name__ == "__main__":
    main()
