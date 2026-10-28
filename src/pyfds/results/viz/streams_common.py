"""Record files and helpers shared by the stream readers."""
from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from typing import List, Tuple

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
            c = json.loads(Path(self.cache_path).read_text(encoding="utf-8"))
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
            Path(self.cache_path).write_text(encoding="utf-8", data=json.dumps({"v": CACHE_VERSION, "sig": self._signature(), "end": self._end,
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

    def read_many(self, first: int, count: int) -> List[bytes]:
        """Records ``first .. first+count-1`` with one open and one read: they lie back to back in the file, and a
        boundary frame has one record per patch (opening the file per record made a frame of 1,000 patches ~0.3 s)."""
        recs = self._rec[first:first + count]
        if not recs:
            return []
        start, end = recs[0][0], recs[-1][0] + recs[-1][1]
        with open(self.path, "rb") as fh:
            fh.seek(start)
            buf = fh.read(end - start)
        return [buf[off - start:off - start + n] for off, n in recs]

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
