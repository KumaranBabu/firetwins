"""
PyFDS SMV Binary Extractor
===========================
High-level facade over the ``results.reader`` low-level Fortran binary
readers, scoped specifically to Smokeview output files.

BUG-07 fix (original ``smv_binary.py``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The original implementation:
  1. Called ``_skip_string_records(fh, 1)`` — only skipped ONE string header
     instead of three (quantity / short_name / units).
  2. Attempted to unpack 3 ints from the index record instead of 6.

This module delegates to ``pyfds.results.reader`` where all three header
strings are correctly consumed before the index record is read.

Additional readers
------------------
- ``read_isosurface_file``  — ``*.iso`` / ``*.ge1`` isosurface geometry + values
- ``read_plot3d_file``      — ``*.q`` Plot3D 5-variable field files

Example::

    from pyfds.smokeview.binary import SmvBinaryExtractor

    extractor = SmvBinaryExtractor()

    # Slice file — BUG-07 already fixed in SliceReader
    header, frames = extractor.read_slice("case_01.sf")
    temp_at_60s = extractor.slice_at_time("case_01.sf", target_time=60.0)

    # Boundary file
    b_header, patches, b_frames = extractor.read_boundary("case_01.bf")

    # Isosurface
    iso = extractor.read_isosurface("case_01.iso")

    # Plot3D
    p3d = extractor.read_plot3d("case_01.q", ni=50, nj=50, nk=30)
"""
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from pyfds.results.reader import (
    SliceReader, SliceHeader, SliceFrame,
    BoundaryReader, BoundaryHeader, BoundaryPatch, BoundaryFrame,
    _read_record, _read_string_record,
)
from pyfds.core.exceptions import FdsBinaryError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Isosurface types
# ---------------------------------------------------------------------------

@dataclass
class IsosurfaceFrame:
    """One time-step of isosurface geometry."""
    time: float
    vertices: np.ndarray     # shape (N, 3) float32
    triangles: np.ndarray    # shape (M, 3) int32 (vertex indices)
    values: Optional[np.ndarray] = None   # per-vertex colour quantity


@dataclass
class IsosurfaceFile:
    """All data from a ``*.iso`` file."""
    filepath: str
    quantity: str = ""
    short_name: str = ""
    units: str = ""
    color_quantity: str = ""
    color_units: str = ""
    frames: List[IsosurfaceFrame] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Plot3D types
# ---------------------------------------------------------------------------

@dataclass
class Plot3DFile:
    """Data from a ``*.q`` Plot3D file (FDS single-block structured)."""
    filepath: str
    time: float = 0.0
    ni: int = 0
    nj: int = 0
    nk: int = 0
    quantities: List[str] = field(default_factory=list)
    data: np.ndarray = field(default_factory=lambda: np.array([]))
    # data shape: (5, ni, nj, nk) — 5 quantities per cell


# ---------------------------------------------------------------------------
# SmvBinaryExtractor facade
# ---------------------------------------------------------------------------

class SmvBinaryExtractor:
    """
    Unified facade for reading all Smokeview binary output files.

    Delegates slice and boundary reading to ``pyfds.results.reader``
    (which already applies BUG-07 fix).  Provides additional readers for
    isosurface and Plot3D files.
    """

    # ── Slice ─────────────────────────────────────────────────────────────────

    def read_slice(self, filepath: str) -> Tuple[SliceHeader, List[SliceFrame]]:
        """Read all frames from a ``*.sf`` slice file."""
        return SliceReader().read(filepath)

    def slice_at_time(
        self,
        filepath: str,
        target_time: float,
        tolerance: float = 0.5,
    ) -> Optional[Tuple[SliceHeader, SliceFrame]]:
        """Return the (header, frame) pair closest to *target_time*, or None."""
        header, frame = SliceReader().read_at_time(filepath, target_time, tolerance)
        if frame is None:
            return None
        return header, frame

    def slice_time_series(
        self,
        filepath: str,
        i: int,
        j: int,
        k: int,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extract time-series at a single grid point (i, j, k) from a slice file.

        Returns
        -------
        (times, values) — both 1-D float64 arrays.
        """
        header, frames = SliceReader().read(filepath)
        times  = np.array([f.time for f in frames], dtype=float)
        values = np.array([f.data[i, j, k] for f in frames], dtype=float)
        return times, values

    # ── Boundary ──────────────────────────────────────────────────────────────

    def read_boundary(
        self, filepath: str
    ) -> Tuple[BoundaryHeader, List[BoundaryPatch], List[BoundaryFrame]]:
        """Read all frames from a ``*.bf`` boundary file."""
        return BoundaryReader().read(filepath)

    # ── Isosurface ────────────────────────────────────────────────────────────

    def read_isosurface(self, filepath: str) -> IsosurfaceFile:
        """
        Read a ``*.iso`` / ``*.ge1`` FDS isosurface file.

        FDS isosurface binary layout (Fortran unformatted)
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        Record 1  — quantity string (30)
        Record 2  — short_name     (30)
        Record 3  — units          (30)
        Record 4  — color quantity (30)
        Record 5  — color units    (30)
        Then for each time step:
          Rec A — float32 time
          Rec B — int32 n_verts
          Rec C — float32[n_verts * 3] xyz vertex data
          Rec D — int32 n_tris
          Rec E — int32[n_tris * 3] triangle vertex indices (1-based)
          Rec F — (optional) float32[n_verts] per-vertex colour values
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Isosurface file not found: {filepath}")

        iso = IsosurfaceFile(filepath=str(filepath))
        try:
            with open(filepath, "rb") as fh:
                iso.quantity       = _read_string_record(fh)
                iso.short_name     = _read_string_record(fh)
                iso.units          = _read_string_record(fh)
                iso.color_quantity = _read_string_record(fh)
                iso.color_units    = _read_string_record(fh)

                has_color = bool(iso.color_quantity.strip())

                while True:
                    try:
                        t_rec    = _read_record(fh)
                        time_val = struct.unpack("<f", t_rec)[0]

                        nv_rec  = _read_record(fh)
                        n_verts = struct.unpack("<i", nv_rec)[0]

                        xyz_rec  = _read_record(fh)
                        xyz = np.frombuffer(xyz_rec, dtype="<f4").reshape(n_verts, 3)

                        nt_rec   = _read_record(fh)
                        n_tris   = struct.unpack("<i", nt_rec)[0]

                        tri_rec  = _read_record(fh)
                        tris = np.frombuffer(tri_rec, dtype="<i4").reshape(n_tris, 3)
                        tris = tris - 1   # Convert 1-based to 0-based

                        values = None
                        if has_color:
                            col_rec = _read_record(fh)
                            values  = np.frombuffer(col_rec, dtype="<f4").copy()

                        iso.frames.append(IsosurfaceFrame(
                            time=float(time_val),
                            vertices=xyz.astype(float),
                            triangles=tris,
                            values=values.astype(float) if values is not None else None,
                        ))
                    except EOFError:
                        break

        except FdsBinaryError:
            raise
        except Exception as exc:
            logger.error("SmvBinaryExtractor: isosurface read error %s: %s", filepath, exc)
            raise

        logger.info("SmvBinaryExtractor: iso %s  qty=%r  frames=%d",
                    filepath, iso.quantity, len(iso.frames))
        return iso

    # ── Plot3D ────────────────────────────────────────────────────────────────

    def read_plot3d(
        self,
        filepath: str,
        ni: int,
        nj: int,
        nk: int,
        quantity_names: Optional[List[str]] = None,
    ) -> Plot3DFile:
        """
        Read a ``*.q`` FDS Plot3D file.

        FDS Plot3D binary layout (Fortran unformatted, single-block)
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        Record 1 — ni nj nk (3 × int32)
        Record 2 — time fsmach alpha re time_again (5 × float32 header)
        Record 3 — float32[ni * nj * nk * 5]  — 5 quantities interleaved

        Parameters
        ----------
        filepath : str
            Path to ``*.q`` file.
        ni, nj, nk : int
            Grid dimensions (must match the FDS mesh).
        quantity_names : list[str], optional
            Human-readable labels for the 5 quantities. Defaults to
            ``['U', 'V', 'W', 'T', 'HRRPUV']``.

        Returns
        -------
        Plot3DFile
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Plot3D file not found: {filepath}")

        names = quantity_names or ["U", "V", "W", "T", "HRRPUV"]
        p3d = Plot3DFile(filepath=str(filepath), ni=ni, nj=nj, nk=nk, quantities=names)

        try:
            with open(filepath, "rb") as fh:
                # Record 1: grid dims (may differ from supplied — sanity check)
                dim_rec = _read_record(fh)
                if len(dim_rec) >= 12:
                    _ni, _nj, _nk = struct.unpack("<3i", dim_rec[:12])
                    if (_ni, _nj, _nk) != (ni, nj, nk):
                        logger.warning(
                            "Plot3D dims mismatch: file=(%d,%d,%d) supplied=(%d,%d,%d)",
                            _ni, _nj, _nk, ni, nj, nk,
                        )
                        ni, nj, nk = _ni, _nj, _nk
                        p3d.ni, p3d.nj, p3d.nk = ni, nj, nk

                # Record 2: FSMACH ALPHA RE TIME (first float is time for FDS)
                hdr_rec  = _read_record(fh)
                p3d.time = struct.unpack("<f", hdr_rec[:4])[0]

                # Record 3: 5-variable field
                data_rec = _read_record(fh)
                n_total  = ni * nj * nk * 5
                arr = np.frombuffer(data_rec, dtype="<f4")[:n_total].astype(float)
                p3d.data = arr.reshape(5, ni, nj, nk, order="F")

        except FdsBinaryError:
            raise
        except Exception as exc:
            logger.error("SmvBinaryExtractor: plot3d read error %s: %s", filepath, exc)
            raise

        logger.info("SmvBinaryExtractor: plot3d %s  shape=(%d,%d,%d)  t=%.2f",
                    filepath, ni, nj, nk, p3d.time)
        return p3d

    # ── Particle ──────────────────────────────────────────────────────────────

    def read_particle(self, filepath: str) -> Any:
        """
        Read a ``*.prt5`` FDS particle file.

        Delegates to ``pyfds.results.particle_reader.ParticleReader``.

        Returns
        -------
        ParticleResult
        """
        from pyfds.results.particle_reader import ParticleReader
        return ParticleReader().read(filepath)

    def get_plot3d_quantity(self, p3d: Plot3DFile, quantity: str) -> np.ndarray:
        """
        Return one 3-D array from a Plot3DFile by quantity name.

        Parameters
        ----------
        p3d : Plot3DFile
        quantity : str
            Must match one of ``p3d.quantities``.

        Returns
        -------
        np.ndarray shape (ni, nj, nk)
        """
        try:
            idx = p3d.quantities.index(quantity)
        except ValueError:
            raise KeyError(f"Quantity {quantity!r} not in {p3d.quantities}")
        return p3d.data[idx]
