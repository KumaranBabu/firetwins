"""Boundary file (.bf) reader."""
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np

from pyfds.core.exceptions import FdsBinaryError

from .reader_common import _read_record, _read_string_record

logger = logging.getLogger(__name__)


@dataclass
class BoundaryHeader:
    quantity: str
    short_name: str
    units: str
    n_patches: int


@dataclass
class BoundaryPatch:
    """One surface patch per mesh face."""
    i1: int; i2: int
    j1: int; j2: int
    k1: int; k2: int
    iblk: int       # mesh index


@dataclass
class BoundaryFrame:
    time: float
    patch_data: List[np.ndarray]   # one array per patch


class BoundaryReader:
    """
    Read FDS boundary files (``*.bf``).

    FDS boundary binary layout (Fortran unformatted)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Record 1  — quantity string (30 chars)
    Record 2  — short name     (30 chars)
    Record 3  — units          (30 chars)
    Record 4  — n_patches (int32)
    For each patch p (0..n_patches-1):
      Record 4+p — i1,i2,j1,j2,k1,k2,iblk (7×int32)
    Then for each time step:
      Record t*0 — float32 time
      For each patch p:
        Record t*p — float32 array of patch values

    Example::

        reader = BoundaryReader()
        header, patches, frames = reader.read("case_01.bf")
        for frame in frames:
            print(frame.time, [p.mean() for p in frame.patch_data])
    """

    def read(
        self, filepath: str
    ) -> Tuple[BoundaryHeader, List[BoundaryPatch], List[BoundaryFrame]]:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Boundary file not found: {filepath}")

        patches: List[BoundaryPatch] = []
        frames: List[BoundaryFrame] = []

        try:
            with open(filepath, "rb") as fh:
                quantity   = _read_string_record(fh)
                short_name = _read_string_record(fh)
                units      = _read_string_record(fh)

                np_data   = _read_record(fh)
                n_patches = struct.unpack("<i", np_data)[0]

                header = BoundaryHeader(
                    quantity=quantity, short_name=short_name,
                    units=units, n_patches=n_patches,
                )

                # Read patch geometry records
                patch_sizes: List[int] = []
                for _ in range(n_patches):
                    rec = _read_record(fh)
                    i1, i2, j1, j2, k1, k2, iblk = struct.unpack("<7i", rec)
                    patches.append(BoundaryPatch(
                        i1=i1, i2=i2, j1=j1, j2=j2, k1=k1, k2=k2, iblk=iblk,
                    ))
                    # size = product of dimensions
                    size = (i2 - i1 + 1) * (j2 - j1 + 1) * (k2 - k1 + 1)
                    patch_sizes.append(max(size, 1))

                # Frame loop
                while True:
                    try:
                        t_rec    = _read_record(fh)
                        time_val = struct.unpack("<f", t_rec)[0]
                        pd: List[np.ndarray] = []
                        for sz in patch_sizes:
                            arr_data = _read_record(fh)
                            arr = np.frombuffer(arr_data, dtype="<f4").astype(float)
                            pd.append(arr[:sz])
                        frames.append(BoundaryFrame(time=float(time_val), patch_data=pd))
                    except EOFError:
                        break

        except FdsBinaryError:
            raise
        except Exception as exc:
            logger.error("BoundaryReader: error reading %s: %s", filepath, exc)
            raise

        logger.info("BoundaryReader: %s  qty=%r  patches=%d  frames=%d",
                    filepath, header.quantity, n_patches, len(frames))
        return header, patches, frames
