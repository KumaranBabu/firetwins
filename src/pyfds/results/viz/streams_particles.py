"""Particle and isosurface stream readers."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from .streams_common import (
    RecordFile,
    StreamError,
    _need,
    _times_cache,
)


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
