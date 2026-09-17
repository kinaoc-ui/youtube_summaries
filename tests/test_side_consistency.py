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
from app.zh_digest import _merge_reasons, build_zh_digest


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

    def test_strength_among_is_lean_long(self) -> None:
        q = (
            "Now I can only see strength among the software names and especially "
            "particularly in the cybersecurity stocks."
        )
        self.assertIn("偏多", _watch_lean(q, "SOFTWARE"))
        self.assertIn("偏多", _watch_lean(q, "CYBER"))

    def test_still_leading_is_lean_long(self) -> None:
        q = "The software name seems like they're still leading."
        self.assertIn("偏多", _watch_lean(q, "SOFTWARE"))

    def test_decent_shot_missed_breakdown_is_lean_long(self) -> None:
        q = (
            "I think like ARM has a pretty decent shot in the morning, but it's "
            "going too fast and I missed it on this like a one minute breakdown."
        )
        self.assertIn("偏多", _watch_lean(q, "ARM"))

    def test_quantum_shot_is_lean_short(self) -> None:
        q = "And maybe also the quantum shot."
        self.assertIn("偏空", _watch_lean(q, "QUANTUM"))

    def test_mixed_last_cue_reject_wins(self) -> None:
        q = "looks pretty strong but then getting rejected at the nine"
        self.assertIn("偏空", _watch_lean(q, "FIG"))

    def test_break_out_is_lean_long(self) -> None:
        q = "Yeah, I think if ARM can break out from this opening range height"
        self.assertIn("偏多", _watch_lean(q, "ARM"))


class DigestMergeTests(unittest.TestCase):
    def test_does_not_glue_strength_onto_lean_short(self) -> None:
        rs = [
            {"side": "Watch／偏多", "text": "SMTC is really strong. looks pretty strong", "start": 1},
            {"side": "Watch／偏空", "text": "getting rejected at the nine", "start": 2},
        ]
        reason = _merge_reasons("SMTC", rs, rs[-1])
        self.assertNotIn("睇落", reason)
        self.assertNotIn("破位", reason)

    def test_fills_plain_watch_from_joined_strength(self) -> None:
        rows = [
            {
                "label": "Software",
                "side": "Watch",
                "text": "Now I can only see strength among the software names",
                "start": 1409,
                "t": "23:29",
            }
        ]
        joined = "\n".join(build_zh_digest(rows, "x"))
        self.assertIn("偏多", joined)
        self.assertNotIn("**觀望／watch｜Software**", joined)

    def test_timeline_fills_plain_watch_from_quote(self) -> None:
        from app.zh_digest import content_zh_line

        line = content_zh_line(
            {
                "label": "ASTS",
                "side": "Watch",
                "text": (
                    "ASTS, the recent bounce in July. it is bouncing into the 50 EMA "
                    "and it just like neglects it and then keeps going higher."
                ),
                "t": "1:44:20",
                "confidence": "dual",
            },
            "x",
        )
        self.assertIn("觀望偏多", line)


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

    def test_flags_plain_watch_with_strength_reason(self) -> None:
        md = (
            "# EP\n\n## 真正摘要（中文）\n\n"
            "- **觀望／watch｜Software** [23:29](https://youtu.be/x) — 仍有強勢\n"
        )
        self.assertTrue(digest_contradictions(md, "x"))


if __name__ == "__main__":
    unittest.main()
