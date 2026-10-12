"""Slice file (.sf) reader."""
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

import numpy as np

from pyfds.core.exceptions import FdsBinaryError

from .reader_devc import ReaderResult
from .reader_common import _read_record, _read_string_record

logger = logging.getLogger(__name__)


@dataclass
class SliceFrame:
    """One time-step worth of slice data."""
    time: float
    data: np.ndarray       # shape (ni, nj, nk) or flattened; see header


@dataclass
class SliceHeader:
    quantity: str
    short_name: str
    units: str
    i1: int; i2: int
    j1: int; j2: int
    k1: int; k2: int

    @property
    def shape(self) -> Tuple[int, int, int]:
        return (self.i2 - self.i1 + 1,
                self.j2 - self.j1 + 1,
                self.k2 - self.k1 + 1)

    @property
    def n_values(self) -> int:
        ni, nj, nk = self.shape
        return ni * nj * nk


class SliceReader:
    """
    Read FDS slice files (``*.sf``).

    FDS slice binary layout (Fortran unformatted)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Record 1  — quantity string   (30 chars)
    Record 2  — short name string (30 chars)
    Record 3  — units string      (30 chars)
    Record 4  — i1, i2, j1, j2, k1, k2  (6 × int32)
    Then for each time step:
      Record 5n+0 — float32 time
      Record 5n+1 — float32 array (n_values floats)

    BUG-07 fix: the original ``smv_binary.py`` skipped only 1 string record
    and read the index record incorrectly. This implementation reads all 3
    string records then the index record before entering the frame loop.

    Example::

        reader = SliceReader()
        header, frames = reader.read("case_01.sf")
        print(header.quantity, header.units)
        for frame in frames:
            print(frame.time, frame.data.mean())
    """

    @classmethod
    def read(cls, filepath: str) -> ReaderResult:
        """
        Read all frames from *filepath* and return a ``ReaderResult``.

        ``result.times`` is a 1-D float array of frame times.
        ``result.data`` is a stacked array of shape ``(n_frames, ni, nj, nk)``.
        """
        header, frames = cls._read_raw(filepath)
        times_arr = np.array([f.time for f in frames], dtype=float)
        data_arr  = (np.stack([f.data for f in frames])
                     if frames else np.array([], dtype=float))
        return ReaderResult(
            source_file=str(filepath),
            quantity=header.quantity,
            units=header.units,
            times=times_arr,
            data=data_arr,
            metadata={"header": header},
        )

    @classmethod
    def _read_raw(cls, filepath: str) -> Tuple[SliceHeader, List[SliceFrame]]:
        """Internal: read header + all frames as raw objects."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Slice file not found: {filepath}")

        frames: List[SliceFrame] = []
        header: Optional[SliceHeader] = None
        try:
            with open(filepath, "rb") as fh:
                quantity   = _read_string_record(fh)
                short_name = _read_string_record(fh)
                units      = _read_string_record(fh)
                idx_data = _read_record(fh)
                i1, i2, j1, j2, k1, k2 = struct.unpack("<6i", idx_data)
                header = SliceHeader(
                    quantity=quantity, short_name=short_name, units=units,
                    i1=i1, i2=i2, j1=j1, j2=j2, k1=k1, k2=k2,
                )
                n_values = header.n_values
                while True:
                    try:
                        t_data = _read_record(fh)
                        time_val = struct.unpack("<f", t_data)[0]
                        arr_data = _read_record(fh)
                        arr = np.frombuffer(arr_data, dtype="<f4").astype(float)
                        arr = arr[:n_values].reshape(header.shape, order="F")
                        frames.append(SliceFrame(time=float(time_val), data=arr))
                    except EOFError:
                        break
        except FdsBinaryError:
            raise
        except Exception as exc:
            logger.error("SliceReader: error reading %s: %s", filepath, exc)
            raise

        logger.info("SliceReader: %s  qty=%r  frames=%d",
                    filepath, header.quantity if header else "?", len(frames))
        return header, frames

    def read_at_time(
        self,
        filepath: str,
        target_time: float,
        tolerance: float = 0.5,
    ) -> Tuple[SliceHeader, Optional[SliceFrame]]:
        """Return the frame closest to *target_time* within *tolerance* seconds."""
        header, frames = self._read_raw(filepath)
        if not frames:
            return header, None
        closest = min(frames, key=lambda f: abs(f.time - target_time))
        if abs(closest.time - target_time) > tolerance:
            return header, None
        return header, closest

    @classmethod
    def iter_frames(cls, filepath: str) -> Iterator[Tuple[float, Any]]:
        """
        Generator that yields ``(time, data)`` tuples without loading all frames
        into memory at once. Suitable for large files.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Slice file not found: {filepath}")

        with open(filepath, "rb") as fh:
            quantity   = _read_string_record(fh)
            short_name = _read_string_record(fh)
            units      = _read_string_record(fh)
            idx_data   = _read_record(fh)
            i1, i2, j1, j2, k1, k2 = struct.unpack("<6i", idx_data)

            header = SliceHeader(
                quantity=quantity, short_name=short_name, units=units,
                i1=i1, i2=i2, j1=j1, j2=j2, k1=k1, k2=k2,
            )
            n_values = header.n_values

            while True:
                try:
                    t_data   = _read_record(fh)
                    time_val = struct.unpack("<f", t_data)[0]
                    arr_data = _read_record(fh)
                    arr = np.frombuffer(arr_data, dtype="<f4").astype(float)
                    arr = arr[:n_values].reshape(header.shape, order="F")
                    yield float(time_val), arr
                except EOFError:
                    break
