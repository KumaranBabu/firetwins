"""Installed FDS builds (RUN-07): find them, read their version, pick one."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"Revision\s*:\s*FDS-?(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)
_EXE = ("fds.exe", "fds")
_probe_cache: Dict[Tuple[str, float], Optional[str]] = {}


@dataclass
class FdsInstall:
    name: str
    path: str                       # the fds executable
    version: Optional[str]          # e.g. "6.10.1"; None if the build would not report one
    mpiexec: Optional[str] = None
    source: str = ""                # where it was found: env, path, repo, config, user

    def to_dict(self) -> dict:
        return dict(vars(self))


def version_tuple(v: Optional[str]) -> Tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", v or "")) or (0,)


def _bin_env(exe: Path) -> dict:
    env = dict(os.environ)
    extra = [str(exe.parent)] + ([str(exe.parent / "mpi")] if (exe.parent / "mpi").is_dir() else [])
    env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    return env


def probe_version(exe: str, timeout: float = 30.0) -> Optional[str]:
    """Run the executable without arguments (FDS prints its banner and stops) and read the revision."""
    p = Path(exe)
    try:
        key = (str(p.resolve()), p.stat().st_mtime)
    except OSError:
        return None
    if key in _probe_cache:
        return _probe_cache[key]
    version = None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run([str(p)], cwd=tmp, env=_bin_env(p), capture_output=True, text=True,
                                 timeout=timeout, stdin=subprocess.DEVNULL)
        m = _VERSION_RE.search(out.stdout + out.stderr)
        version = m.group(1) if m else None
    except (OSError, subprocess.SubprocessError) as exc:
        logger.info("Could not read the version of %s: %s", exe, exc)
    _probe_cache[key] = version
    return version


def _mpiexec_for(exe: Path) -> Optional[str]:
    for cand in (exe.parent / "mpi" / "mpiexec.exe", exe.parent / "mpi" / "mpiexec", exe.parent / "mpiexec"):
        if cand.is_file():
            return str(cand)
    return shutil.which("mpiexec")


def _exes_in(directory: Path) -> Iterable[Path]:
    for base in (directory, directory / "bin"):
        for n in _EXE:
            if (base / n).is_file():
                yield base / n


def _candidates(extra_dirs: Iterable[str]) -> List[Tuple[Path, str]]:
    found: List[Tuple[Path, str]] = []
    env = os.environ.get("FDS_BIN")
    if env:
        p = Path(env)
        found += [(p, "env")] if p.is_file() else [(e, "env") for e in _exes_in(p)]
    w = shutil.which("fds")
    if w:
        found.append((Path(w), "path"))
    repo = Path(__file__).resolve().parents[3] / "fds_smv"
    if repo.is_dir():
        for d in sorted(repo.iterdir()):
            found += [(e, "repo") for e in _exes_in(d)]
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), "/opt", str(Path.home())):
        if not root:
            continue
        base = Path(root)
        for pattern in ("firemodels/FDS*", "FDS*", "firemodels/FDS*/FDS*"):
            for d in sorted(base.glob(pattern)):
                found += [(e, "scan") for e in _exes_in(d)]
    for d in extra_dirs:
        p = Path(d)
        if p.is_file():
            found.append((p, "config"))
        elif p.is_dir():
            found += [(e, "config") for e in _exes_in(p)]
            for sub in sorted(p.iterdir()):
                if sub.is_dir():
                    found += [(e, "config") for e in _exes_in(sub)]
    return found


def discover(extra_dirs: Iterable[str] = (), probe: bool = True) -> List[FdsInstall]:
    """Every FDS executable found in FDS_BIN, PATH, the repo's ``fds_smv`` folder, the usual install
    folders and *extra_dirs* (files or folders), newest version first."""
    seen, out = set(), []
    for exe, source in _candidates(extra_dirs):
        try:
            key = str(exe.resolve()).lower()
        except OSError:
            continue
        if key in seen or exe.name.lower().startswith("fds_openmp"):
            continue
        seen.add(key)
        version = probe_version(str(exe)) if probe else None
        label = f"FDS {version}" if version else exe.parent.parent.name or exe.name
        out.append(FdsInstall(label, str(exe), version, _mpiexec_for(exe), source))
    out.sort(key=lambda i: version_tuple(i.version), reverse=True)
    names: Dict[str, int] = {}
    for i in out:                          # two builds of one version still need different names
        names[i.name] = names.get(i.name, 0) + 1
        if names[i.name] > 1:
            i.name = f"{i.name} ({names[i.name]})"
    return out


def compatibility(install_version: Optional[str], project_fds_version: str) -> Tuple[bool, str]:
    """Can a build of *install_version* run a project written for syntax *project_fds_version*?"""
    if project_fds_version in (None, "", "latest"):
        return True, "project is written for the newest FDS syntax"
    if install_version is None:
        return True, "installed version unknown; cannot check"
    if version_tuple(install_version) >= version_tuple(project_fds_version):
        return True, f"FDS {install_version} reads FDS {project_fds_version} syntax"
    return False, f"project targets FDS {project_fds_version} syntax but FDS {install_version} is older"
