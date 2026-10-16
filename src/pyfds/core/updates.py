"""Is a newer version available? (Help > Check for Updates)

PyFDS is distributed as a git checkout, so "an update" means commits on the remote that this copy does not have. The check
is read-only: ``git ls-remote`` asks the remote for its current commit and nothing in the working copy is touched or
fetched. It never updates anything; it tells the user what to run.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

Runner = Callable[[Sequence[str], Path, float], "subprocess.CompletedProcess"]


@dataclass
class UpdateStatus:
    state: str                       # up_to_date | behind | ahead | diverged | unknown
    message: str
    local: str = ""
    remote: str = ""
    behind: Optional[int] = None     # commits on the remote this copy lacks (None when not known locally)
    ahead: int = 0                   # commits here the remote lacks


def _run(args: Sequence[str], cwd: Path, timeout: float) -> "subprocess.CompletedProcess":
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")             # never wait for a password prompt
    return subprocess.run(list(args), cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=env)


def repo_root(start: Optional[Path] = None) -> Optional[Path]:
    """The git checkout this code runs from, or None for an installed copy."""
    here = Path(start) if start else Path(__file__).resolve().parent
    for p in (here, *here.parents):
        if (p / ".git").exists():
            return p
    return None


def check_for_updates(root: Optional[Path] = None, branch: str = "main", timeout: float = 20.0,
                      runner: Runner = _run) -> UpdateStatus:
    """Compare this checkout's commit with the remote's *branch*. Never raises: problems become ``state="unknown"``."""
    root = root or repo_root()
    if root is None:
        return UpdateStatus("unknown", "This copy of PyFDS is not a git checkout, so there is nothing to compare "
                                       "with. Download a newer version from where you got it.")
    try:
        local = runner(["git", "rev-parse", "HEAD"], root, timeout).stdout.strip()
        if not local:
            return UpdateStatus("unknown", "Could not read the current version (is git installed?).")
        listed = runner(["git", "ls-remote", "origin", f"refs/heads/{branch}"], root, timeout)
    except FileNotFoundError:
        return UpdateStatus("unknown", "git is not installed or not on the path, so updates cannot be checked.")
    except subprocess.TimeoutExpired:
        return UpdateStatus("unknown", "The remote did not answer in time. Check the network connection and try again.")
    if listed.returncode != 0 or not listed.stdout.strip():
        why = (listed.stderr or "").strip().splitlines()[:1]
        return UpdateStatus("unknown", "Could not reach the remote" + (f": {why[0]}" if why else ".") +
                            " (offline, or the repository needs a login).", local=local)
    remote = listed.stdout.split()[0]
    if remote == local:
        return UpdateStatus("up_to_date", "You have the latest version.", local, remote, 0, 0)
    have = runner(["git", "cat-file", "-e", f"{remote}^{{commit}}"], root, timeout).returncode == 0
    if not have:
        return UpdateStatus("behind", "A newer version is available. Run `git pull` in the PyFDS folder to get it.",
                            local, remote, None, 0)
    if runner(["git", "merge-base", "--is-ancestor", remote, local], root, timeout).returncode == 0:
        ahead = _count(runner, root, f"{remote}..{local}", timeout)
        return UpdateStatus("ahead", f"Nothing newer on the remote. This copy is {ahead} commit(s) ahead of it "
                                     f"(not pushed yet).", local, remote, 0, ahead)
    behind = _count(runner, root, f"{local}..{remote}", timeout)
    ahead = _count(runner, root, f"{remote}..{local}", timeout)
    if ahead:
        return UpdateStatus("diverged", f"The remote has {behind} new commit(s) and this copy has {ahead} of its own. "
                                        f"Run `git pull --rebase` to combine them.", local, remote, behind, ahead)
    return UpdateStatus("behind", f"{behind} newer commit(s) are available. Run `git pull` in the PyFDS folder.",
                        local, remote, behind, 0)


def _count(runner: Runner, root: Path, rng: str, timeout: float) -> int:
    out = runner(["git", "rev-list", "--count", rng], root, timeout).stdout.strip()
    return int(out) if out.isdigit() else 0
