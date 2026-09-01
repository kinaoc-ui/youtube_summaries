# -*- coding: utf-8 -*-
"""Commit + push summaries. ASCII-safe for Task Scheduler / cmd.exe."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GIT = Path(r"C:\Program Files\Git\cmd\git.exe")
GIT_BIN = str(GIT) if GIT.exists() else "git"


def _git(args: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [GIT_BIN, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def main() -> int:
    msg = sys.argv[1] if len(sys.argv) > 1 else "Update Martin Luk summaries"
    add = _git(["add", "-A"])
    if add.returncode != 0:
        print("[ERROR] git add failed")
        print(add.stderr or add.stdout)
        return 1
    st = _git(["status", "-sb"])
    print(st.stdout or "")
    cached = _git(["diff", "--cached", "--quiet"])
    if cached.returncode == 0:
        print("[OK] Nothing to commit.")
        ahead = _git(["status", "-sb"])
        if "ahead" in (ahead.stdout or ""):
            print("[..] pushing existing commits...")
            push = _git(["push", "-u", "origin", "main"])
            print(push.stdout or push.stderr)
            return push.returncode
        return 0
    commit = _git(["commit", "-m", msg])
    print(commit.stdout or "")
    if commit.returncode != 0:
        print("[ERROR] commit failed")
        print(commit.stderr)
        return 1
    print("[..] git push origin main...")
    push = _git(["push", "-u", "origin", "main"])
    print(push.stdout or "")
    if push.stderr:
        print(push.stderr)
    if push.returncode != 0:
        print("[ERROR] push failed")
        return 1
    print("[OK] Pushed to github.com/kinaoc-ui/youtube_summaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
