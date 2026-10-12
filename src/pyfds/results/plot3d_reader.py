"""
PyFDS Plot3D Reader
===================
Reads FDS ``*.q`` (plot3d) binary output files.

FDS Plot3D binary layout (Fortran unformatted records)
------------------------------------------------------
Record 1  — n_quantities  (int32)
Record 2  — quantity names: n_quantities × 30-char ASCII strings, concatenated
Record 3  — units strings: n_quantities × 30-char ASCII strings, concatenated
Record 4  — mesh dimensions: ni, nj, nk  (3 × int32)
For each time frame:
  Record A — time  (float32)
  Record B — data  (n_quantities × ni × nj × nk  float32, Fortran column-major order)

Usage::

    from pyfds.results.plot3d_reader import Plot3DReader

    result = Plot3DReader.read("case_01.q")
    print(result.quantities)          # ['TEMPERATURE', 'U-VELOCITY', ...]
    print(result.data.shape)          # (n_frames, n_qty, ni, nj, nk)
    print(result.times)               # 1-D float array of frame times
"""
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np

from pyfds.core.exceptions import FdsBinaryError

logger = logging.getLogger(__name__)

# Each string field in FDS binary output occupies exactly 30 characters
_STR_LEN = 30


def _read_fortran_record(fh) -> bytes:
    """Read one Fortran unformatted sequential record."""
    hdr = fh.read(4)
    if len(hdr) < 4:
        raise EOFError("Plot3D: unexpected EOF reading record header")
    length = struct.unpack("<i", hdr)[0]
    data = fh.read(length)
    if len(data) < length:
        raise EOFError(f"Plot3D: expected {length} bytes, got {len(data)}")
    trail = fh.read(4)
    if len(trail) < 4:
        raise EOFError("Plot3D: unexpected EOF reading record trailer")
    trail_len = struct.unpack("<i", trail)[0]
    if trail_len != length:
        raise FdsBinaryError(
            filepath=getattr(fh, "name", "?"),
            offset=fh.tell(),
            message=f"Plot3D: Fortran record length mismatch {length} vs {trail_len}",
        )
    return data


def _read_string_block(fh, n: int) -> List[str]:
    """Read a record containing *n* concatenated 30-char strings."""
    data = _read_fortran_record(fh)
    expected = n * _STR_LEN
    if len(data) < expected:
        raise FdsBinaryError(
            filepath=getattr(fh, "name", "?"),
            offset=0,
            message=f"Plot3D: string block too short: {len(data)} < {expected}",
        )
    return [
        data[i * _STR_LEN:(i + 1) * _STR_LEN].decode("ascii", errors="replace").strip()
        for i in range(n)
    ]


@dataclass
class Plot3DResult:
    """Container for all frames read from one ``*.q`` file."""
    source_file: str
    quantities: List[str]            # quantity names, length n_quantities
    units: List[str]                 # units strings, length n_quantities
    shape: Tuple[int, int, int]      # (ni, nj, nk) mesh cell counts
    times: np.ndarray                # shape (n_frames,), float64
    data: np.ndarray                 # shape (n_frames, n_quantities, ni, nj, nk)

    @property
    def n_frames(self) -> int:
        return len(self.times)

    @property
    def n_quantities(self) -> int:
        return len(self.quantities)

    def frame(self, index: int) -> np.ndarray:
        """Return data for frame *index*, shape (n_quantities, ni, nj, nk)."""
        return self.data[index]

    def quantity_index(self, name: str) -> Optional[int]:
        """Return the index of *name* in quantities, or None if not found."""
        name_upper = name.upper()
        for i, q in enumerate(self.quantities):
            if q.upper() == name_upper:
                return i
        return None

    def get_quantity(self, name: str) -> Optional[np.ndarray]:
        """Return all frames for *name*, shape (n_frames, ni, nj, nk), or None."""
        idx = self.quantity_index(name)
        if idx is None:
            return None
        return self.data[:, idx, :, :, :]


class Plot3DReader:
    """
    Read FDS ``*.q`` plot3d binary files.

    All main methods are classmethods so the reader can be used without
    instantiation::

        result = Plot3DReader.read("case_01.q")
    """

    @classmethod
    def read(cls, filepath: str) -> Plot3DResult:
        """
        Read all frames from *filepath*.

        Parameters
        ----------
        filepath : str
            Path to a ``.q`` binary file.

        Returns
        -------
        Plot3DResult
            Contains quantities, units, shape, times array, and data array.

        Raises
        ------
        FileNotFoundError
            If *filepath* does not exist.
        FdsBinaryError
            If the binary structure is malformed.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Plot3D file not found: {filepath}")

        times_list: List[float] = []
        frames_list: List[np.ndarray] = []
        quantities: List[str] = []
        units: List[str] = []
        shape: Tuple[int, int, int] = (0, 0, 0)

        try:
            with open(filepath, "rb") as fh:
                # Header: n_quantities, quantity names, units, mesh dims
                n_qty_data = _read_fortran_record(fh)
                n_quantities = struct.unpack("<i", n_qty_data)[0]

                quantities = _read_string_block(fh, n_quantities)
                units      = _read_string_block(fh, n_quantities)

                dims_data = _read_fortran_record(fh)
                ni, nj, nk = struct.unpack("<3i", dims_data)
                shape = (ni, nj, nk)
                n_values = ni * nj * nk

                # Frames: time + data
                while True:
                    try:
                        t_bytes = _read_fortran_record(fh)
                        time_val = struct.unpack("<f", t_bytes)[0]

                        d_bytes = _read_fortran_record(fh)
                        arr = np.frombuffer(d_bytes, dtype="<f4").astype(np.float64)
                        arr = np.moveaxis(arr[: n_quantities * n_values].reshape(
                            (ni, nj, nk, n_quantities), order="F"), -1, 0)
                        times_list.append(float(time_val))
                        frames_list.append(arr)
                    except EOFError:
                        break

        except FdsBinaryError:
            raise
        except FileNotFoundError:
            raise
        except Exception as exc:
            logger.error("Plot3DReader: error reading %s: %s", filepath, exc)
            raise

        times_arr = np.array(times_list, dtype=np.float64)
        data_arr  = (np.stack(frames_list) if frames_list
                     else np.zeros((0, n_quantities, *shape), dtype=np.float64))

        logger.info("Plot3DReader: %s  qty=%d  frames=%d  shape=%s",
                    filepath, n_quantities, len(times_list), shape)
        return Plot3DResult(
            source_file=str(path),
            quantities=quantities,
            units=units,
            shape=shape,
            times=times_arr,
            data=data_arr,
        )

    @classmethod
    def iter_frames(cls, filepath: str):
        """
        Generator yielding ``(time, data)`` one frame at a time.

        *data* shape: ``(n_quantities, ni, nj, nk)``.
        Avoids loading all frames into memory simultaneously.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Plot3D file not found: {filepath}")

        with open(filepath, "rb") as fh:
            n_qty_data   = _read_fortran_record(fh)
            n_quantities = struct.unpack("<i", n_qty_data)[0]
            _read_string_block(fh, n_quantities)   # quantities (skip)
            _read_string_block(fh, n_quantities)   # units (skip)
            dims_data    = _read_fortran_record(fh)
            ni, nj, nk   = struct.unpack("<3i", dims_data)
            n_values     = ni * nj * nk

            while True:
                try:
                    t_bytes  = _read_fortran_record(fh)
                    time_val = float(struct.unpack("<f", t_bytes)[0])
                    d_bytes  = _read_fortran_record(fh)
                    arr = np.frombuffer(d_bytes, dtype="<f4").astype(np.float64)
                    arr = np.moveaxis(arr[: n_quantities * n_values].reshape(
                        (ni, nj, nk, n_quantities), order="F"), -1, 0)
                    yield time_val, arr
                except EOFError:
                    break
