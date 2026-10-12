"""
PyFDS Particle Reader
=====================
Reads FDS ``*.prt5`` Lagrangian particle output files.

FDS particle binary layout (Fortran unformatted records)
---------------------------------------------------------
Record 1  — CHID string (30 chars)
Record 2  — N_PART (int32): number of particle classes
  For each class (repeated N_PART times):
    Record  — class_name (30-char string)
    Record  — n_quantities (int32), quantity_names (n × 30-char), units (n × 30-char)
For each time frame:
  Record  — time (float32), N_PART particle counts (N_PART × int32)
  For each class with count > 0:
    Record  — X, Y, Z positions (count × float32 each, 3 records)
    Record  — tag integers (count × int32)
    For each quantity:
      Record  — values (count × float32)

Usage::

    from pyfds.results.particle_reader import ParticleReader

    result = ParticleReader.read("case.prt5")
    print(result.n_classes)
    for cls in result.classes:
        print(cls.name, len(cls.frames))
        for frame in cls.frames:
            print(frame.time, frame.positions.shape)
"""
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from pyfds.core.exceptions import FdsBinaryError

logger = logging.getLogger(__name__)

_STR_LEN = 30


def _read_record(fh) -> bytes:
    """Read one Fortran unformatted record."""
    hdr = fh.read(4)
    if len(hdr) < 4:
        raise EOFError("Particle: unexpected EOF reading record header")
    length = struct.unpack("<i", hdr)[0]
    data = fh.read(length)
    if len(data) < length:
        raise EOFError(f"Particle: short read: expected {length}, got {len(data)}")
    trail = fh.read(4)
    if len(trail) < 4:
        raise EOFError("Particle: unexpected EOF reading record trailer")
    trail_len = struct.unpack("<i", trail)[0]
    if trail_len != length:
        raise FdsBinaryError(
            filepath=getattr(fh, "name", "?"),
            offset=fh.tell(),
            message=f"Particle: record length mismatch {length} vs {trail_len}",
        )
    return data


def _read_string(fh) -> str:
    return _read_record(fh).decode("ascii", errors="replace").strip()


def _read_string_block(fh, n: int) -> List[str]:
    data = _read_record(fh)
    return [
        data[i * _STR_LEN:(i + 1) * _STR_LEN].decode("ascii", errors="replace").strip()
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class ParticleFrame:
    """One time-step of particle positions and quantities for one class."""
    time: float
    positions: np.ndarray       # shape (n_particles, 3) — X, Y, Z columns
    tags: np.ndarray            # shape (n_particles,) — integer tags
    quantities: Dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def n_particles(self) -> int:
        return len(self.tags)


@dataclass
class ParticleClass:
    """All frames for one FDS particle class."""
    name: str
    quantity_names: List[str]
    units: List[str]
    frames: List[ParticleFrame] = field(default_factory=list)

    @property
    def times(self) -> np.ndarray:
        return np.array([f.time for f in self.frames], dtype=np.float64)

    @property
    def n_frames(self) -> int:
        return len(self.frames)


@dataclass
class ParticleResult:
    """All particle data from one ``*.prt5`` file."""
    source_file: str
    chid: str
    classes: List[ParticleClass] = field(default_factory=list)

    @property
    def n_classes(self) -> int:
        return len(self.classes)

    def get_class(self, name: str) -> Optional[ParticleClass]:
        """Return the particle class whose name contains *name* (case-insensitive)."""
        name_upper = name.upper()
        for cls in self.classes:
            if name_upper in cls.name.upper():
                return cls
        return None


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

class ParticleReader:
    """
    Read FDS ``*.prt5`` Lagrangian particle binary files.

    Classmethods allow use without instantiation::

        result = ParticleReader.read("case.prt5")
    """

    @classmethod
    def read(cls, filepath: str) -> ParticleResult:
        """
        Read all frames from *filepath*.

        Returns
        -------
        ParticleResult

        Raises
        ------
        FileNotFoundError
            If *filepath* does not exist.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Particle file not found: {filepath}")

        try:
            with open(filepath, "rb") as fh:
                # ── File header ───────────────────────────────────────────
                chid = _read_string(fh)

                n_part_data = _read_record(fh)
                n_classes = struct.unpack("<i", n_part_data)[0]

                part_classes: List[ParticleClass] = []
                for _ in range(n_classes):
                    cls_name = _read_string(fh)
                    n_qty_data = _read_record(fh)
                    n_qty = struct.unpack("<i", n_qty_data)[0]
                    if n_qty > 0:
                        qty_names = _read_string_block(fh, n_qty)
                        qty_units = _read_string_block(fh, n_qty)
                    else:
                        qty_names = []
                        qty_units = []
                    part_classes.append(ParticleClass(
                        name=cls_name,
                        quantity_names=qty_names,
                        units=qty_units,
                    ))

                # ── Time frames ───────────────────────────────────────────
                while True:
                    try:
                        frame_hdr = _read_record(fh)
                        # time (float32) + counts per class (N × int32)
                        expected = 4 + n_classes * 4
                        if len(frame_hdr) < expected:
                            break
                        time_val = struct.unpack("<f", frame_hdr[:4])[0]
                        counts   = list(struct.unpack(
                            f"<{n_classes}i", frame_hdr[4: 4 + n_classes * 4]
                        ))

                        for ci, count in enumerate(counts):
                            pc = part_classes[ci]
                            if count <= 0:
                                continue

                            x_bytes = _read_record(fh)
                            y_bytes = _read_record(fh)
                            z_bytes = _read_record(fh)
                            x = np.frombuffer(x_bytes, dtype="<f4")[:count].astype(float)
                            y = np.frombuffer(y_bytes, dtype="<f4")[:count].astype(float)
                            z = np.frombuffer(z_bytes, dtype="<f4")[:count].astype(float)
                            positions = np.column_stack([x, y, z])

                            tag_bytes = _read_record(fh)
                            tags = np.frombuffer(tag_bytes, dtype="<i4")[:count].copy()

                            qty_data: Dict[str, np.ndarray] = {}
                            for qname in pc.quantity_names:
                                q_bytes = _read_record(fh)
                                q_arr = np.frombuffer(q_bytes, dtype="<f4")[:count].astype(float)
                                qty_data[qname] = q_arr

                            pc.frames.append(ParticleFrame(
                                time=float(time_val),
                                positions=positions,
                                tags=tags,
                                quantities=qty_data,
                            ))

                    except EOFError:
                        break

        except FdsBinaryError:
            raise
        except FileNotFoundError:
            raise
        except Exception as exc:
            logger.error("ParticleReader: error reading %s: %s", filepath, exc)
            raise

        result = ParticleResult(
            source_file=str(path),
            chid=chid,
            classes=part_classes,
        )
        total_frames = sum(pc.n_frames for pc in part_classes)
        logger.info("ParticleReader: %s  classes=%d  total_frames=%d",
                    filepath, n_classes, total_frames)
        return result
