"""Maximum numerical errors (pressure and velocity) per logged time step, read from the FDS log (``CHID.out``).

FDS prints, at every logged time step, the cell with the largest velocity and pressure error::

    Time Step  1 ...
    Step Size: 0.160E+00 s, Total Time:    0.15964 s
    Maximum Velocity Error:  0.18E-02 on Mesh 1 at (10,9,2)
    Maximum Pressure Error:  0.13E-05 on Mesh 2 at (8,5,1)

Only the logged steps are available (FDS does not log every step), so the viewer shows the most recent
logged error at or before the playback time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

_TIME = re.compile(r"Total Time:\s+([0-9.Ee+\-]+)\s*s")
_ERR = re.compile(r"Maximum (Velocity|Pressure) Error:\s+([0-9.Ee+\-]+)\s+on Mesh\s+(\d+)\s+at\s+\((\d+),(\d+),(\d+)\)")


@dataclass
class ErrorSample:
    time: float
    value: float
    mesh: int
    cell: tuple          # (i, j, k) 1-based cell indices


def read_max_errors(out_file: str) -> Dict[str, List[ErrorSample]]:
    """``{"VELOCITY": [...], "PRESSURE": [...]}`` in time order; empty lists when the log has none."""
    result: Dict[str, List[ErrorSample]] = {"VELOCITY": [], "PRESSURE": []}
    p = Path(out_file)
    if not p.exists():
        return result
    t: Optional[float] = None
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _TIME.search(line)
        if m:
            t = float(m.group(1))
            continue
        e = _ERR.search(line)
        if e and t is not None:
            result[e.group(1).upper()].append(ErrorSample(t, float(e.group(2)), int(e.group(3)),
                                                          (int(e.group(4)), int(e.group(5)), int(e.group(6)))))
    return result


def at_time(samples: List[ErrorSample], t: float) -> Optional[ErrorSample]:
    """Latest logged sample at or before *t* (the first sample before the first logged step)."""
    if not samples:
        return None
    times = np.array([s.time for s in samples])
    return samples[int(np.clip(np.searchsorted(times, t + 1e-9) - 1, 0, len(samples) - 1))]


def cell_box(mesh, cell) -> tuple:
    """The (xmin, xmax, ymin, ymax, zmin, zmax) of a 1-based cell of an ``fds_run.Mesh``."""
    out = []
    for a in range(3):
        nodes = mesh.node_coords(a)
        i = min(max(cell[a] - 1, 0), len(nodes) - 2)
        out += [float(nodes[i]), float(nodes[i + 1])]
    return tuple(out)
