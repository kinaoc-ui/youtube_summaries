# -*- coding: utf-8 -*-
"""Regression: lean-short must not fire on failed breakdown / contrast strength."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auto_summary import _watch_lean
from app.side_audit import digest_contradictions
from app.zh_digest import _merge_reasons


class WatchLeanTests(unittest.TestCase):
    def test_smtc_failed_push_then_breakout(self) -> None:
        q = (
            "from three to four days with several attempts to push lower, "
            "but eventually it all failed. And then we got this breakout."
        )
        self.assertIn("偏多", _watch_lean(q, "SMTC"))

    def test_weak_stock_contrast_then_holding(self) -> None:
        q = (
            "When the stock is weak, we will see a fade, we will see some rejection, "
            "we will see some resistance, but SMTC is like holding near this 50 EMA "
            "and the anchor fill up"
        )
        self.assertIn("偏多", _watch_lean(q, "SMTC"))

    def test_not_sign_of_weakness(self) -> None:
        q = "Yeah, especially on the semis But we're not getting much sign of weakness on this bounce so maybe"
        self.assertNotIn("偏空", _watch_lean(q, "SEMIS"))

    def test_software_strength_semis_weakness(self) -> None:
        q = "the strength in the software and the weakness in the semis can go together at the same time"
        self.assertIn("偏多", _watch_lean(q, "SOFTWARE"))
        self.assertIn("偏空", _watch_lean(q, "SEMIS"))

    def test_unfortunate_if_rejected_wants_higher(self) -> None:
        q = (
            "Like if the quantums are getting rejected today and then goes lower "
            "that will be very unfortunate. So wish they can like go higher."
        )
        self.assertIn("偏多", _watch_lean(q, "QUANTUM"))


class DigestMergeTests(unittest.TestCase):
    def test_does_not_glue_strength_onto_lean_short(self) -> None:
        rs = [
            {"side": "Watch／偏多", "text": "SMTC is really strong. looks pretty strong", "start": 1},
            {"side": "Watch／偏空", "text": "getting rejected at the nine", "start": 2},
        ]
        reason = _merge_reasons("SMTC", rs, rs[-1])
        self.assertNotIn("睇落", reason)
        self.assertNotIn("破位", reason)


class DigestGateTests(unittest.TestCase):
    def test_flags_lean_short_with_strength_reason(self) -> None:
        md = (
            "# EP\n\n## 真正摘要（中文）\n\n"
            "- **觀望偏空／lean short｜SMTC** [45:27](https://youtu.be/x) — 睇落仍然強；破位／轉強\n"
        )
        hits = digest_contradictions(md, "x")
        self.assertTrue(hits)

    def test_allows_lean_short_with_reject(self) -> None:
        md = (
            "# EP\n\n## 真正摘要（中文）\n\n"
            "- **觀望偏空／lean short｜FIG** [1:15:04](https://youtu.be/x) — 被 reject\n"
        )
        self.assertEqual(digest_contradictions(md, "x"), [])


if __name__ == "__main__":
    unittest.main()
