#!/usr/bin/env python3
"""Streamlit Cloud entry. This folder's requirements.txt is streamlit-only (no Whisper)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from streamlit_app import main

main()
