# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ticker_verify import verify_labels  # noqa: E402


def main(video_id: str) -> None:
    out = verify_labels(video_id)
    print(json.dumps({"video_id": video_id, "asof": out["asof"], "counts": out["counts"]}, indent=2))
    for x in out["items"]:
        if x["verdict"] in {"fail", "split", "no_quote"}:
            print(
                f"{x['t']:>8}  {x['verdict']:12}  {x.get('symbol')}  "
                f"suggest={x.get('suggest')}  speech={x.get('speech')}  {x.get('note')}"
            )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "5ACCeRUiR2k")
