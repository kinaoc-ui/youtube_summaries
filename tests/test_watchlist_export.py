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
from app.us_tickers import filter_symbols, is_valid_us_ticker
from app.watchlist_extract import (
    IMBI_LEADER_SYMBOLS,
    OCR_STOP,
    _candidate_tickers,
    analyze_frame_ocr,
    crop_watchlist_panel,
    extract_watchlist,
    sample_screener_seconds,
    sample_tail_seconds,
    symbols_from_boxes,
)
from app.screener_vision import _parse_symbol_json


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

    def test_reject_rapidocr_garbage(self) -> None:
        junk = ["KK", "LM", "SX", "A.M", "I.NE", "T.X", "CERA", "XY"]
        for j in junk:
            self.assertFalse(is_valid_us_ticker(j), j)
        cleaned = filter_symbols(junk + IMBI_LEADER_SYMBOLS[:5])
        for j in junk:
            self.assertNotIn(j, cleaned)
        self.assertIn("AXSM", cleaned)
        self.assertIn("GNS", cleaned)

    def test_imbi_leader_symbols_all_allowlisted(self) -> None:
        for sym in IMBI_LEADER_SYMBOLS:
            self.assertTrue(is_valid_us_ticker(sym), sym)
        # short real tickers only via allowlist
        self.assertTrue(is_valid_us_ticker("Z"))
        self.assertTrue(is_valid_us_ticker("GH"))
        self.assertFalse(is_valid_us_ticker("QQ"))  # not allowlisted 2-letter noise


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
        # OCR junk mixed in
        boxes.append(self._box("KK", 40, 420))
        boxes.append(self._box("A.M", 40, 460))
        # Detail panel on the right (BRZE @ 45.85)
        boxes.append(self._box("BRZE", 700, 100))
        boxes.append(self._box("45.85", 700, 140))
        boxes.append(self._box("Braze Inc", 700, 180, w=80))

        parsed = symbols_from_boxes(boxes)
        self.assertEqual(parsed["layout"], "screener_table")
        for sym in table:
            self.assertIn(sym, parsed["table_symbols"])
        self.assertNotIn("KK", parsed["table_symbols"])
        self.assertNotIn("A.M", parsed["table_symbols"])
        self.assertGreaterEqual(len(parsed["table_symbols"]), 6)

    def test_imbi_like_column_with_garbage_ocr(self) -> None:
        boxes = [self._box("Leader", 30, 10), self._box("Symbol", 30, 40)]
        for i, sym in enumerate(IMBI_LEADER_SYMBOLS):
            boxes.append(self._box(sym, 35, 70 + i * 28))
            boxes.append(self._box("1.2%", 180, 70 + i * 28))
        for i, junk in enumerate(["KK", "LM", "SX", "I.NE"]):
            boxes.append(self._box(junk, 35, 900 + i * 20))
        parsed = symbols_from_boxes(boxes)
        self.assertEqual(parsed["layout"], "screener_table")
        got = parsed["table_symbols"]
        for sym in IMBI_LEADER_SYMBOLS:
            self.assertIn(sym, got)
        for junk in ("KK", "LM", "SX", "I.NE"):
            self.assertNotIn(junk, got)

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

    def test_vision_json_parse(self) -> None:
        raw = '["AXSM", "GNS", "ICLR", "EVR"]'
        self.assertEqual(_parse_symbol_json(raw), ["AXSM", "GNS", "ICLR", "EVR"])
        fenced = '```json\n["SOFI","GH"]\n```'
        self.assertEqual(_parse_symbol_json(fenced), ["SOFI", "GH"])


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

            table_syms = list(IMBI_LEADER_SYMBOLS)

            def fake_analyze(path):
                # Alternate: strong table (+ OCR junk that must be stripped) vs detail BRZE
                if fake_analyze.i % 3 == 0:
                    fake_analyze.i += 1
                    return {
                        "engine": "mock",
                        "ocr": "Leader Symbol " + " ".join(table_syms) + " KK LM A.M",
                        "layout": "screener_table",
                        "score": 20.0,
                        "symbols": table_syms,
                        "table_symbols": table_syms,
                        "detail_symbols": [],
                        "raw_ocr_symbols": table_syms + ["KK", "LM", "A.M"],
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
                    "raw_ocr_symbols": ["BRZE"],
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
                mock.patch("app.watchlist_extract.crop_symbol_column", return_value=None),
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
                    use_vision=False,
                    force=True,
                )
                self.assertGreaterEqual(report["symbol_count"], 20)
                for sym in ("AXSM", "SOFI", "GH", "Z", "MNSO"):
                    self.assertIn(sym, report["symbols"])
                for junk in ("KK", "LM", "A.M", "SX"):
                    self.assertNotIn(junk, report["symbols"])
                self.assertNotEqual(report["symbols"], ["BRZE"])
                tv = tmp_path / "out" / f"{video_id}.txt"
                self.assertTrue(tv.exists())
                self.assertIn("NASDAQ:AXSM", tv.read_text(encoding="utf-8"))

    def test_vision_overrides_ocr_junk(self) -> None:
        video_id = "TESTVISN001"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_video = tmp_path / f"{video_id}.mp4"
            fake_video.write_bytes(b"\x00" * 64)

            def fake_extract(video_path, seconds, out_path):
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 3000)
                return out_path

            def fake_analyze(path):
                return {
                    "engine": "mock",
                    "ocr": "KK LM SX A.M garbage",
                    "layout": "screener_table",
                    "score": 8.0,
                    "symbols": [],
                    "table_symbols": [],
                    "detail_symbols": [],
                    "raw_ocr_symbols": ["KK", "LM", "SX", "A.M"],
                    "sections": ["leader"],
                    "prices": {},
                    "header_hits": 1,
                }

            vision_payload = {
                "available": True,
                "backend": "openai",
                "model": "mock",
                "symbols": IMBI_LEADER_SYMBOLS,
                "reads": [{"path": "x", "symbols": IMBI_LEADER_SYMBOLS, "error": None}],
            }

            with (
                mock.patch("app.watchlist_extract.download_video", return_value=fake_video),
                mock.patch("app.watchlist_extract.video_duration_sec", return_value=300.0),
                mock.patch("app.watchlist_extract.extract_frame", side_effect=fake_extract),
                mock.patch("app.watchlist_extract.analyze_frame_ocr", side_effect=fake_analyze),
                mock.patch("app.watchlist_extract.crop_symbol_column", return_value=None),
                mock.patch("app.watchlist_extract.speech_hint_seconds", return_value=[]),
                mock.patch("app.watchlist_extract.FRAMES_DIR", tmp_path / "frames"),
                mock.patch("app.watchlist_extract.SUMMARY_DIR", tmp_path / "summaries"),
                mock.patch("app.watchlist_extract.WATCHLIST_OUT_DIR", tmp_path / "out"),
                mock.patch("app.watchlist_extract.OUTPUT_DIR", tmp_path / "outputs"),
                mock.patch(
                    "app.screener_vision.vision_available",
                    return_value={"ok": True, "backend": "openai", "model": "mock"},
                ),
                mock.patch(
                    "app.screener_vision.read_best_screener_frames",
                    return_value=vision_payload,
                ),
            ):
                (tmp_path / "summaries").mkdir(parents=True, exist_ok=True)
                report = extract_watchlist(
                    video_id,
                    mode="screener",
                    max_frames=10,
                    use_vision=True,
                    vision_frames=2,
                    force=True,
                )
                self.assertEqual(report["symbol_source"], "vision")
                self.assertGreaterEqual(report["symbol_count"], 25)
                self.assertEqual(report["symbols"][:3], IMBI_LEADER_SYMBOLS[:3])
                for junk in ("KK", "LM", "SX", "A.M"):
                    self.assertNotIn(junk, report["symbols"])

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
