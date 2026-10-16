"""Turns a navigation-tree leaf and a playback time into drawable primitives.

``ResultsDataset`` is the data half of the viewer: it opens the streaming readers lazily, picks (and by
default interpolates between) frames, converts units, builds smoke / fire / slice / boundary / particle
shapes in true mesh coordinates, and measures per-quantity statistics for the colorbars. It never draws.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import max_errors as me
from .fds_run import FdsRun
from .model import ResultsVisualization
from .primitives import GeometryBoxes
from .streams import open_stream
from .tree import NavNode

from .dataset_common import (  # noqa: F401  (re-exported)
    QuantityStats,
    STATS_VERSION,
)
from .dataset_primitives import (  # noqa: F401  (re-exported)
    ResultsDatasetPrimitivesMixin,
)
from .dataset_stats import (  # noqa: F401  (re-exported)
    ResultsDatasetStatsMixin,
)

from .dataset_common import (  # noqa: F401  (re-exported)
    STATS_VERSION,
)


class ResultsDataset(ResultsDatasetStatsMixin, ResultsDatasetPrimitivesMixin):
    def __init__(self, run: FdsRun, viz: ResultsVisualization, use_cache: bool = True, max_open: int = 24) -> None:
        self.run, self.viz, self.use_cache = run, viz, use_cache
        self._streams: "OrderedDict[str, object]" = OrderedDict()
        self._max_open = max_open
        self._stats: Dict[str, QuantityStats] = {}
        self._errors: Optional[Dict[str, List[me.ErrorSample]]] = None
        #: injected by the API: ``() -> GeometryBoxes`` for the sets that come from a model, not from the run
        self.requested_geometry: Optional[Callable[[], GeometryBoxes]] = None
        self.model_geometry: Optional[Callable[[], GeometryBoxes]] = None

    # -- streams -------------------------------------------------------------------------------------
    def stream(self, kind: str, file: str):
        path = str(self.run.resolve(file))
        s = self._streams.get(path)
        if s is None:
            s = open_stream(kind, path, self.use_cache)
            self._streams[path] = s
            while len(self._streams) > self._max_open:
                self._streams.popitem(last=False)
        else:
            self._streams.move_to_end(path)
        return s

    def refresh(self) -> int:
        """Pick up frames FDS has written since; returns the number of new records seen."""
        n = 0
        for s in self._streams.values():
            n += s.refresh()
        self._errors = None
        return n

    # -- time ----------------------------------------------------------------------------------------
    @property
    def offset(self) -> float:
        return self.viz.fds.time_offset + self.viz.timelines.fds_offset

    def leaf_times(self, leaf: NavNode) -> np.ndarray:
        """FDS times of the leaf's frames (before the time offset)."""
        k = leaf.kind
        if k == "slice2d" or k == "slice3d":
            return self.stream("slice", leaf.files[0]).times
        if k == "slice_vectors":
            return self.stream("slice", leaf.files[0]).times
        if k == "boundary":
            return self.stream("boundary", leaf.files[0]).times
        if k == "smoke3d":
            return self.stream("smoke3d", leaf.files[0]).times
        if k == "isosurface":
            return self.stream("isosurface", leaf.files[0]).times
        if k == "particles":
            return self.stream("particles", leaf.files[0]).times
        if k == "plot3d":
            by_name = {p.file: p.time for p in self.run.plot3d}
            return np.array(sorted(by_name[f] for f in leaf.files))
        if k == "max_error":
            s = self.errors()[leaf.data["which"]]
            return np.array([x.time for x in s])
        return np.array([self.run.times[0], self.run.times[1]])           # geometry, views: whole run

    def timeline(self, leaves: Sequence[NavNode]) -> np.ndarray:
        """The union of the leaves' frame times on the global clock (empty when nothing animated is active)."""
        parts = [self.leaf_times(l) for l in leaves if l.kind not in ("geometry", "view", "devices")]
        parts = [p for p in parts if len(p)]
        if not parts:
            return np.array([])
        return np.unique(np.round(np.concatenate(parts) + self.offset, 6))

    def _pick(self, times: np.ndarray, t_fds: float) -> Tuple[int, Optional[int], float]:
        n = len(times)
        if n == 0:
            raise ValueError("no frames")
        k = int(np.clip(np.searchsorted(times, t_fds + 1e-9) - 1, 0, n - 1))
        if not self.viz.fds.interpolate or k >= n - 1 or t_fds <= times[0] or times[k + 1] == times[k]:
            return k, None, 0.0
        a = float((t_fds - times[k]) / (times[k + 1] - times[k]))
        return k, k + 1, min(max(a, 0.0), 1.0)

    def _blend(self, get: Callable[[int], np.ndarray], times: np.ndarray, t_fds: float) -> np.ndarray:
        k0, k1, a = self._pick(times, t_fds)
        v0 = get(k0)
        if k1 is None:
            return v0
        return (1.0 - a) * v0 + a * get(k1)

    # -- errors -----------------------------------------------------------------------------------------
    def errors(self) -> Dict[str, List[me.ErrorSample]]:
        if self._errors is None:
            self._errors = me.read_max_errors(str(self.run.directory / (self.run.chid + ".out")))
        return self._errors
