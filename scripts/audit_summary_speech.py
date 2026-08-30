# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.speech_audit import audit_summary  # noqa: E402


def main() -> None:
    vid = sys.argv[1] if len(sys.argv) > 1 else "5ACCeRUiR2k"
    report = audit_summary(vid)
    print(json.dumps({"suspect_count": report["suspect_count"], "ok_count": report["ok_count"]}, indent=2))
    for s in report.get("suspects") or []:
        print(f"MISS {s['t']:>8}  {s['ticker']:<12} screen={s.get('screen')}")


if __name__ == "__main__":
    main()
