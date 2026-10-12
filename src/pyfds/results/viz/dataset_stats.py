"""ResultsDataset: colour bar statistics and their cache."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from . import colorbar as cb
from . import units as un
from .tree import NavNode

from .dataset_common import QuantityStats, STATS_VERSION


class ResultsDatasetStatsMixin:
    # -- statistics for colorbars --------------------------------------------------------------------------
    def stats(self, quantity: str, leaves: Sequence[NavNode]) -> QuantityStats:
        """Min, max and the middle 98 % of every value of *quantity* over all time (sampled; cached)."""
        mine = [l for l in leaves if l.quantity == quantity and l.kind in ("slice2d", "slice3d", "boundary", "plot3d",
                                                                          "smoke3d", "slice_vectors")]
        key = quantity + "|" + "|".join(sorted(f"{l.kind}:{f}" for l in mine for f in l.files))
        if key in self._stats:
            return self._stats[key]
        disk = self._load_stats(key, mine)
        if disk is not None:
            self._stats[key] = disk
            return disk
        samples: List[np.ndarray] = []
        for leaf in mine:
            for arr in self._sample_values(leaf):
                samples.append(np.asarray(arr, dtype=np.float32).ravel())
        if not samples:
            stats = QuantityStats(0.0, 1.0, 0.0, 1.0, 0)
        else:
            v = np.concatenate(samples)
            v = v[np.isfinite(v)]
            if v.size > 2_000_000:
                v = v[np.random.default_rng(0).choice(v.size, 2_000_000, replace=False)]
            stats = QuantityStats(0, 1, 0, 1, 0)
            if v.size:
                lo, hi = float(v.min()), float(v.max())
                p1, p99 = float(np.percentile(v, 1)), float(np.percentile(v, 99))
                if p99 - p1 < 0.01 * (hi - lo):          # a sparse quantity (flame: zero almost everywhere): the middle 98 % is empty
                    p1, p99 = lo, hi
                stats = QuantityStats(lo, hi, p1, p99, int(v.size))
        self._stats[key] = stats
        self._save_stats(key, mine, stats)
        return stats

    def _sample_values(self, leaf: NavNode, max_frames: int = 24):
        def picks(n):
            return np.unique(np.linspace(0, n - 1, min(n, max_frames)).astype(int)) if n else []
        if leaf.kind in ("slice2d", "slice3d", "slice_vectors"):
            s = self.stream("slice", leaf.files[0])
            for k in picks(s.n_frames):
                yield s.frame(int(k))
        elif leaf.kind == "boundary":
            s = self.stream("boundary", leaf.files[0])
            for k in picks(s.n_frames):
                yield from s.frame(int(k))
        elif leaf.kind == "plot3d":
            for f in leaf.files[:max_frames]:
                yield self.stream("plot3d", f).data()[leaf.data["index"]]
        elif leaf.kind == "smoke3d":
            s = self.stream("smoke3d", leaf.files[0])
            for k in picks(s.n_frames):
                yield self._smoke_values(leaf, s.frame_bytes(int(k)))[1]

    def _stats_path(self) -> Path:
        return Path(self.run.path + ".pyfstats")

    def _fingerprint(self, leaves: Sequence[NavNode]) -> str:
        parts = []
        for l in leaves:
            for f in l.files:
                p = self.run.resolve(f)
                parts.append(f"{f}:{p.stat().st_size if p.exists() else 0}")
        return ";".join(parts)

    def _load_stats(self, key: str, leaves: Sequence[NavNode]) -> Optional[QuantityStats]:
        if not self.use_cache or not self._stats_path().exists():
            return None
        try:
            c = json.loads(self._stats_path().read_text())
            e = c.get("v") == STATS_VERSION and c["entries"].get(key)
            if e and e["fp"] == self._fingerprint(leaves):
                return QuantityStats(**e["stats"])
        except (OSError, ValueError, KeyError):
            pass
        return None

    def _save_stats(self, key: str, leaves: Sequence[NavNode], stats: QuantityStats) -> None:
        if not self.use_cache:
            return
        try:
            c = json.loads(self._stats_path().read_text()) if self._stats_path().exists() else {}
            if c.get("v") != STATS_VERSION:
                c = {"v": STATS_VERSION, "entries": {}}
            c["entries"][key] = {"fp": self._fingerprint(leaves), "stats": stats.__dict__}
            self._stats_path().write_text(json.dumps(c))
        except OSError:
            pass

    def colorbar(self, quantity: str, units: str, leaves: Sequence[NavNode]) -> cb.ColorbarModel:
        """The colorbar for *quantity* in the user's display units (range from the stats and the range mode)."""
        props = self.viz.fds.colorbar(quantity)
        st = self.stats(quantity, leaves)
        conv = lambda v: float(un.convert(np.array([v]), units, self.viz.units)[0][0])
        scaled = QuantityStats(conv(st.min), conv(st.max), conv(st.p1), conv(st.p99), st.n)
        lo, hi = cb.data_range(props, scaled)
        return cb.ColorbarModel(props, lo, hi)
