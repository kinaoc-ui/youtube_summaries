# -*- coding: utf-8 -*-
"""Re-assert the latest complete dated Martin E_Main as TradingView Active.

Does not use filename sort or mtime. ``Martin_Luk_NA_E_Main.txt``, video-id
copies, and lists missing INDEXES/LONGS/SHORTS/FOCUS are never uploaded.

  python scripts/reassert_martin_tv.py --dry-run
  python scripts/reassert_martin_tv.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.emain_eligibility import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
