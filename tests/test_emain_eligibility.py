# -*- coding: utf-8 -*-
"""Eligibility and latest-file selection for Martin E_Main TradingView uploads.

The 2026-11-11 incident uploaded ``Martin_Luk_NA_E_Main.txt`` (TRACKING only)
as Active. These fixtures make that file lose to a complete dated list.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.emain_eligibility import (  # noqa: E402
    browser_cap_args,
    canonical_list_date,
    eligibility_problems,
    is_eligible_emain,
    main,
    prepare_emain_outputs,
    select_latest_emain,
)
from app.tradingview_export import write_tradingview_txt  # noqa: E402
from app.tv_cdp_upload import upload_watchlist_txt  # noqa: E402

# Exact body committed in e6d4eff for the bad Active list.
NA_TRACKING_ONLY = (
    "###TRACKING\n"
    "NASDAQ:DAY,NASDAQ:SKHY,NASDAQ:IT,NASDAQ:ON,NASDAQ:PEN,"
    "NASDAQ:INTC,NASDAQ:CE,NASDAQ:ARE,NASDAQ:ALL\n"
)

# Shaped like outputs/watchlists/Martin_Luk_2026-11-08_E_Main.txt
COMPLETE_DATED = (
    "###INDEXES\n"
    "NASDAQ:QQQ,AMEX:SPY,AMEX:IWM\n"
    "###LONGS\n"
    "CBOE:SSPC,AMEX:SOXS\n"
    "###SHORTS\n"
    "AMEX:SLV,AMEX:GLD,NYSE:BMNR,CBOE:DRAM,NYSE:BE,NASDAQ:AXTI,NASDAQ:SKHY\n"
    "###FOCUS\n"
    "AMEX:UVXY\n"
    "###TRACKING\n"
    "NASDAQ:SOXX,NASDAQ:SPCX,NASDAQ:SMH,NYSE:GEV,NASDAQ:TSLA,NASDAQ:CRWD\n"
)

MINIMAL_COMPLETE = (
    "###INDEXES\nNASDAQ:QQQ\n"
    "###LONGS\nAMEX:SOXS\n"
    "###SHORTS\nAMEX:SLV\n"
    "###FOCUS\nAMEX:UVXY\n"
)


def _touch(path: Path, when: float) -> None:
    os.utime(path, (when, when))


class DateAndSectionTests(unittest.TestCase):
    def test_canonical_date_rejects_na_and_impossible_days(self) -> None:
        self.assertEqual(canonical_list_date("2026-11-08"), "2026-11-08")
        self.assertEqual(canonical_list_date("20261028"), "2026-10-28")
        self.assertEqual(canonical_list_date("2024-02-29"), "2024-02-29")
        self.assertIsNone(canonical_list_date("NA"))
        self.assertIsNone(canonical_list_date("na"))
        self.assertIsNone(canonical_list_date(""))
        self.assertIsNone(canonical_list_date(None))
        self.assertIsNone(canonical_list_date("unknown-date"))
        self.assertIsNone(canonical_list_date("2026-02-31"))
        self.assertIsNone(canonical_list_date("2026-02-29"))

    def test_na_tracking_only_is_ineligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Martin_Luk_NA_E_Main.txt"
            path.write_text(NA_TRACKING_ONLY, encoding="utf-8")
            problems = eligibility_problems(path)
            self.assertFalse(is_eligible_emain(path))
        blob = " ".join(problems)
        self.assertIn("date is NA", blob)
        self.assertIn("###INDEXES", blob)
        self.assertIn("###LONGS", blob)
        self.assertIn("###SHORTS", blob)
        self.assertIn("###FOCUS", blob)
        self.assertIn("###TRACKING", blob)

    def test_complete_dated_is_eligible_without_requiring_tracking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Martin_Luk_2026-11-08_E_Main.txt"
            path.write_text(MINIMAL_COMPLETE, encoding="utf-8")
            self.assertEqual(eligibility_problems(path), [])
            path.write_text(COMPLETE_DATED, encoding="utf-8")
            self.assertEqual(eligibility_problems(path), [])

    def test_empty_required_section_is_ineligible(self) -> None:
        text = (
            "###INDEXES\nNASDAQ:QQQ\n"
            "###LONGS\nAMEX:SOXS\n"
            "###SHORTS\nAMEX:SLV\n"
            "###FOCUS\n"
            "###TRACKING\nNASDAQ:SOXX\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Martin_Luk_2026-11-08_E_Main.txt"
            path.write_text(text, encoding="utf-8")
            blob = " ".join(eligibility_problems(path))
        self.assertIn("empty required sections", blob)
        self.assertIn("###FOCUS", blob)

    def test_video_id_file_is_ineligible_even_when_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "YXWBRbXQGBk.E_Main.txt"
            path.write_text(COMPLETE_DATED, encoding="utf-8")
            blob = " ".join(eligibility_problems(path))
        self.assertIn("not Martin_Luk_YYYY-MM-DD_E_Main", blob)

    def test_browser_cap_omits_upload_for_na(self) -> None:
        extra, why = browser_cap_args("NA")
        self.assertEqual(extra, ["--date", "NA"])
        self.assertNotIn("--upload", extra)
        self.assertIn("NA", why or "")
        extra, why = browser_cap_args("20261028")
        self.assertEqual(extra, ["--date", "2026-10-28", "--upload"])
        self.assertIsNone(why)
        extra, why = browser_cap_args("2026-02-31")
        self.assertNotIn("--upload", extra)
        self.assertIsNotNone(why)


class LatestSelectionTests(unittest.TestCase):
    def _write(self, directory: Path, name: str, body: str, when: float) -> Path:
        path = directory / name
        path.write_text(body, encoding="utf-8")
        _touch(path, when)
        return path

    def test_na_loses_to_dated_complete_regardless_of_mtime(self) -> None:
        now = 1_700_000_000.0
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self._write(directory, "Martin_Luk_NA_E_Main.txt", NA_TRACKING_ONLY, now + 500)
            self._write(directory, "YXWBRbXQGBk.E_Main.txt", NA_TRACKING_ONLY, now + 400)
            self._write(
                directory, "Martin_Luk_2026-11-10_E_Main.txt", NA_TRACKING_ONLY, now + 300
            )
            self._write(
                directory, "Martin_Luk_2026-02-31_E_Main.txt", COMPLETE_DATED, now + 250
            )
            self._write(
                directory, "Martin_Luk_unknown-date_E_Main.txt", COMPLETE_DATED, now + 220
            )
            self._write(
                directory, "Martin_Luk_2026-11-04_E_Main.txt", COMPLETE_DATED, now + 200
            )
            winner_file = self._write(
                directory, "Martin_Luk_2026-11-08_E_Main.txt", COMPLETE_DATED, now - 10_000
            )
            # Newest mtime in the folder is the NA file. Date order must win.
            self.assertGreater(
                (directory / "Martin_Luk_NA_E_Main.txt").stat().st_mtime,
                winner_file.stat().st_mtime,
            )
            winner, notes = select_latest_emain(directory)
            self.assertIsNotNone(winner)
            assert winner is not None
            self.assertEqual(winner.name, "Martin_Luk_2026-11-08_E_Main.txt")
            blob = "\n".join(notes)
            self.assertIn("skip Martin_Luk_NA_E_Main.txt", blob)
            self.assertIn("date is NA", blob)
            self.assertIn("skip YXWBRbXQGBk.E_Main.txt", blob)
            self.assertIn("skip Martin_Luk_2026-11-10_E_Main.txt", blob)
            self.assertIn("mtime ignored", blob)

            newer = self._write(
                directory, "Martin_Luk_2026-11-09_E_Main.txt", COMPLETE_DATED, now - 20_000
            )
            self.assertLess(newer.stat().st_mtime, winner_file.stat().st_mtime)
            winner, _notes = select_latest_emain(directory)
            assert winner is not None
            self.assertEqual(winner.name, "Martin_Luk_2026-11-09_E_Main.txt")

    def test_repo_incident_files_select_2026_11_08(self) -> None:
        wl = ROOT / "outputs" / "watchlists"
        na = wl / "Martin_Luk_NA_E_Main.txt"
        good = wl / "Martin_Luk_2026-11-08_E_Main.txt"
        self.assertTrue(na.is_file())
        self.assertTrue(good.is_file())
        self.assertTrue(eligibility_problems(na))
        self.assertEqual(eligibility_problems(good), [])
        self.assertEqual(na.read_text(encoding="utf-8").splitlines()[0], "###TRACKING")
        winner, notes = select_latest_emain(wl)
        self.assertIsNotNone(winner)
        assert winner is not None
        self.assertEqual(winner.name, "Martin_Luk_2026-11-08_E_Main.txt")
        blob = "\n".join(notes)
        self.assertIn("skip Martin_Luk_NA_E_Main.txt", blob)
        self.assertIn("skip YXWBRbXQGBk.E_Main.txt", blob)
        self.assertNotIn("select Martin_Luk_NA_E_Main.txt", blob)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--dry-run", "--watchlists", str(wl)])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("select Martin_Luk_2026-11-08_E_Main.txt", out)
        self.assertIn(f"dry-run: would upload {good}", out)
        self.assertIn("skip Martin_Luk_NA_E_Main.txt", out)


class PublishAndUploadGateTests(unittest.TestCase):
    def test_prepare_keeps_na_body_off_the_selectable_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            info = prepare_emain_outputs(
                tmp,
                video_id="YXWBRbXQGBk",
                vod_date="NA",
                body=NA_TRACKING_ONLY,
            )
            directory = Path(tmp)
            self.assertFalse((directory / "Martin_Luk_NA_E_Main.txt").exists())
            self.assertTrue(info["debug_path"].is_file())
            self.assertIsNone(info["dated_path"])
            self.assertIsNone(info["upload_path"])
            blob = " ".join(info["problems"])
            self.assertIn("date is NA", blob)
            self.assertIn("###INDEXES", blob)

    def test_prepare_keeps_incomplete_dated_file_but_does_not_upload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            info = prepare_emain_outputs(
                tmp,
                video_id="YXWBRbXQGBk",
                vod_date="2026-10-26",
                body=NA_TRACKING_ONLY,
            )
            self.assertIsNotNone(info["dated_path"])
            self.assertTrue(info["dated_path"].is_file())
            self.assertEqual(info["dated_path"].name, "Martin_Luk_2026-10-26_E_Main.txt")
            self.assertIsNone(info["upload_path"])
            self.assertTrue(info["problems"])

    def test_prepare_complete_dated_is_uploadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            info = prepare_emain_outputs(
                tmp,
                video_id="abc",
                vod_date="20261108",
                body=COMPLETE_DATED,
            )
            self.assertEqual(info["problems"], [])
            self.assertEqual(info["upload_path"].name, "Martin_Luk_2026-11-08_E_Main.txt")

    def test_write_tradingview_txt_does_not_emit_na_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            video = directory / "YXWBRbXQGBk.txt"
            got = write_tradingview_txt(
                video,
                buckets={"TRACKING": ["DAY", "SKHY"]},
                date_iso="NA",
                video_id="YXWBRbXQGBk",
                emain=True,
                also_dated_filename=True,
            )
            self.assertEqual(got.name, "YXWBRbXQGBk.txt")
            self.assertFalse((directory / "Martin_Luk_NA_E_Main.txt").exists())
            self.assertEqual(list(directory.glob("Martin_Luk_*")), [])

    def test_upload_refuses_na_and_incomplete_without_calling_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            na = directory / "Martin_Luk_NA_E_Main.txt"
            na.write_text(NA_TRACKING_ONLY, encoding="utf-8")
            incomplete = directory / "Martin_Luk_2026-11-10_E_Main.txt"
            incomplete.write_text(NA_TRACKING_ONLY, encoding="utf-8")
            video = directory / "YXWBRbXQGBk.E_Main.txt"
            video.write_text(COMPLETE_DATED, encoding="utf-8")
            with (
                mock.patch("app.tv_cdp_upload.subprocess.run") as run,
                mock.patch("app.tv_cdp_upload.ensure_cdp") as cdp,
            ):
                for path in (na, incomplete, video):
                    got = upload_watchlist_txt(path, ensure=True)
                    self.assertFalse(got["ok"], path.name)
                    self.assertTrue(got["skipped"], path.name)
                    self.assertTrue(got["reason"], path.name)
            run.assert_not_called()
            cdp.assert_not_called()

    def test_reassert_uploads_dated_winner_not_na(self) -> None:
        now = 1_700_000_000.0
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            na = directory / "Martin_Luk_NA_E_Main.txt"
            na.write_text(NA_TRACKING_ONLY, encoding="utf-8")
            _touch(na, now + 50)
            good = directory / "Martin_Luk_2026-11-08_E_Main.txt"
            good.write_text(COMPLETE_DATED, encoding="utf-8")
            _touch(good, now - 50)
            with mock.patch(
                "app.tv_cdp_upload.upload_watchlist_txt",
                return_value={"ok": True, "listStem": good.stem},
            ) as upload:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = main(["--watchlists", str(directory)])
            self.assertEqual(rc, 0)
            upload.assert_called_once()
            self.assertEqual(Path(upload.call_args.args[0]).name, good.name)
            self.assertIn("skip Martin_Luk_NA_E_Main.txt", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
