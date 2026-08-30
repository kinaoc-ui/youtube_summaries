# -*- coding: utf-8 -*-
import json
from pathlib import Path
import sys

vid = sys.argv[1] if len(sys.argv) > 1 else "5ACCeRUiR2k"
p = Path("data/transcripts") / f"{vid}.json"
d = json.loads(p.read_text(encoding="utf-8"))
chunks = d.get("chunks") or []
print("source", d.get("source"), "snippets", len(d.get("snippets") or []), "chunks", len(chunks))
out = Path("data/transcripts") / f"{vid}_chunks.txt"
lines = [f"[{c['t']}] {c['text']}" for c in chunks]
out.write_text("\n\n".join(lines), encoding="utf-8")
print("wrote", out, "chars", sum(len(x) for x in lines))
for c in chunks[:10]:
    print("---", c["t"], "---")
    print(c["text"][:300])
