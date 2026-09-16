# -*- coding: utf-8 -*-
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dual_asr_build import patch_markdown_with_dual
from app.storage import save_summary

ROOT = Path(__file__).resolve().parents[1]
failed = []
only = set(sys.argv[1:])
for p in sorted((ROOT / "data" / "summaries").glob("*.md")):
    vid = p.stem
    if only and vid not in only:
        continue
    md = p.read_text(encoding="utf-8")
    title = md.splitlines()[0].lstrip("# ").strip() if md else vid
    print(f".. {vid} {title}", flush=True)
    try:
        new, built = patch_markdown_with_dual(vid, md)
        save_summary(vid, new, meta={"title": title, "provider": "auto-summary"})
        print(
            f"OK {vid} dual={built.get('dual_count')} wx={built.get('wx_only_count')} src={built.get('quote_source')}",
            flush=True,
        )
    except Exception as e:
        failed.append(vid)
        print(f"FAIL {vid} {e}", flush=True)
if failed:
    raise SystemExit("failed: " + ",".join(failed))
