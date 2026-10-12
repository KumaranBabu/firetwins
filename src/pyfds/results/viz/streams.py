"""Streaming readers for FDS binary output (slices, boundaries, particles, isosurfaces, Plot3D, smoke3D).

Every FDS binary file is a sequence of Fortran unformatted records (4-byte length, data, 4-byte length).
``RecordFile`` indexes the records once (and keeps that index in a ``.pyfcache`` file next to the data so
the next open is instant, and so a file that is still growing only has its new tail scanned); the
``*Stream`` classes then read a single frame on demand instead of loading the whole file. The layouts were
checked against real FDS 6.10.1 output (``tests/fixtures/results_room``).
"""
from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

CACHE_VERSION = 1


class StreamError(ValueError):
    """The file is not in the layout this reader understands."""


class RecordFile:
    """A Fortran-unformatted file indexed by record offsets."""

    kind = "records"

    def __init__(self, path: str, use_cache: bool = True) -> None:
        self.path = str(path)
        self.use_cache = use_cache
        self._rec: List[Tuple[int, int]] = []        # (data offset, length)
        self._end = 0                                # file position after the last indexed record
        self._load_cache()
        self.refresh()

    # -- indexing --------------------------------------------------------------------
    @property
    def cache_path(self) -> str:
        return self.path + ".pyfcache"

    def _signature(self) -> str:
        with open(self.path, "rb") as fh:
            return fh.read(64).hex()

    def _load_cache(self) -> None:
        if not self.use_cache or not os.path.exists(self.cache_path):
            return
        try:
            c = json.loads(Path(self.cache_path).read_text())
            size = os.path.getsize(self.path)
            if c.get("v") != CACHE_VERSION or c.get("sig") != self._signature() or c.get("end", 0) > size:
                return
            flat = c["records"]
            self._rec = [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
            self._end = c["end"]
        except (OSError, ValueError, KeyError):
            self._rec, self._end = [], 0

    def _save_cache(self) -> None:
        if not self.use_cache:
            return
        flat = [x for r in self._rec for x in r]
        try:
            Path(self.cache_path).write_text(json.dumps({"v": CACHE_VERSION, "sig": self._signature(), "end": self._end,
                                                         "records": flat}))
        except OSError:
            pass                                       # read-only folder: the cache is only a speed-up

    def refresh(self) -> int:
        """Index records written since the last call (a running FDS appends); returns how many were added."""
        size = os.path.getsize(self.path)
        added = 0
        with open(self.path, "rb") as fh:
            pos = self._end
            while pos + 4 <= size:
                fh.seek(pos)
                n = struct.unpack("<i", fh.read(4))[0]
                if n < 0 or pos + 8 + n > size:         # incomplete tail record: wait for FDS to finish writing it
                    break
                self._rec.append((pos + 4, n))
                pos += 8 + n
                added += 1
            self._end = pos
        if added:
            self._save_cache()
        return added

    # -- access ----------------------------------------------------------------------
    @property
    def n_records(self) -> int:
        return len(self._rec)

    def read(self, i: int) -> bytes:
        off, n = self._rec[i]
        with open(self.path, "rb") as fh:
            fh.seek(off)
            return fh.read(n)

    def ints(self, i: int) -> Tuple[int, ...]:
        b = self.read(i)
        return struct.unpack(f"<{len(b) // 4}i", b)

    def floats(self, i: int) -> np.ndarray:
        return np.frombuffer(self.read(i), dtype="<f4")

    def text(self, i: int) -> str:
        return self.read(i).decode("latin-1").strip()


def _times_cache(fn):
    """Frame times are read from every frame record (thousands of file opens for a 3D smoke run): keep them until the file grows."""
    def wrapper(self):
        hit = self.__dict__.get("_times_memo")
        if hit is not None and hit[0] == self.n_records:
            return hit[1]
        out = fn(self)
        self.__dict__["_times_memo"] = (self.n_records, out)
        return out
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def _need(f: RecordFile, n: int) -> None:
    if f.n_records < n:
        raise StreamError(f"{f.path}: file ends inside its header ({f.n_records} of {n} records)")


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
        self.patches: List[Tuple[int, ...]] = [self.ints(4 + p) for p in range(self.n_patches)]
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
        base = self._t(k)
        return [self.floats(base + 1 + p)[:self.sizes[p]].astype(np.float32) for p in range(self.n_patches)]


class ParticleStream(RecordFile):
    """``*.prt5``: endian flag, version, class count, per-class quantity list, then frames."""
    kind = "particles"

    def __init__(self, path: str, use_cache: bool = True) -> None:
        super().__init__(path, use_cache)
        _need(self, 3)
        if self.ints(0)[0] != 1:
            raise StreamError(f"{path}: unexpected endian marker")
        self.version = self.ints(1)[0]
        self.n_classes = self.ints(2)[0]
        i = 3
        self.quantities: List[List[Tuple[str, str]]] = []
        for _ in range(self.n_classes):
            _need(self, i + 1)
            nq = self.ints(i)[0]
            i += 1
            qs = []
            _need(self, i + 2 * nq)
            for q in range(nq):
                qs.append((self.text(i + 2 * q), self.text(i + 2 * q + 1)))
            i += 2 * nq
            self.quantities.append(qs)
        self._first = i
        self._frames: List[int] = []                 # record index of each frame's time record
        self._scan_from = i
        self._index_frames()

    def refresh(self) -> int:                        # noqa: D401 - extends the base class
        added = super().refresh()
        if hasattr(self, "_frames"):
            self._index_frames()
        return added

    def _index_frames(self) -> None:
        i = self._frames[-1] if self._frames else self._first
        if self._frames:
            i = self._skip_frame(i)
        else:
            i = self._first
        while i is not None and i < self.n_records:
            nxt = self._skip_frame(i)
            if nxt is None:
                break
            self._frames.append(i)
            i = nxt

    def _skip_frame(self, i: int) -> Optional[int]:
        """Record index after the frame that starts at *i*, or None when that frame is incomplete."""
        j = i + 1
        for qs in self.quantities:
            if j >= self.n_records:
                return None
            j += 3 + (1 if qs else 0)
        return j if j <= self.n_records else None

    @property
    def n_frames(self) -> int:
        return len(self._frames)

    @property
    @_times_cache
    def times(self) -> np.ndarray:
        return np.array([float(self.floats(i)[0]) for i in self._frames])

    def frame(self, k: int) -> List[Dict[str, np.ndarray]]:
        """Per class: ``positions`` (n, 3), ``tags`` (n,), ``values`` (n, nq)."""
        j = self._frames[k] + 1
        out = []
        for qs in self.quantities:
            n = self.ints(j)[0]
            xyz = self.floats(j + 1)[:3 * n].reshape(3, n).T.astype(np.float64) if n else np.zeros((0, 3))
            tags = np.frombuffer(self.read(j + 2), dtype="<i4")[:n]
            vals = (self.floats(j + 3)[:n * len(qs)].reshape(len(qs), n).T if qs and n else np.zeros((n, len(qs))))
            out.append({"positions": xyz, "tags": tags.copy(), "values": vals.astype(np.float32)})
            j += 3 + (1 if qs else 0)
        return out


class IsoStream(RecordFile):
    """``*.iso``: levels, then per frame a (time, 0) record and per level (n_vertices, n_triangles) + arrays."""
    kind = "isosurface"

    def __init__(self, path: str, use_cache: bool = True) -> None:
        super().__init__(path, use_cache)
        _need(self, 4)
        if self.ints(0)[0] != 1:
            raise StreamError(f"{path}: unexpected endian marker")
        self.version = self.ints(1)[0]
        self.n_levels = self.ints(2)[0]
        self.levels = [float(v) for v in self.floats(3)[:self.n_levels]]
        self._first = 6                               # one count record and one (0, 0) record follow the levels
        _need(self, self._first)
        self._frames: List[Tuple[int, List[int]]] = []   # (time record, record index of each level's counts)
        self._index_frames()

    def refresh(self) -> int:
        added = super().refresh()
        if hasattr(self, "_frames"):
            self._index_frames()
        return added

    def _index_frames(self) -> None:
        i = self._frames_end() if self._frames else self._first
        while i < self.n_records:
            t = i
            j = i + 1
            counts = []
            ok = True
            for _ in range(self.n_levels):
                if j >= self.n_records:
                    ok = False
                    break
                nv, nt = self.ints(j)[:2]
                counts.append(j)
                j += 1 + (3 if nv > 0 and nt > 0 else 0)
            if not ok or j > self.n_records:
                break
            self._frames.append((t, counts))
            i = j

    def _frames_end(self) -> int:
        t, counts = self._frames[-1]
        j = counts[-1]
        nv, nt = self.ints(j)[:2]
        return j + 1 + (3 if nv > 0 and nt > 0 else 0)

    @property
    def n_frames(self) -> int:
        return len(self._frames)

    @property
    @_times_cache
    def times(self) -> np.ndarray:
        return np.array([float(self.floats(t)[0]) for t, _ in self._frames])

    def frame(self, k: int) -> List[Tuple[np.ndarray, np.ndarray]]:
        """Per level: vertices (n, 3) and 0-based triangles (m, 3)."""
        out = []
        for j in self._frames[k][1]:
            nv, nt = self.ints(j)[:2]
            if nv > 0 and nt > 0:
                v = self.floats(j + 1)[:3 * nv].reshape(nv, 3).astype(np.float64)
                tri = np.frombuffer(self.read(j + 2), dtype="<i4")[:3 * nt].reshape(nt, 3) - 1
                out.append((v, tri.astype(np.int64)))
            else:
                out.append((np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)))
        return out


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
