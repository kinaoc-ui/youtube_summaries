# -*- coding: utf-8 -*-
"""Unit tests for E_Main sidebar watchlist OCR + TradingView export."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.tradingview_export import (
    IMBI_EMAIN_BUCKETS,
    IMBI_EMAIN_DATE,
    IMBI_EMAIN_TXT,
    EXCHANGE_FOR_TICKER,
    format_emain_watchlist_txt,
    format_watchlist_txt,
    list_display_name,
    list_filename,
    tv_symbol,
)
from app.us_tickers import filter_symbols, is_valid_us_ticker
from app.vod_date import resolve_vod_date
from app.watchlist_extract import (
    IMBI_LEADER_SYMBOLS,
    OCR_STOP,
    _candidate_tickers,
    analyze_frame_ocr,
    crop_watchlist_panel,
    parse_sidebar_sections_from_boxes,
    sample_screener_seconds,
    sample_tail_seconds,
    symbols_from_boxes,
)
from app.screener_vision import _parse_symbol_json, parse_sidebar_json


class TradingViewExportTests(unittest.TestCase):
    def test_tv_symbol_emain_exchanges(self) -> None:
        self.assertEqual(tv_symbol("QQQ"), "NASDAQ:QQQ")
        self.assertEqual(tv_symbol("SPY"), "AMEX:SPY")
        self.assertEqual(tv_symbol("USD"), "AMEX:USD")
        self.assertEqual(tv_symbol("SSPC"), "CBOE:SSPC")
        self.assertEqual(tv_symbol("SOXS"), "AMEX:SOXS")
        self.assertEqual(tv_symbol("BMNR"), "NYSE:BMNR")
        self.assertEqual(tv_symbol("DRAM"), "CBOE:DRAM")
        self.assertEqual(tv_symbol("UVXY"), "AMEX:UVXY")
        self.assertEqual(tv_symbol("SNDK"), "NASDAQ:SNDK")
        self.assertEqual(tv_symbol("SKHY"), "NASDAQ:SKHY")
        self.assertEqual(tv_symbol("SKHY", "KRX"), "KRX:000660")

    def test_emain_short_headers_canonical(self) -> None:
        """One watchlist file: short ###SECTION headers; dated name is metadata."""
        text = format_emain_watchlist_txt(IMBI_EMAIN_BUCKETS)
        self.assertEqual(text, IMBI_EMAIN_TXT)
        self.assertIn("###INDEXES\n", text)
        self.assertIn("###LONGS\n", text)
        self.assertIn("###SHORTS\n", text)
        self.assertIn("###FOCUS\n", text)
        self.assertIn("###TRACKING\n", text)
        # Must NOT repeat dated list name in every header
        self.assertNotIn("###Martin Luk", text)
        self.assertNotIn("E_Main INDEXES", text)
        self.assertIn("AMEX:USD", text)
        self.assertNotIn("AMEX:USO", text)
        self.assertIn("NYSE:BMNR", text)
        self.assertNotIn("BWNR", text)
        self.assertIn("NASDAQ:SNDK", text)
        self.assertNotIn("SNOK", text)
        self.assertEqual(
            list_display_name(date_iso=IMBI_EMAIN_DATE),
            "Martin Luk 2026-10-28 E_Main",
        )
        self.assertEqual(
            list_filename(IMBI_EMAIN_DATE),
            "Martin_Luk_2026-10-28_E_Main.txt",
        )

    def test_format_watchlist_txt_sections_dict(self) -> None:
        text = format_watchlist_txt(sections={"INDEXES": ["QQQ"], "LONGS": ["USD"]})
        self.assertEqual(text.splitlines()[0], "###INDEXES")
        self.assertIn("AMEX:USD", text)

    def test_sample_outputs_match_canonical(self) -> None:
        for name in ("iMBI3ZcQ6sU.txt", "Martin_Luk_2026-10-28_E_Main.txt"):
            path = ROOT / "outputs" / "watchlists" / name
            self.assertTrue(path.exists(), name)
            self.assertEqual(path.read_text(encoding="utf-8"), IMBI_EMAIN_TXT)

    def test_vod_date_from_upload_date(self) -> None:
        self.assertEqual(resolve_vod_date("iMBI3ZcQ6sU", hint="20261028"), "2026-10-28")


class SidebarParseTests(unittest.TestCase):
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

    def test_parse_emain_sidebar_sections(self) -> None:
        """Right-column E_Main headers → INDEXES/LONGS/SHORTS/FOCUS/TRACKING."""
        boxes = [self._box("E_Main", 700, 10)]
        y = 40
        sections = [
            ("INDEXES", ["QQQ", "SPY", "IWM"]),
            ("LONGS", ["USD", "SSPC", "SOXS"]),
            ("SHORTS", ["SLV", "GLD", "BMNR", "COIN"]),
            ("FOCUS", ["DRAM", "UVXY"]),
            ("TRACKING", ["SOXX", "SPCX", "SNDK", "SKHY", "GEV", "VRT", "AXTI"]),
        ]
        for header, syms in sections:
            boxes.append(self._box(header, 700, y))
            y += 24
            for sym in syms:
                boxes.append(self._box(sym, 700, y))
                y += 22
        parsed = parse_sidebar_sections_from_boxes(boxes)
        self.assertTrue(parsed["sidebar"])
        self.assertEqual(parsed["buckets"]["INDEXES"], ["QQQ", "SPY", "IWM"])
        self.assertEqual(parsed["buckets"]["LONGS"], ["USD", "SSPC", "SOXS"])
        self.assertEqual(parsed["buckets"]["SHORTS"][:2], ["SLV", "GLD"])
        self.assertIn("BMNR", parsed["buckets"]["SHORTS"])
        self.assertEqual(parsed["buckets"]["FOCUS"], ["DRAM", "UVXY"])
        self.assertIn("SNDK", parsed["buckets"]["TRACKING"])
        self.assertIn("SKHY", parsed["buckets"]["TRACKING"])

    def test_long_alias_maps_to_longs(self) -> None:
        boxes = [
            self._box("LONG", 700, 40),
            self._box("USD", 700, 70),
            self._box("SHORT", 700, 120),
            self._box("COIN", 700, 150),
        ]
        parsed = parse_sidebar_sections_from_boxes(boxes)
        self.assertTrue(parsed["sidebar"])
        self.assertEqual(parsed["buckets"]["LONGS"], ["USD"])
        self.assertEqual(parsed["buckets"]["SHORTS"], ["COIN"])

    def test_potent_table_alone_is_not_sidebar(self) -> None:
        """Left Symbol column without E_Main headers must not invent sections."""
        boxes = [self._box("Symbol", 40, 40), self._box("Potent", 40, 10)]
        for i, sym in enumerate(["AXSM", "GNS", "ICLR", "EVR", "WMG"]):
            boxes.append(self._box(sym, 40, 80 + i * 28))
        parsed = parse_sidebar_sections_from_boxes(boxes)
        self.assertFalse(parsed["sidebar"])

    def test_usd_not_ocr_stop(self) -> None:
        self.assertNotIn("USD", OCR_STOP)
        self.assertTrue(is_valid_us_ticker("USD"))
        self.assertTrue(is_valid_us_ticker("BMNR"))
        self.assertTrue(is_valid_us_ticker("SNDK"))
        self.assertTrue(is_valid_us_ticker("DRAM"))


class VisionJsonTests(unittest.TestCase):
    def test_parse_sidebar_json_emain(self) -> None:
        raw = (
            '{"indexes":["QQQ","SPY"],"longs":["USD","SSPC"],'
            '"shorts":["BMNR"],"focus":["DRAM"],"tracking":["SNDK"]}'
        )
        got = parse_sidebar_json(raw)
        self.assertEqual(got["INDEXES"], ["QQQ", "SPY"])
        self.assertEqual(got["LONGS"], ["USD", "SSPC"])
        self.assertEqual(got["SHORTS"], ["BMNR"])
        self.assertEqual(got["FOCUS"], ["DRAM"])
        self.assertEqual(got["TRACKING"], ["SNDK"])

    def test_flat_potent_json(self) -> None:
        self.assertEqual(_parse_symbol_json('["AXSM","GNS"]'), ["AXSM", "GNS"])


class TailSampleTests(unittest.TestCase):
    def test_sample_last_10_min(self) -> None:
        times = sample_tail_seconds(7200.0, last_minutes=10.0, interval_sec=20.0, end_pad_sec=5.0)
        self.assertTrue(times)
        self.assertGreaterEqual(times[0], 7200 - 600 - 1)

    def test_screener_samples_whole_vod(self) -> None:
        times = sample_screener_seconds(5300.0, coarse_interval=60.0, max_frames=80)
        self.assertLess(times[0], 120.0)
        self.assertGreater(times[-1], 5000.0)


class OcrTickerFilterTests(unittest.TestCase):
    def test_reject_rapidocr_garbage(self) -> None:
        junk = ["KK", "LM", "SX", "A.M", "I.NE"]
        for j in junk:
            self.assertFalse(is_valid_us_ticker(j), j)
        cleaned = filter_symbols(junk + ["QQQ", "USD", "BMNR"])
        self.assertEqual(cleaned, ["QQQ", "USD", "BMNR"])

    def test_imbi_potent_still_allowlisted(self) -> None:
        for sym in IMBI_LEADER_SYMBOLS:
            self.assertTrue(is_valid_us_ticker(sym), sym)


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

    def test_leader_table_symbol_column(self) -> None:
        boxes = [
            self._box("Leader", 40, 20),
            self._box("Symbol", 40, 50),
        ]
        table = ["NVDA", "HOOD", "CRWD", "ALAB", "AMD", "SMCI", "ARM", "BRZE"]
        for i, sym in enumerate(table):
            boxes.append(self._box(sym, 40, 100 + i * 40))
        parsed = symbols_from_boxes(boxes)
        self.assertEqual(parsed["layout"], "screener_table")
        for sym in table:
            self.assertIn(sym, parsed["table_symbols"])


class CropTests(unittest.TestCase):
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
