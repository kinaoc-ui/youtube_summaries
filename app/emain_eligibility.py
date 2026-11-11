# -*- coding: utf-8 -*-
"""Who may become the active Martin Luk TradingView list.

Active must be a complete dated file named ``Martin_Luk_YYYY-MM-DD_E_Main``
with ``###INDEXES``, ``###LONGS``, ``###SHORTS``, and ``###FOCUS``.
``NA``, missing dates, video-id copies, and TRACKING-only bodies are not
eligible. Latest means the newest real date in the filename, never mtime
and never reverse-alpha (``Martin_Luk_NA_...`` sorts after ``2026-...``).
"""
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path
from typing import Any

REQUIRED_SECTIONS = ("INDEXES", "LONGS", "SHORTS", "FOCUS")

_DATED_STEM = re.compile(
    r"^Martin_Luk_(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})_E_Main$"
)
_MARTIN_STEM = re.compile(r"^Martin_Luk_(?P<token>.+)_E_Main$")
_HEADER = re.compile(r"###\s*([A-Za-z][A-Za-z0-9_]*)\s*")
_ISO = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
_COMPACT = re.compile(r"(20\d{2})(\d{2})(\d{2})")
_NA_TOKENS = {"NA", "N/A", "NONE", "NULL"}


def _stem(name: str) -> str:
    base = Path(name).name
    if base.lower().endswith(".txt"):
        return base[:-4]
    return base


def canonical_list_date(raw: str | None) -> str | None:
    """Return ``YYYY-MM-DD`` when ``raw`` is a real calendar date, else None.

    Accepts ``YYYY-MM-DD`` or yt-dlp ``YYYYMMDD``. Rejects blank, ``NA``,
    ``unknown-date``, and impossible dates such as ``2026-02-31``.
    """
    if raw is None:
        return None
    h = str(raw).strip()
    if not h or h.upper() in _NA_TOKENS or h.lower() == "unknown-date":
        return None
    m = _ISO.fullmatch(h)
    if not m:
        m = _COMPACT.fullmatch(h)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def date_problem(raw: str | None) -> str | None:
    """Why ``raw`` cannot name an Active list, or None when it is a real date."""
    if canonical_list_date(raw):
        return None
    token = ("" if raw is None else str(raw)).strip()
    if not token:
        return "date is missing, not a real YYYY-MM-DD"
    if token.upper() in _NA_TOKENS:
        return "date is NA, not a real YYYY-MM-DD"
    return f"date {token!r} is not a real YYYY-MM-DD"


def debug_date_token(raw: str | None) -> str:
    """Filename-safe token for a rejected date (never used as the Active name)."""
    token = re.sub(r"[^A-Za-z0-9_-]", "", ("" if raw is None else str(raw)).strip())[:32]
    return token or "undated"


def parse_martin_emain_date(name: str) -> date | None:
    """Calendar date from ``Martin_Luk_YYYY-MM-DD_E_Main[.txt]``, else None."""
    m = _DATED_STEM.fullmatch(_stem(name))
    if not m:
        return None
    try:
        return date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
    except ValueError:
        return None


def section_symbols(text: str) -> dict[str, list[str]]:
    """Map ``###SECTION`` headers to the symbols that follow them.

    A header with no symbols is present and empty. A missing header is absent.
    """
    current: str | None = None
    out: dict[str, list[str]] = {}
    body = (text or "").lstrip("\ufeff")
    for raw in body.splitlines():
        line = raw.strip()
        m = _HEADER.fullmatch(line)
        if m:
            current = m.group(1).upper()
            out.setdefault(current, [])
            continue
        if not current or not line:
            continue
        for part in line.split(","):
            tok = part.strip()
            if tok and any(c.isalnum() for c in tok):
                out[current].append(tok)
    return out


def eligibility_problems(path: Path | str, *, text: str | None = None) -> list[str]:
    """Reasons this file must not be uploaded or set TradingView Active.

    An empty list means the file is a complete dated ``Martin_Luk_YYYY-MM-DD_E_Main``.
    """
    p = Path(path)
    problems: list[str] = []
    stem = _stem(p.name)
    vod = parse_martin_emain_date(stem)
    if vod is None:
        named = _MARTIN_STEM.fullmatch(stem)
        if named:
            problems.append(date_problem(named.group("token")) or "date is not a real YYYY-MM-DD")
        else:
            problems.append(f"filename is not Martin_Luk_YYYY-MM-DD_E_Main ({p.name})")
    if text is None:
        if not p.is_file():
            problems.append("file missing")
            return problems
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as e:
            problems.append(f"unreadable: {e}")
            return problems
    bodies = section_symbols(text)
    missing = [sec for sec in REQUIRED_SECTIONS if sec not in bodies]
    empty = [sec for sec in REQUIRED_SECTIONS if sec in bodies and not bodies[sec]]
    if missing:
        present = ", ".join(f"###{s}" for s in bodies) or "none"
        problems.append(
            "missing required sections: "
            + ", ".join(f"###{s}" for s in missing)
            + f" (present: {present})"
        )
    if empty:
        problems.append(
            "empty required sections: " + ", ".join(f"###{s}" for s in empty)
        )
    return problems


def is_eligible_emain(path: Path | str, *, text: str | None = None) -> bool:
    return not eligibility_problems(path, text=text)


def log_refuse(path: Path | str, problems: list[str]) -> str:
    """Print why an upload was refused. Returns the same reason string."""
    reason = "; ".join(problems) if problems else "not eligible for TradingView Active"
    name = Path(path).name
    print(f"[martin-tv] skip upload {name}: {reason}", flush=True)
    if Path(path).is_file():
        print("[martin-tv] kept on disk; TradingView Active unchanged", flush=True)
    else:
        print("[martin-tv] TradingView Active unchanged", flush=True)
    return reason


def _interesting_candidate(name: str) -> bool:
    """Dated Martin lists and video-id ``*.E_Main.txt`` copies. Other txt files are ignored."""
    return bool(_MARTIN_STEM.fullmatch(_stem(name))) or name.endswith(".E_Main.txt")


def select_latest_emain(directory: Path | str) -> tuple[Path | None, list[str]]:
    """Latest complete dated Martin E_Main, by the date in the filename.

    Mtime is ignored. ``Martin_Luk_NA_E_Main.txt``, other undated names,
    incomplete bodies, and ``<video_id>.E_Main.txt`` copies never win.
    """
    directory = Path(directory)
    notes: list[str] = []
    if not directory.is_dir():
        return None, [f"watchlists dir missing: {directory}"]
    candidates: list[tuple[date, Path]] = []
    for path in sorted(directory.glob("*.txt"), key=lambda p: p.name.lower()):
        if not _interesting_candidate(path.name):
            continue
        problems = eligibility_problems(path)
        if problems:
            notes.append(f"skip {path.name}: " + "; ".join(problems))
            continue
        vod = parse_martin_emain_date(path.name)
        if vod is None:
            notes.append(f"skip {path.name}: date is not a real YYYY-MM-DD")
            continue
        candidates.append((vod, path))
        notes.append(f"eligible {path.name} date {vod.isoformat()}")
    if not candidates:
        notes.append("no complete dated Martin_Luk_YYYY-MM-DD_E_Main list")
        return None, notes
    candidates.sort(key=lambda item: (item[0].isoformat(), item[1].name))
    vod, winner = candidates[-1]
    notes.append(
        f"select {winner.name} by filename date {vod.isoformat()} (mtime ignored)"
    )
    return winner, notes


def browser_cap_args(upload_date: str | None) -> tuple[list[str], str | None]:
    """CLI args for ``yt_browser_cap_emain``.

    A real date is passed with ``--upload``. ``NA`` and any other non-date
    are passed as ``--date`` only so the screenshot still runs, and the
    second value explains why upload was omitted.
    """
    ud = ("" if upload_date is None else str(upload_date)).strip()
    iso = canonical_list_date(ud)
    if iso:
        return ["--date", iso, "--upload"], None
    return ["--date", debug_date_token(ud)], date_problem(ud) or "date is not a real YYYY-MM-DD"


def prepare_emain_outputs(
    directory: Path | str,
    *,
    video_id: str,
    vod_date: str | None,
    body: str,
) -> dict[str, Any]:
    """Write the OCR body for debugging and, only if the date is real, the dated list.

    ``upload_path`` is set only when that dated file is complete. An ``NA``
    date does not create ``Martin_Luk_NA_E_Main.txt``. An incomplete dated
    file is kept and ``upload_path`` stays None.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    text = body if (not body or body.endswith("\n")) else body + "\n"
    debug = directory / f"{video_id}.E_Main.txt"
    debug.write_text(text, encoding="utf-8")
    iso = canonical_list_date(vod_date)
    dated: Path | None = None
    if iso:
        dated = directory / f"Martin_Luk_{iso}_E_Main.txt"
        dated.write_text(text, encoding="utf-8")
        problems = eligibility_problems(dated)
    else:
        problems = eligibility_problems(debug, text=text)
        why = date_problem(vod_date)
        if why and why not in problems:
            problems.insert(0, why)
    upload_path = dated if dated is not None and not problems else None
    return {
        "debug_path": debug,
        "dated_path": dated,
        "upload_path": upload_path,
        "problems": problems,
        "date": iso,
    }


def main(argv: list[str] | None = None) -> int:
    """Select the latest complete dated list and optionally upload it as Active."""
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description=(
            "Re-assert the latest complete dated Martin E_Main "
            "(Martin_Luk_YYYY-MM-DD_E_Main) as the TradingView Active list"
        )
    )
    parser.add_argument(
        "--watchlists",
        type=Path,
        default=root / "outputs" / "watchlists",
        help="Directory of Martin_Luk_*_E_Main.txt files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the selected list and every skip; do not upload",
    )
    parser.add_argument(
        "--screening-root",
        type=Path,
        default=None,
        help="NineEdge screening checkout (defaults to env / sibling ../screening)",
    )
    args = parser.parse_args(argv)

    winner, notes = select_latest_emain(args.watchlists)
    for line in notes:
        print(f"[martin-tv] {line}", flush=True)
    if winner is None:
        print(
            "[martin-tv] no eligible Martin E_Main list — TradingView Active unchanged",
            flush=True,
        )
        return 0
    if args.dry_run:
        print(f"[martin-tv] dry-run: would upload {winner}", flush=True)
        return 0

    screening = args.screening_root
    if screening is None:
        sibling = root.parent / "screening"
        script = sibling / "scripts" / "tv_upload_watchlist.js"
        if script.is_file():
            screening = sibling

    from .tv_cdp_upload import upload_watchlist_txt

    result = upload_watchlist_txt(winner, root=screening, ensure=True)
    print(result, flush=True)
    if result.get("ok"):
        return 0
    # Match the old bat: a machine without the NineEdge upload script is a
    # warning, not a failed daily task. A real upload/CDP failure still fails.
    err = str(result.get("error") or "")
    if "upload script missing" in err:
        print("[martin-tv] WARN upload script missing — Active unchanged", flush=True)
        return 0
    return 1
