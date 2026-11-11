# -*- coding: utf-8 -*-
"""Unit tests for TradingView CDP upload helper (mocked; no real CDP)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.tv_cdp_upload import (  # noqa: E402
    cdp_ready,
    maybe_upload_after_extract,
    upload_watchlist_txt,
)


class CdpReadyTests(unittest.TestCase):
    def test_cdp_ready_ok(self) -> None:
        fake = mock.MagicMock()
        fake.__enter__.return_value = fake
        fake.__exit__.return_value = False
        resp = mock.MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"Browser": "Chrome/test", "webSocketDebuggerUrl": "ws://x"}
        fake.get.return_value = resp
        with mock.patch("app.tv_cdp_upload.httpx.Client", return_value=fake):
            got = cdp_ready(9222)
        self.assertTrue(got["ok"])
        self.assertEqual(got["port"], 9222)

    def test_cdp_ready_down(self) -> None:
        with mock.patch(
            "app.tv_cdp_upload.httpx.Client",
            side_effect=OSError("connection refused"),
        ):
            got = cdp_ready(9222)
        self.assertFalse(got["ok"])


class UploadWatchlistTxtTests(unittest.TestCase):
    def test_upload_parses_json_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "scripts" / "tv_upload_watchlist.js"
            script.parent.mkdir(parents=True)
            script.write_text("// stub\n", encoding="utf-8")
            txt = root / "Martin_Luk_2026-10-28_E_Main.txt"
            txt.write_text(
                "###INDEXES\nNASDAQ:QQQ\n"
                "###LONGS\nAMEX:SOXS\n"
                "###SHORTS\nAMEX:SLV\n"
                "###FOCUS\nAMEX:UVXY\n",
                encoding="utf-8",
            )

            payload = {
                "ok": True,
                "txt": str(txt),
                "listStem": "Martin_Luk_2026-10-28_E_Main",
                "importResult": {"sections": 5},
            }

            completed = mock.MagicMock()
            completed.returncode = 0
            completed.stdout = json.dumps(payload)
            completed.stderr = ""

            with (
                mock.patch("app.tv_cdp_upload.ensure_cdp", return_value={"ok": True, "port": 9222}),
                mock.patch("app.tv_cdp_upload.subprocess.run", return_value=completed) as run,
                mock.patch("app.tv_cdp_upload.node_bin", return_value="node"),
            ):
                got = upload_watchlist_txt(txt, root=root, ensure=True)

            self.assertTrue(got["ok"])
            self.assertEqual(got["listStem"], "Martin_Luk_2026-10-28_E_Main")
            self.assertEqual(got["importResult"], {"sections": 5})
            cmd = run.call_args.args[0]
            self.assertEqual(cmd[0], "node")
            self.assertTrue(str(cmd[1]).endswith("tv_upload_watchlist.js"))
            self.assertEqual(Path(cmd[2]), txt.resolve())

    def test_upload_missing_txt(self) -> None:
        got = upload_watchlist_txt("/no/such/Martin_Luk_2026-10-28_E_Main.txt", ensure=False)
        self.assertFalse(got["ok"])
        self.assertEqual(got["listStem"], "Martin_Luk_2026-10-28_E_Main")

    def test_maybe_upload_skipped_without_env(self) -> None:
        with mock.patch("app.tv_cdp_upload.tv_upload_enabled", return_value=False):
            got = maybe_upload_after_extract("x.txt")
        self.assertTrue(got.get("skipped"))
        self.assertFalse(got.get("ok"))

    def test_non_json_stdout_is_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "scripts" / "tv_upload_watchlist.js"
            script.parent.mkdir(parents=True)
            script.write_text("// stub\n", encoding="utf-8")
            txt = root / "Martin_Luk_2026-10-28_E_Main.txt"
            txt.write_text(
                "###INDEXES\nNASDAQ:QQQ\n"
                "###LONGS\nAMEX:SOXS\n"
                "###SHORTS\nAMEX:SLV\n"
                "###FOCUS\nAMEX:UVXY\n",
                encoding="utf-8",
            )
            completed = mock.MagicMock()
            completed.returncode = 0
            completed.stdout = "not json"
            completed.stderr = ""
            with (
                mock.patch("app.tv_cdp_upload.ensure_cdp", return_value={"ok": True}),
                mock.patch("app.tv_cdp_upload.subprocess.run", return_value=completed),
                mock.patch("app.tv_cdp_upload.node_bin", return_value="node"),
            ):
                got = upload_watchlist_txt(txt, root=root)
            self.assertFalse(got["ok"])
            self.assertIn("non-JSON", got.get("error") or "")


if __name__ == "__main__":
    unittest.main()
