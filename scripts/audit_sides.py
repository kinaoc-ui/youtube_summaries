# -*- coding: utf-8 -*-
"""CLI for lean/digest contradictions. Exit 1 if the push gate would fail."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.side_audit import run_gate  # noqa: E402


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(run_gate())
