"""Activation-time table and HRR summary from FDS output files (TH-03).

Files used (all written by FDS 6.x): ``<chid>_devc_ctrl_log.csv`` (when each device or control changed state),
``<chid>.out`` (the "Activation Times" tables, as a fallback) and ``<chid>_hrr.csv``.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


def read_activation_log(path: str) -> List[Dict[str, Any]]:
    """Rows of ``<chid>_devc_ctrl_log.csv``: ``{"time", "type" (DEVC|CTRL), "id", "state", "value", "units"}``."""
    rows: List[Dict[str, Any]] = []
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        next(reader, None)                                        # header
        for r in reader:
            if len(r) < 4:
                continue
            try:
                t = float(r[0])
            except ValueError:
                continue
            value = None
            if len(r) > 4 and r[4].strip():
                try:
                    value = float(r[4])
                except ValueError:
                    value = None
            rows.append({"time": t, "type": r[1].strip(), "id": r[2].strip(), "state": r[3].strip() == "T",
                         "value": value, "units": r[5].strip() if len(r) > 5 else ""})
    return rows


_OUT_ROW = re.compile(r"^\s*\d+\s+(\S.*?)\s+([TF])\s+(-?[\d.]+(?:E[+-]?\d+)?)\s*$")


def read_activation_out(path: str) -> List[Dict[str, Any]]:
    """Activation times from the ``.out`` file: the DEVICE and CONTROL tables."""
    rows: List[Dict[str, Any]] = []
    kind: Optional[str] = None
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith("DEVICE Activation Times"):
            kind = "DEVC"
        elif s.startswith("CONTROL Activation Times"):
            kind = "CTRL"
        elif kind and ("Time Stepping" in s or "Total Elapsed" in s):
            kind = None
        elif kind:
            m = _OUT_ROW.match(line)
            if m:
                rows.append({"time": float(m.group(3)), "type": kind, "id": m.group(1).strip(),
                             "state": m.group(2) == "T", "value": None, "units": ""})
    return rows


def activation_table(output_dir: str, chid: str) -> List[Dict[str, Any]]:
    """First activation of every device and control, earliest first:
    ``[{"id", "type", "time", "value", "units"}]``. Items that never activated are not listed."""
    d = Path(output_dir)
    log, out = d / f"{chid}_devc_ctrl_log.csv", d / f"{chid}.out"
    if log.exists():
        rows = [r for r in read_activation_log(str(log)) if r["state"]]
    elif out.exists():
        rows = [r for r in read_activation_out(str(out)) if r["state"]]
    else:
        raise FileNotFoundError(f"no activation log or .out file for {chid!r} in {d}")
    first: Dict[tuple, Dict[str, Any]] = {}
    for r in rows:
        first.setdefault((r["type"], r["id"]), r)
    return sorted(({"id": r["id"], "type": r["type"], "time": r["time"], "value": r["value"], "units": r["units"]}
                   for r in first.values()), key=lambda r: (r["time"], r["id"]))


def read_hrr(path: str) -> Dict[str, np.ndarray]:
    """Columns of ``<chid>_hrr.csv`` by name (``Time``, ``HRR`` ...)."""
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        next(reader, None)                                        # units row
        names = [n.strip().strip('"') for n in next(reader)]
        data = np.array([[float(v) for v in r] for r in reader if r], dtype=float)
    if data.size == 0:
        raise ValueError(f"{Path(path).name}: no data rows")
    return {n: data[:, i] for i, n in enumerate(names)}


def hrr_summary(output_dir: str, chid: str, thresholds_kw: Optional[List[float]] = None) -> Dict[str, Any]:
    """Peak HRR (kW) and when it occurred, total energy released (MJ, trapezoid rule), the time-average HRR
    and the first time the HRR reached each threshold (default 100 kW, 500 kW, 1 MW, 5 MW; ``None`` if never)."""
    cols = read_hrr(str(Path(output_dir) / f"{chid}_hrr.csv"))
    t, q = cols["Time"], cols["HRR"]
    i = int(np.argmax(q))
    energy_kj = float(np.sum((q[1:] + q[:-1]) * np.diff(t)) / 2.0) if len(t) > 1 else 0.0
    duration = float(t[-1] - t[0])
    reach = {}
    for th in (thresholds_kw or [100.0, 500.0, 1000.0, 5000.0]):
        hit = np.nonzero(q >= th)[0]
        reach[th] = float(t[hit[0]]) if len(hit) else None
    return {"peak_hrr_kw": float(q[i]), "time_of_peak_s": float(t[i]), "total_energy_mj": energy_kj / 1000.0,
            "average_hrr_kw": energy_kj / duration if duration > 0 else float(q[0]),
            "duration_s": duration, "time_to_reach_kw": reach}
