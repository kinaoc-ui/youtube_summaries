# -*- coding: utf-8 -*-
"""A/B: faster-whisper vs WhisperX — list time ranges that are out of sync.

Usage (local, free):
  pip install faster-whisper
  pip install git+https://github.com/m-bain/whisperX.git

  python scripts/compare_asr.py EhTGyU44w9M
  python scripts/compare_asr.py EhTGyU44w9M --model large-v3-turbo
  python scripts/compare_asr.py EhTGyU44w9M --report-only   # reuse caches
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.asr_compare import compare_whisper_vs_whisperx, run_compare  # noqa: E402
from app.config import DATA_DIR  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Compare faster-whisper vs WhisperX sync")
    p.add_argument("video_id")
    p.add_argument("--model", default="large-v3-turbo", help="Shared model size")
    p.add_argument("--report-only", action="store_true", help="Compare existing JSON only")
    p.add_argument("--skip-whisper", action="store_true")
    p.add_argument("--skip-whisperx", action="store_true")
    args = p.parse_args()
    vid = args.video_id
    model = args.model

    if args.report_only:
        w = DATA_DIR / "transcripts" / f"{vid}.whisper-{model}.json"
        if not w.exists():
            w = DATA_DIR / "transcripts" / f"{vid}.whisper.json"
        x = DATA_DIR / "transcripts" / f"{vid}.whisperx-{model}.json"
        if not x.exists():
            x = DATA_DIR / "transcripts" / f"{vid}.whisperx.json"
        if not w.exists() or not x.exists():
            raise SystemExit(f"Missing cache:\n  {w}\n  {x}")
        report = compare_whisper_vs_whisperx(w, x)
        report["video_id"] = vid
        report["model"] = model
        out = DATA_DIR / "asr_compare" / f"{vid}.whisper-vs-whisperx.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(out)
    else:
        report = run_compare(
            vid,
            whisper_model=model,
            skip_whisper=args.skip_whisper,
            skip_whisperx=args.skip_whisperx,
        )

    print("===", report.get("pair"), "|", vid, "| model", report.get("model"))
    print("hint:", report.get("hint"))
    print("desync_by_kind:", json.dumps(report.get("desync_by_kind") or {}, ensure_ascii=False))
    a, b = report.get("a") or {}, report.get("b") or {}
    print(
        f"faster-whisper: snippets={a.get('snippet_count')} gaps={a.get('gap_count')} "
        f"tickers={a.get('ticker_types')} word_ts={a.get('has_word_ts')}"
    )
    print(
        f"whisperx:       snippets={b.get('snippet_count')} gaps={b.get('gap_count')} "
        f"tickers={b.get('ticker_types')} word_ts={b.get('has_word_ts')}"
    )
    print("only_faster_whisper_tickers:", report.get("only_a_tickers"))
    print("only_whisperx_tickers:", report.get("only_b_tickers"))
    print("--- unsync regions (first 25) ---")
    for d in (report.get("desync") or [])[:25]:
        kind = d.get("kind")
        print(f"[{kind}] {d.get('t')}–{d.get('t_end')}  {d.get('note')}")
        if d.get("tickers_only_a") or d.get("tickers_only_b"):
            print(f"    tickers A={d.get('tickers_only_a')} B={d.get('tickers_only_b')}")
    print("report:", report.get("report_path"))


if __name__ == "__main__":
    main()
