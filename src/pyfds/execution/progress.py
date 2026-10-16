"""How far a run has got (RUN progress): the simulated time, read from the files FDS writes in the case folder.

Works on any folder this machine can open, so it follows a run whose case lives on a network share (a cluster run, or a
run on another PC writing to a shared folder) exactly as it follows a local one. Only the end of each file is read, which
keeps it cheap over a network.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_TAIL = 16384
_OUT_RE = re.compile(r"Time Step\s+(\d+)\s+.*?\n\s*Step Size:.*?Total Time:\s*([0-9.Ee+-]+)\s*s", re.S)


def _tail(path: Path, size: int = _TAIL) -> Optional[str]:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            end = fh.tell()
            fh.seek(max(0, end - size))
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return None


def _from_steps(path: Path) -> Optional[Tuple[int, float]]:
    """(step, simulated time) from the last full row of ``<chid>_steps.csv``."""
    text = _tail(path)
    if not text:
        return None
    for line in reversed(text.splitlines()):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4 and parts[0].isdigit():
            try:
                return int(parts[0]), float(parts[3])
            except ValueError:
                continue
    return None


def _from_out(path: Path) -> Optional[Tuple[int, float]]:
    """(step, simulated time) from the last "Time Step ... Total Time" entry of the ``.out`` log."""
    text = _tail(path)
    if not text:
        return None
    found = _OUT_RE.findall(text)
    if not found:
        return None
    step, t = found[-1]
    try:
        return int(step), float(t)
    except ValueError:
        return None


def read_progress(folder: str, chid: str, t_end: Optional[float] = None) -> Dict[str, Any]:
    """Progress of the run writing ``<chid>`` files in *folder*.

    Returns ``time`` (simulated seconds, ``None`` before the first step), ``step``, ``t_end``, ``fraction`` (0..1,
    ``None`` when unknown), ``finished`` (the log says FDS completed) and ``idle`` (seconds since a progress file last
    changed, ``None`` when there are none: a long idle spell on a running case means the run has stalled or was lost).
    """
    d = Path(folder)
    best: Optional[Tuple[int, float]] = None
    newest = 0.0
    for name, reader in ((f"{chid}_steps.csv", _from_steps), (f"{chid}.out", _from_out)):
        p = d / name
        try:
            newest = max(newest, p.stat().st_mtime)
        except OSError:
            continue
        got = reader(p)
        if got is not None and (best is None or got[1] > best[1]):
            best = got
    out_tail = _tail(d / f"{chid}.out", 4096) or ""
    finished = "STOP: FDS completed successfully" in out_tail
    t = best[1] if best else None
    frac = None if t is None or not t_end or t_end <= 0 else max(0.0, min(1.0, t / t_end))
    if finished and frac is not None:
        frac = 1.0
    return {"time": t, "step": best[0] if best else None, "t_end": t_end, "fraction": frac, "finished": finished,
            "idle": (time.time() - newest) if newest else None}


def describe(info: Dict[str, Any]) -> str:
    """A short status-bar phrase: ``"12.3 / 60 s (20%)"``, ``"12.3 s"`` or ``"waiting for the first step"``."""
    if info["time"] is None:
        return "waiting for the first step"
    if info["t_end"]:
        return f"{info['time']:.1f} / {info['t_end']:g} s ({round(100 * (info['fraction'] or 0))}%)"
    return f"{info['time']:.1f} s"
