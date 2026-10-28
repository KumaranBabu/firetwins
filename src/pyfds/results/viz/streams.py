"""Streaming readers for FDS binary output (slices, boundaries, particles, isosurfaces, Plot3D, smoke3D).

Every FDS binary file is a sequence of Fortran unformatted records (4-byte length, data, 4-byte length).
``RecordFile`` indexes the records once (and keeps that index in a ``.pyfcache`` file next to the data so
the next open is instant, and so a file that is still growing only has its new tail scanned); the
``*Stream`` classes then read a single frame on demand instead of loading the whole file. The layouts were
checked against real FDS 6.10.1 output (``tests/fixtures/results_room``).
"""
from __future__ import annotations

import struct
from typing import List, Tuple

import numpy as np

from .streams_particles import (  # noqa: F401  (re-exported)
    IsoStream,
    ParticleStream,
)
from .streams_common import (  # noqa: F401  (re-exported)
    CACHE_VERSION,
    RecordFile,
    StreamError,
    _need,
    _times_cache,
)



class SliceStream(RecordFile):
    """``*.sf``: quantity / short name / units, node range, then (time, values) per frame."""
    kind = "slice"

    def __init__(self, path: str, use_cache: bool = True) -> None:
        super().__init__(path, use_cache)
        _need(self, 4)
        self.quantity, self.short, self.units = (self.text(i) for i in range(3))
        ijk = self.ints(3)
        if len(ijk) != 6:
            raise StreamError(f"{path}: not a slice file")
        self.ijk = ijk
        self.shape = (ijk[1] - ijk[0] + 1, ijk[3] - ijk[2] + 1, ijk[5] - ijk[4] + 1)

    @property
    def n_frames(self) -> int:
        return (self.n_records - 4) // 2

    @property
    @_times_cache
    def times(self) -> np.ndarray:
        return np.array([float(self.floats(4 + 2 * k)[0]) for k in range(self.n_frames)])

    def frame(self, k: int) -> np.ndarray:
        data = self.floats(5 + 2 * k)
        n = int(np.prod(self.shape))
        if data.size < n:
            raise StreamError(f"{self.path}: frame {k} is short ({data.size} of {n} values)")
        return data[:n].reshape(self.shape, order="F").astype(np.float32)


class BoundaryStream(RecordFile):
    """``*.bf``: header, one 9-integer record per patch (i1 i2 j1 j2 k1 k2 ior obst mesh), then frames."""
    kind = "boundary"

    def __init__(self, path: str, use_cache: bool = True) -> None:
        super().__init__(path, use_cache)
        _need(self, 4)
        self.quantity, self.short, self.units = (self.text(i) for i in range(3))
        self.n_patches = self.ints(3)[0]
        _need(self, 4 + self.n_patches)
        self.patches: List[Tuple[int, ...]] = [struct.unpack(f"<{len(b) // 4}i", b)
                                               for b in self.read_many(4, self.n_patches)]
        if any(len(p) not in (7, 9) for p in self.patches):
            raise StreamError(f"{path}: unexpected boundary patch record")
        self.sizes = [(p[1] - p[0] + 1) * (p[3] - p[2] + 1) * (p[5] - p[4] + 1) for p in self.patches]

    @property
    def n_frames(self) -> int:
        return (self.n_records - 4 - self.n_patches) // (1 + self.n_patches)

    def _t(self, k: int) -> int:
        return 4 + self.n_patches + k * (1 + self.n_patches)

    @property
    @_times_cache
    def times(self) -> np.ndarray:
        return np.array([float(self.floats(self._t(k))[0]) for k in range(self.n_frames)])

    def frame(self, k: int) -> List[np.ndarray]:
        records = self.read_many(self._t(k) + 1, self.n_patches)
        return [np.frombuffer(b, dtype="<f4")[:size].astype(np.float32) for b, size in zip(records, self.sizes)]


class Plot3DStream(RecordFile):
    """``*.q``: grid size, four header numbers, then the five quantities over the mesh nodes."""
    kind = "plot3d"

    def __init__(self, path: str, use_cache: bool = True) -> None:
        super().__init__(path, use_cache)
        _need(self, 3)
        self.shape = tuple(self.ints(0))
        if len(self.shape) != 3:
            raise StreamError(f"{path}: not a Plot3D q file")

    def data(self) -> np.ndarray:
        """``(5, nx, ny, nz)``."""
        a = self.floats(2)
        n = int(np.prod(self.shape))
        if a.size < 5 * n:
            raise StreamError(f"{self.path}: data record is short")
        # FDS writes variable 1 for the whole mesh (x fastest), then variable 2, ...: five blocks, not interleaved values
        return np.moveaxis(a[:5 * n].reshape(self.shape + (5,), order="F"), -1, 0).astype(np.float32)


def rle_decode(buf: bytes, expected: int) -> np.ndarray:
    """Expand FDS's run-length coding: byte 255 introduces (value, count); anything else is a literal."""
    a = np.frombuffer(buf, dtype=np.uint8)
    mark = a == 255
    if not mark.any():
        out = a
    else:
        pos = np.flatnonzero(mark)
        pos = pos[pos + 2 < a.size]
        skip = np.zeros(a.size, dtype=bool)
        skip[pos] = skip[pos + 1] = skip[pos + 2] = True
        lit = np.flatnonzero(~skip)
        order = np.argsort(np.concatenate([lit, pos]), kind="stable")
        vals = np.concatenate([a[lit], a[pos + 1]])[order]
        counts = np.concatenate([np.ones(lit.size, dtype=np.int64), a[pos + 2].astype(np.int64)])[order]
        out = np.repeat(vals, counts)
    if out.size != expected:
        raise StreamError(f"smoke frame decodes to {out.size} bytes, expected {expected}")
    return out


class Smoke3DStream(RecordFile):
    """``*.s3d``: ``(1, version, i1 i2 j1 j2 k1 k2)``, then per frame time, (bytes, compressed bytes), data."""
    kind = "smoke3d"

    def __init__(self, path: str, use_cache: bool = True) -> None:
        super().__init__(path, use_cache)
        _need(self, 1)
        h = self.ints(0)
        if len(h) != 8 or h[0] != 1:
            raise StreamError(f"{path}: not a smoke3d file")
        self.version = h[1]
        self.ijk = h[2:]
        self.shape = (h[3] - h[2] + 1, h[5] - h[4] + 1, h[7] - h[6] + 1)

    @property
    def n_frames(self) -> int:
        return (self.n_records - 1) // 3

    @property
    @_times_cache
    def times(self) -> np.ndarray:
        return np.array([float(self.floats(1 + 3 * k)[0]) for k in range(self.n_frames)])

    def frame_bytes(self, k: int) -> np.ndarray:
        """The frame as 8-bit node values, shape (nx, ny, nz)."""
        nin, nout = self.ints(2 + 3 * k)[:2]
        flat = rle_decode(self.read(3 + 3 * k)[:nout], nin)
        return flat.reshape(self.shape, order="F")


def open_stream(kind: str, path: str, use_cache: bool = True) -> RecordFile:
    cls = {"slice": SliceStream, "boundary": BoundaryStream, "particles": ParticleStream, "isosurface": IsoStream,
           "plot3d": Plot3DStream, "smoke3d": Smoke3DStream}[kind]
    return cls(path, use_cache)
