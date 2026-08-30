# -*- coding: utf-8 -*-
from pathlib import Path
import ast
import re

p = Path(__file__).resolve().parents[1] / "app" / "main.py"
text = p.read_text(encoding="utf-8")

pattern = re.compile(
    r"            # Caption-disabled.*?status=\"whisper_running\",\n                hint=hint,\n            \)\n",
    re.S,
)
replacement = """            # Caption-disabled -> background Whisper (do not block HTTP for hours)
            job = _start_whisper_job(video_id)
            st = job.get("status") or "starting"
            hint = (
                f"[{title}] YouTube captions disabled (no auto-captions). "
                f"Started local Whisper (model={settings.whisper_model}, status={st}). "
                "A ~3h stream may take tens of minutes to a few hours on CPU. "
                f"When done, click Analyze again or say in Chat: summarize {video_id}. "
                f"Progress: GET /api/whisper/{video_id}"
            )
            return AnalyzeResponse(
                video_id=video_id,
                title=title,
                provider=provider,
                bullet_count=0,
                bullets=[],
                markdown="",
                url=url,
                status="whisper_running",
                hint=hint,
            )
"""

new, n = pattern.subn(replacement, text, count=1)
if n != 1:
    raise SystemExit(f"replace count={n}")
ast.parse(new)
p.write_text(new, encoding="utf-8")
print("patched")
