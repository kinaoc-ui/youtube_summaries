# -*- coding: utf-8 -*-
"""Unit tests for screener-aware watchlist OCR + TradingView export."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.tradingview_export import format_watchlist_txt, tv_symbol
from app.watchlist_extract import (
    OCR_STOP,
    _candidate_tickers,
    analyze_frame_ocr,
    crop_watchlist_panel,
    extract_watchlist,
    sample_screener_seconds,
    sample_tail_seconds,
    symbols_from_boxes,
)


class TradingViewExportTests(unittest.TestCase):
    def test_tv_symbol_default_nasdaq(self) -> None:
        self.assertEqual(tv_symbol("NVDA"), "NASDAQ:NVDA")
        self.assertEqual(tv_symbol("CRM"), "NYSE:CRM")
        self.assertEqual(tv_symbol("SPY"), "AMEX:SPY")

    def test_tv_symbol_already_prefixed(self) -> None:
        self.assertEqual(tv_symbol("NASDAQ:AAPL"), "NASDAQ:AAPL")

    def test_format_watchlist_txt_section_and_csv(self) -> None:
        text = format_watchlist_txt(["NVDA", "HOOD", "NVDA"], section="Martin Luk")
        self.assertIn("###Martin Luk", text)
        self.assertIn("NASDAQ:NVDA", text)
        body = [ln for ln in text.splitlines() if ln and not ln.startswith("###")][0]
        self.assertEqual(body.count("NASDAQ:NVDA"), 1)
        self.assertIn(",", body)


class TailSampleTests(unittest.TestCase):
    def test_sample_last_10_min(self) -> None:
        times = sample_tail_seconds(7200.0, last_minutes=10.0, interval_sec=20.0, end_pad_sec=5.0)
        self.assertTrue(times)
        self.assertGreaterEqual(times[0], 7200 - 600 - 1)
        self.assertLessEqual(times[-1], 7200 - 5 + 1)

    def test_short_vod(self) -> None:
        times = sample_tail_seconds(120.0, last_minutes=10.0, interval_sec=30.0)
        self.assertTrue(times)
        self.assertEqual(times[0], 0.0)

    def test_screener_samples_whole_vod_not_only_tail(self) -> None:
        times = sample_screener_seconds(5300.0, coarse_interval=60.0, max_frames=80)
        self.assertTrue(times)
        self.assertLess(times[0], 120.0)  # early frames included
        self.assertGreater(times[-1], 5000.0)  # near end too
        self.assertLessEqual(len(times), 80)


class OcrTickerFilterTests(unittest.TestCase):
    def test_known_and_stop(self) -> None:
        text = "NVDA 142.5  EMA  HOOD  leading mediocre CRWD"
        found = _candidate_tickers(text)
        self.assertIn("NVDA", found)
        self.assertIn("HOOD", found)
        self.assertIn("CRWD", found)
        self.assertNotIn("EMA", found)
        for stop in ("LEADING", "MEDIOCRE"):
            self.assertNotIn(stop, found)
            self.assertIn(stop, OCR_STOP)


class ScreenerBoxTests(unittest.TestCase):
    def _box(self, text: str, x0: float, y0: float, w: float = 40, h: float = 16) -> dict:
        return {
            "text": text,
            "score": 0.99,
            "x0": x0,
            "y0": y0,
            "x1": x0 + w,
            "y1": y0 + h,
            "cx": x0 + w / 2,
            "cy": y0 + h / 2,
        }

    def test_leader_table_symbol_column_vs_detail_panel(self) -> None:
        """Left Symbol column wins; right BRZE detail must not wipe the list."""
        boxes = [
            self._box("Leader", 40, 20),
            self._box("Symbol", 40, 50),
            self._box("Price", 200, 50),
            self._box("Change %", 320, 50),
        ]
        table = ["NVDA", "HOOD", "CRWD", "ALAB", "AMD", "SMCI", "ARM", "BRZE"]
        for i, sym in enumerate(table):
            boxes.append(self._box(sym, 40, 100 + i * 40))
            boxes.append(self._box(f"{100 + i}.5", 200, 100 + i * 40))
        # Detail panel on the right (BRZE @ 45.85) — should be ignored as list source
        boxes.append(self._box("BRZE", 700, 100))
        boxes.append(self._box("45.85", 700, 140))
        boxes.append(self._box("Braze Inc", 700, 180, w=80))

        parsed = symbols_from_boxes(boxes)
        self.assertEqual(parsed["layout"], "screener_table")
        for sym in table:
            self.assertIn(sym, parsed["table_symbols"])
        self.assertGreaterEqual(len(parsed["table_symbols"]), 6)

    def test_detail_panel_alone_is_not_table(self) -> None:
        boxes = [
            self._box("BRZE", 700, 100),
            self._box("45.85", 700, 140),
            self._box("Braze Inc", 700, 180, w=80),
        ]
        parsed = symbols_from_boxes(boxes)
        self.assertEqual(parsed["layout"], "detail_panel")
        self.assertEqual(parsed["table_symbols"], [])
        self.assertIn("BRZE", parsed["detail_symbols"])

    def test_cera_junk_filtered(self) -> None:
        self.assertIn("CERA", OCR_STOP)
        self.assertNotIn("CERA", _candidate_tickers("CERA 12.3 EMA"))


class SyntheticPipelineTests(unittest.TestCase):
    def test_extract_watchlist_screener_mode_ignores_detail_wipe(self) -> None:
        video_id = "TESTSCRN001"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_video = tmp_path / f"{video_id}.mp4"
            fake_video.write_bytes(b"\x00" * 64)

            def fake_extract(video_path, seconds, out_path):
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 3000)
                return out_path

            table_syms = ["NVDA", "HOOD", "CRWD", "ALAB", "AMD", "SMCI", "ARM", "BRZE"]

            def fake_analyze(path):
                # Alternate: strong table vs detail-only BRZE
                if fake_analyze.i % 3 == 0:
                    fake_analyze.i += 1
                    return {
                        "engine": "mock",
                        "ocr": "Leader Symbol " + " ".join(table_syms),
                        "layout": "screener_table",
                        "score": 12.0,
                        "symbols": table_syms,
                        "table_symbols": table_syms,
                        "detail_symbols": [],
                        "sections": ["leader"],
                        "prices": {"BRZE": 45.85},
                        "header_hits": 2,
                    }
                fake_analyze.i += 1
                return {
                    "engine": "mock",
                    "ocr": "BRZE 45.85 Braze Inc",
                    "layout": "detail_panel",
                    "score": 0.5,
                    "symbols": ["BRZE"],
                    "table_symbols": [],
                    "detail_symbols": ["BRZE"],
                    "sections": [],
                    "prices": {"BRZE": 45.85},
                    "header_hits": 0,
                }

            fake_analyze.i = 0

            with (
                mock.patch("app.watchlist_extract.download_video", return_value=fake_video),
                mock.patch("app.watchlist_extract.video_duration_sec", return_value=600.0),
                mock.patch("app.watchlist_extract.extract_frame", side_effect=fake_extract),
                mock.patch("app.watchlist_extract.analyze_frame_ocr", side_effect=fake_analyze),
                mock.patch("app.watchlist_extract.speech_hint_seconds", return_value=[400.0]),
                mock.patch("app.watchlist_extract.FRAMES_DIR", tmp_path / "frames"),
                mock.patch("app.watchlist_extract.SUMMARY_DIR", tmp_path / "summaries"),
                mock.patch("app.watchlist_extract.WATCHLIST_OUT_DIR", tmp_path / "out"),
                mock.patch("app.watchlist_extract.OUTPUT_DIR", tmp_path / "outputs"),
            ):
                (tmp_path / "summaries").mkdir(parents=True, exist_ok=True)
                report = extract_watchlist(
                    video_id,
                    mode="screener",
                    last_minutes=2.0,
                    coarse_interval=60.0,
                    dense_interval=30.0,
                    max_frames=20,
                    min_hits=1,
                    force=True,
                )
                self.assertGreaterEqual(report["symbol_count"], 6)
                for sym in ("NVDA", "HOOD", "CRWD", "BRZE"):
                    self.assertIn(sym, report["symbols"])
                # Detail panel alone must not shrink list to BRZE-only
                self.assertNotEqual(report["symbols"], ["BRZE"])
                tv = tmp_path / "out" / f"{video_id}.txt"
                self.assertTrue(tv.exists())
                self.assertIn("NASDAQ:NVDA", tv.read_text(encoding="utf-8"))

    def test_crop_watchlist_panel(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow missing")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "frame.jpg"
            dst = Path(tmp) / "crop.jpg"
            im = Image.new("RGB", (960, 540), (0, 0, 0))
            d = ImageDraw.Draw(im)
            d.text((700, 100), "AMD", fill=(255, 255, 255))
            im.save(src)
            out = crop_watchlist_panel(src, dst)
            self.assertIsNotNone(out)
            self.assertTrue(dst.exists())

    def test_analyze_frame_ocr_on_synthetic_png(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow missing")
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "leader.png"
            im = Image.new("RGB", (900, 600), (20, 20, 24))
            d = ImageDraw.Draw(im)
            d.text((40, 20), "Leader", fill=(200, 200, 200))
            d.text((40, 60), "Symbol", fill=(160, 160, 160))
            d.text((200, 60), "Price", fill=(160, 160, 160))
            rows = ["NVDA", "HOOD", "CRWD", "ALAB", "AMD", "SMCI", "ARM", "BRZE"]
            for i, sym in enumerate(rows):
                d.text((40, 100 + i * 40), sym, fill=(240, 240, 240))
                d.text((200, 100 + i * 40), f"{40 + i}.5", fill=(200, 200, 200))
            d.rectangle((550, 80, 880, 400), fill=(28, 28, 32))
            d.text((570, 100), "BRZE", fill=(255, 255, 255))
            d.text((570, 140), "45.85", fill=(180, 255, 180))
            im.save(p)
            result = analyze_frame_ocr(p)
            self.assertEqual(result["layout"], "screener_table")
            self.assertGreaterEqual(len(result["table_symbols"]), 5)
            self.assertIn("NVDA", result["table_symbols"])


if __name__ == "__main__":
    unittest.main()
