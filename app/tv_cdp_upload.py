# -*- coding: utf-8 -*-
"""Post-extract TradingView Desktop CDP upload for Martin E_Main .txt files.

Calls NineEdge ``scripts/tv_upload_watchlist.js`` over Chrome DevTools Protocol
(port 9222). Preserves ###INDEXES / ###LONGS / … section headers.

Does NOT use flat MCP ``watchlist_add`` / NineEdge ``import_watchlist_from_txt``.

Enable (Windows local):
  set TUBEON_TV_UPLOAD=1
  set TUBEON_TV_SCREENING_ROOT=C:\\Users\\kinao\\OneDrive\\桌面\\stock\\screening
  :: optional
  set TUBEON_TV_CDP_PORT=9222
  set TUBEON_TV_AUTO_LAUNCH=1
  set TUBEON_TV_NODE=node

Then either launch CDP first:
  {screening}\\launch_tv_debug.bat
or rely on AUTO_LAUNCH.

Upload argv is only the absolute .txt path; listStem = filename without .txt
(e.g. Martin_Luk_2026-10-28_E_Main).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from .config import settings

DEFAULT_SCREENING_ROOT = r"C:\Users\kinao\OneDrive\桌面\stock\screening"
DEFAULT_CDP_PORT = 9222
UPLOAD_SCRIPT_REL = Path("scripts") / "tv_upload_watchlist.js"
LAUNCH_BAT = "launch_tv_debug.bat"


def tv_upload_enabled() -> bool:
    """True when TUBEON_TV_UPLOAD is truthy (1/true/yes/on)."""
    raw = (getattr(settings, "tv_upload", None) or os.environ.get("TUBEON_TV_UPLOAD") or "").strip()
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def screening_root() -> Path:
    raw = (
        getattr(settings, "tv_screening_root", None)
        or os.environ.get("TUBEON_TV_SCREENING_ROOT")
        or DEFAULT_SCREENING_ROOT
    )
    return Path(str(raw).strip().strip('"'))


def cdp_port() -> int:
    try:
        return int(
            getattr(settings, "tv_cdp_port", None)
            or os.environ.get("TUBEON_TV_CDP_PORT")
            or DEFAULT_CDP_PORT
        )
    except (TypeError, ValueError):
        return DEFAULT_CDP_PORT


def node_bin() -> str:
    raw = (
        getattr(settings, "tv_node", None)
        or os.environ.get("TUBEON_TV_NODE")
        or ""
    ).strip()
    if raw:
        return raw
    return shutil.which("node") or "node"


def auto_launch_enabled() -> bool:
    raw = (
        getattr(settings, "tv_auto_launch", None)
        or os.environ.get("TUBEON_TV_AUTO_LAUNCH")
        or ""
    )
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def cdp_ready(port: int | None = None, *, timeout: float = 2.0) -> dict[str, Any]:
    """Probe http://127.0.0.1:{port}/json/version."""
    port = DEFAULT_CDP_PORT if port is None else int(port)
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()
        return {"ok": True, "port": port, "version": data}
    except Exception as e:
        return {"ok": False, "port": port, "error": str(e)}


def launch_tv_debug(*, root: Path | None = None) -> dict[str, Any]:
    """Spawn NineEdge ``launch_tv_debug.bat`` (Windows). Non-blocking."""
    root = root or screening_root()
    bat = root / LAUNCH_BAT
    if not bat.exists():
        return {"ok": False, "error": f"missing launch bat: {bat}"}
    if os.name != "nt":
        return {
            "ok": False,
            "error": f"launch_tv_debug.bat is Windows-only (os.name={os.name})",
            "bat": str(bat),
        }
    flags = 0
    for name in (
        "CREATE_NEW_PROCESS_GROUP",
        "DETACHED_PROCESS",
        "CREATE_BREAKAWAY_FROM_JOB",
    ):
        flags |= int(getattr(subprocess, name, 0) or 0)
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat)],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=False,
            creationflags=flags,
        )
        return {"ok": True, "bat": str(bat), "cwd": str(root)}
    except OSError as e:
        return {"ok": False, "error": str(e), "bat": str(bat)}


def ensure_cdp(
    *,
    port: int | None = None,
    auto_launch: bool | None = None,
    wait_sec: float = 25.0,
    poll_sec: float = 1.5,
) -> dict[str, Any]:
    """Return ready CDP probe; optionally launch TV debug and wait."""
    port = cdp_port() if port is None else int(port)
    probe = cdp_ready(port)
    if probe.get("ok"):
        return probe
    do_launch = auto_launch_enabled() if auto_launch is None else bool(auto_launch)
    if not do_launch:
        return {**probe, "launched": False}
    launched = launch_tv_debug()
    deadline = time.time() + max(0.0, wait_sec)
    while time.time() < deadline:
        time.sleep(max(0.2, poll_sec))
        probe = cdp_ready(port)
        if probe.get("ok"):
            return {**probe, "launched": True, "launch": launched}
    return {
        "ok": False,
        "port": port,
        "launched": True,
        "launch": launched,
        "error": probe.get("error") or f"CDP not ready on {port} after {wait_sec}s",
    }


def upload_script_path(root: Path | None = None) -> Path:
    return (root or screening_root()) / UPLOAD_SCRIPT_REL


def _node_env() -> dict[str, str]:
    """NODE_PATH so chrome-remote-interface resolves from tradingview-mcp."""
    env = dict(os.environ)
    home = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or "").expanduser()
    mcp_nm = home / "tradingview-mcp" / "node_modules"
    extra = str(mcp_nm) if mcp_nm.is_dir() else ""
    existing = env.get("NODE_PATH", "")
    parts = [p for p in (extra, existing) if p]
    if parts:
        env["NODE_PATH"] = os.pathsep.join(parts)
    return env


def upload_watchlist_txt(
    txt_path: Path | str,
    *,
    root: Path | None = None,
    ensure: bool = True,
    timeout_sec: float = 120.0,
) -> dict[str, Any]:
    """Run ``node scripts/tv_upload_watchlist.js <abs txt>``; parse JSON stdout.

    Success shape (from js):
      {"ok": true, "txt": ..., "listStem": ..., "importResult": ...}
    """
    path = Path(txt_path).expanduser().resolve()
    list_stem = path.stem
    if not path.exists():
        return {"ok": False, "txt": str(path), "listStem": list_stem, "error": "txt missing"}
    if path.suffix.lower() != ".txt":
        return {
            "ok": False,
            "txt": str(path),
            "listStem": list_stem,
            "error": "expected .txt path",
        }

    root = root or screening_root()
    script = upload_script_path(root)
    if not script.exists():
        return {
            "ok": False,
            "txt": str(path),
            "listStem": list_stem,
            "error": f"upload script missing: {script}",
            "screening_root": str(root),
        }

    if ensure:
        ready = ensure_cdp(port=cdp_port())
        if not ready.get("ok"):
            return {
                "ok": False,
                "txt": str(path),
                "listStem": list_stem,
                "error": ready.get("error") or "CDP not ready",
                "cdp": ready,
            }

    cmd = [node_bin(), str(script), str(path)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            env=_node_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "txt": str(path),
            "listStem": list_stem,
            "error": f"timeout after {timeout_sec}s",
            "cmd": cmd,
            "stdout": (e.stdout or "")[:2000] if isinstance(e.stdout, str) else "",
            "stderr": (e.stderr or "")[:2000] if isinstance(e.stderr, str) else "",
        }
    except OSError as e:
        return {
            "ok": False,
            "txt": str(path),
            "listStem": list_stem,
            "error": str(e),
            "cmd": cmd,
        }

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    parsed: dict[str, Any] | None = None
    # Prefer last JSON object in stdout
    for blob in reversed([ln.strip() for ln in stdout.splitlines() if ln.strip()] or [stdout]):
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            parsed = data
            break
    if parsed is None and stdout:
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                parsed = data
        except json.JSONDecodeError:
            parsed = None

    if parsed is None:
        return {
            "ok": False,
            "txt": str(path),
            "listStem": list_stem,
            "error": "non-JSON stdout from tv_upload_watchlist.js",
            "returncode": proc.returncode,
            "stdout": stdout[:2000],
            "stderr": stderr[:2000],
            "cmd": cmd,
        }

    out = dict(parsed)
    out.setdefault("txt", str(path))
    out.setdefault("listStem", list_stem)
    out["returncode"] = proc.returncode
    if stderr and "stderr" not in out:
        out["stderr"] = stderr[:2000]
    if proc.returncode != 0 and out.get("ok") is not False:
        out["ok"] = False
        out.setdefault("error", f"node exit {proc.returncode}")
    return out


def maybe_upload_after_extract(txt_path: Path | str | None) -> dict[str, Any]:
    """No-op unless TUBEON_TV_UPLOAD enabled. Safe to call from watchlist_job."""
    if not tv_upload_enabled():
        return {"ok": False, "skipped": True, "reason": "TUBEON_TV_UPLOAD not enabled"}
    if not txt_path:
        return {"ok": False, "skipped": True, "reason": "no tradingview txt path"}
    return upload_watchlist_txt(txt_path, ensure=True)
