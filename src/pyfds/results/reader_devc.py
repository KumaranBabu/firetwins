"""Device (CSV) reader."""
from __future__ import annotations

import logging
import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ReaderResult:
    """Generic container returned by all readers."""
    source_file: str
    quantity: str = ""
    units: str = ""
    times: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    data: Any = None          # shape depends on reader (1-D, 3-D, ...)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def n_times(self) -> int:
        return len(self.times)

    @property
    def time(self):
        """Backward-compat alias for ``times``."""
        return self.times

    @property
    def values(self):
        """Backward-compat alias for ``data``."""
        return self.data


class DeviceReader:
    """
    Parse FDS device output CSV files (``<CHID>_devc.csv``).

    The first row of the CSV is the quantity/label row; the second row is
    the units row; subsequent rows are numeric time-series data.

    Example::

        reader = DeviceReader()
        results = reader.read("case_devc.csv")
        # results["Time"]        → ReaderResult  (times vector)
        # results["SPRK_01"]     → ReaderResult  (single device)
    """

    @classmethod
    def read(cls, filepath: str) -> Dict[str, ReaderResult]:
        """
        Read a ``*_devc.csv`` file.

        Returns
        -------
        dict
            Mapping ``device_name → ReaderResult``.  The ``"Time"`` key
            always contains the simulation time axis.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Device CSV not found: {filepath}")

        results: Dict[str, ReaderResult] = {}
        try:
            with path.open(newline="", encoding="utf-8-sig") as fh:
                reader = csv.reader(fh)
                rows = list(reader)

            if len(rows) < 3:
                logger.warning("DeviceReader: too few rows in %s", filepath)
                return results

            # Row 0: column headers (device names / "Time")
            # Row 1: units
            headers = [h.strip() for h in rows[0]]
            units   = [u.strip() for u in rows[1]]
            # Real FDS writes the UNITS row first and the names row ("Time", "HRR", ...) second;
            # older/hand-made files have them the other way round. Go by where "Time" is.
            if headers and units and units[0].lower() == "time" and headers[0].lower() != "time":
                headers, units = units, headers

            # Remaining rows: numeric data
            data_rows = rows[2:]
            if not data_rows:
                return results

            n_cols = len(headers)
            columns: List[List[float]] = [[] for _ in range(n_cols)]

            for row in data_rows:
                for i, val in enumerate(row[:n_cols]):
                    try:
                        columns[i].append(float(val))
                    except ValueError:
                        columns[i].append(float("nan"))

            time_arr = np.array(columns[0], dtype=float)

            for i, name in enumerate(headers):
                arr = np.array(columns[i], dtype=float)
                results[name] = ReaderResult(
                    source_file=str(path),
                    quantity=name,
                    units=units[i] if i < len(units) else "",
                    times=time_arr,
                    data=arr,
                )

            logger.info("DeviceReader: read %d devices from %s", n_cols - 1, filepath)
        except Exception as exc:
            logger.error("DeviceReader: failed reading %s: %s", filepath, exc)
            raise

        return results

    def read_device(self, filepath: str, device_name: str) -> Optional[ReaderResult]:
        """Convenience: read a single device by name."""
        all_results = self.read(filepath)
        return all_results.get(device_name)

    def find_csv(self, output_dir: str, chid: str) -> Optional[str]:
        """Locate ``<CHID>_devc.csv`` in *output_dir*."""
        p = Path(output_dir) / f"{chid}_devc.csv"
        return str(p) if p.exists() else None
