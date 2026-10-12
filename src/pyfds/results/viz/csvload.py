"""Loading CSV time series (phase V10): FDS output files and any CSV with a time column.

Header handling follows PyroSim Results: one to three header rows may carry a description, a quantity and a
unit per column, either on their own rows or combined as ``Door01_width (m)``. Real FDS files put the unit
row first and the name row second (``s,kW,kW`` / ``Time,HRR,Q_RADI``); that layout is recognised.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .model import CsvFileRef

#: FDS output files whose layout is known, by the name suffix: (header rows, description row, unit row)
KNOWN_TYPES = {"_hrr": ("FDS heat release", 2, 2, 1), "_devc": ("FDS devices", 2, 2, 1), "_ctrl": ("FDS controls", 2, 2, 1),
               "_steps": ("FDS time steps", 2, 2, 1), "_cpu": ("FDS CPU time", 2, 2, 1), "_mass": ("FDS mass", 2, 2, 1),
               "_git": None}


@dataclass
class TimeSeries:
    description: str
    quantity: str
    unit: str
    times: np.ndarray
    values: np.ndarray

    @property
    def label(self) -> str:
        return self.description + (f" {self.quantity}" if self.quantity and self.quantity != self.description else "")


@dataclass
class CsvData:
    ref: CsvFileRef
    series: List[TimeSeries] = field(default_factory=list)


def guess_type(path: str) -> CsvFileRef:
    """A ready reference for a known FDS CSV (by file name), else a 'custom' one for the Load CSV dialog to fill."""
    stem = Path(path).stem
    for suffix, spec in KNOWN_TYPES.items():
        if stem.endswith(suffix) and spec:
            name, header_rows, desc_row, unit_row = spec
            return CsvFileRef(path, name, 1, header_rows, desc_row, None, unit_row)
    return CsvFileRef(path)


def preview(path: str, rows: int = 10, cols: int = 20) -> List[List[str]]:
    """The top-left corner of the file, as the Load CSV dialog shows it."""
    out = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for i, row in enumerate(csv.reader(fh)):
            if i >= rows:
                break
            out.append([c.strip() for c in row[:cols]])
    return out


_COMBINED = re.compile(r"^(?P<desc>.*?)(?:_(?P<q>[^_()]+))?\s*(?:\((?P<u>[^)]*)\))?$")


def _split_combined(cell: str) -> Tuple[str, str, str]:
    m = _COMBINED.match(cell.strip())
    if not m:
        return cell.strip(), "", ""
    return (m.group("desc") or cell).strip(), (m.group("q") or "").strip(), (m.group("u") or "").strip()


def load(ref: CsvFileRef) -> CsvData:
    """Read the series described by *ref*. Raises ``ValueError`` with a plain message for unusable files."""
    p = Path(ref.path)
    if not p.exists():
        raise FileNotFoundError(f"CSV file not found: {ref.path}")
    with open(p, newline="", encoding="utf-8-sig") as fh:
        rows = [r for r in csv.reader(fh)]
    if len(rows) <= ref.header_rows:
        raise ValueError(f"{p.name} has no data rows after {ref.header_rows} header row(s)")
    if not 1 <= ref.time_column <= max(len(rows[0]), 1):
        raise ValueError("the time column is outside the file")
    header = rows[:ref.header_rows]

    def cells(row_no: Optional[int]) -> Optional[List[str]]:
        if row_no is None:
            return None
        if not 1 <= row_no <= len(header):
            raise ValueError(f"header row {row_no} does not exist (the file has {len(header)} header rows)")
        return [c.strip() for c in header[row_no - 1]]

    desc, qty, unit = cells(ref.description_row), cells(ref.quantity_row), cells(ref.unit_row)
    body = rows[ref.header_rows:]
    n_cols = len(rows[ref.header_rows - 1]) if ref.header_rows else len(body[0])
    data = np.full((len(body), n_cols), np.nan)
    for i, r in enumerate(body):
        for j in range(min(n_cols, len(r))):
            try:
                data[i, j] = float(r[j])
            except ValueError:
                pass
    t = data[:, ref.time_column - 1]
    if np.isnan(t).all():
        raise ValueError("the time column holds no numbers; check the time column and the number of header rows")
    keep = ~np.isnan(t)
    t = t[keep]
    if np.any(np.diff(t) < 0):
        raise ValueError("times must not decrease")
    # duplicate times: only the first row of a run of equal times is used
    first = np.concatenate([[True], np.diff(t) > 0])
    out = CsvData(ref)
    for j in range(n_cols):
        if j == ref.time_column - 1:
            continue
        d = desc[j] if desc and j < len(desc) else f"Column {j + 1}"
        q = qty[j] if qty and j < len(qty) else ""
        u = unit[j] if unit and j < len(unit) else ""
        if (desc is qty or desc is unit) or (not q and not u and ("(" in d or "_" in d) and ref.header_rows == 1):
            d, q2, u2 = _split_combined(d)
            q, u = q or q2, u or u2
        col = data[keep, j]
        if np.isnan(col).all():
            continue
        out.series.append(TimeSeries(d, q, u, t[first], col[first]))
    if not out.series:
        raise ValueError("no numeric columns found besides the time column")
    return out


def export(series: Sequence[TimeSeries], path: str, sep: str = ",") -> int:
    """Write selected series to CSV / TSV: time first, then one column each, over the union of their times."""
    if not series:
        raise ValueError("select at least one series to export")
    if sep not in (",", "\t"):
        raise ValueError("separator must be a comma or a tab")
    times = np.unique(np.concatenate([s.times for s in series]))
    cols = [np.interp(times, s.times, s.values, left=np.nan, right=np.nan) for s in series]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=sep)
        w.writerow(["s"] + [s.unit for s in series])
        w.writerow(["Time"] + [s.label for s in series])
        for i, t in enumerate(times):
            w.writerow([f"{t:.6g}"] + ["" if np.isnan(c[i]) else f"{c[i]:.6g}" for c in cols])
    return len(times)
