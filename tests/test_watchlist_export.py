# -*- coding: utf-8 -*-
"""Unit tests for Martin tail-watchlist sampling + TradingView export."""
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
    crop_watchlist_panel,
    extract_watchlist,
    sample_tail_seconds,
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
        self.assertIn("NASDAQ:HOOD", text)
        # deduped, comma-separated on one line
        body = [ln for ln in text.splitlines() if ln and not ln.startswith("###")][0]
        self.assertEqual(body.count("NASDAQ:NVDA"), 1)
        self.assertIn(",", body)


class TailSampleTests(unittest.TestCase):
    def test_sample_last_10_min(self) -> None:
        # 2h stream
        times = sample_tail_seconds(7200.0, last_minutes=10.0, interval_sec=20.0, end_pad_sec=5.0)
        self.assertTrue(times)
        self.assertGreaterEqual(times[0], 7200 - 600 - 1)
        self.assertLessEqual(times[-1], 7200 - 5 + 1)
        # roughly every 20s
        gaps = [b - a for a, b in zip(times, times[1:])]
        self.assertTrue(all(15 <= g <= 25 for g in gaps[:-1]) or len(gaps) < 2)

    def test_short_vod(self) -> None:
        times = sample_tail_seconds(120.0, last_minutes=10.0, interval_sec=30.0)
        self.assertTrue(times)
        self.assertEqual(times[0], 0.0)


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


class SyntheticPipelineTests(unittest.TestCase):
    def test_extract_watchlist_writes_tv_txt(self) -> None:
        """End-to-end without YouTube: fake duration + mocked OCR per frame."""
        video_id = "TESTWLIST01"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_video = tmp_path / f"{video_id}.mp4"
            fake_video.write_bytes(b"\x00" * 64)

            def fake_extract(video_path, seconds, out_path):
                out_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    from PIL import Image, ImageDraw

                    im = Image.new("RGB", (960, 540), (10, 10, 10))
                    d = ImageDraw.Draw(im)
                    d.rectangle((620, 40, 940, 500), fill=(30, 30, 30))
                    d.text((640, 80), "NVDA", fill=(240, 240, 240))
                    d.text((640, 120), "HOOD", fill=(240, 240, 240))
                    d.text((640, 160), "CRWD", fill=(240, 240, 240))
                    im.save(out_path, quality=90)
                except ImportError:
                    out_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 3000)
                return out_path

            ocr_cycle = [
                ("NVDA HOOD leading", "mock"),
                ("NVDA HOOD CRWD", "mock"),
                ("HOOD CRWD mediocre", "mock"),
            ]

            def fake_ocr(_path):
                # rotate so aggregation sees repeats
                text, eng = ocr_cycle[fake_ocr.i % len(ocr_cycle)]
                fake_ocr.i += 1
                return text, eng

            fake_ocr.i = 0

            with (
                mock.patch("app.watchlist_extract.download_video", return_value=fake_video),
                mock.patch("app.watchlist_extract.video_duration_sec", return_value=600.0),
                mock.patch("app.watchlist_extract.extract_frame", side_effect=fake_extract),
                mock.patch("app.watchlist_extract.ocr_image", side_effect=fake_ocr),
                mock.patch("app.watchlist_extract.FRAMES_DIR", tmp_path / "frames"),
                mock.patch("app.watchlist_extract.SUMMARY_DIR", tmp_path / "summaries"),
                mock.patch("app.watchlist_extract.WATCHLIST_OUT_DIR", tmp_path / "out"),
                mock.patch("app.watchlist_extract.OUTPUT_DIR", tmp_path / "outputs"),
            ):
                (tmp_path / "summaries").mkdir(parents=True, exist_ok=True)
                report = extract_watchlist(
                    video_id,
                    last_minutes=2.0,
                    interval_sec=30.0,
                    min_hits=1,
                    force=True,
                )
                self.assertGreaterEqual(report["symbol_count"], 2)
                self.assertIn("NVDA", report["symbols"])
                self.assertIn("HOOD", report["symbols"])
                tv = tmp_path / "out" / f"{video_id}.txt"
                self.assertTrue(tv.exists())
                body = tv.read_text(encoding="utf-8")
                self.assertIn("###", body)
                self.assertIn("NASDAQ:NVDA", body)
                slim = tmp_path / "summaries" / f"{video_id}.watchlist.json"
                self.assertTrue(slim.exists())

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


if __name__ == "__main__":
    unittest.main()
