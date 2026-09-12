import json
from pathlib import Path

p = Path("data/transcripts/I8QnaZwg7Qw.json")
d = json.loads(p.read_text(encoding="utf-8"))
sn = d["snippets"]
print("n", len(sn), "source", d.get("source"))
for s in sn:
    t = (s.get("text") or "").strip().replace("\n", " ")
    if len(t) > 50:
        print(f"{s['start']:8.1f} d={s.get('duration', 0):8.1f} {t[:180]}")
