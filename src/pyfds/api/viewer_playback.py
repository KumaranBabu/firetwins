"""ViewerManager: timeline, playback and frames."""
from __future__ import annotations

import copy
import threading
from typing import Any, Callable, List, Optional, Sequence, Tuple

import numpy as np

from pyfds.results.playback import Playback
from pyfds.results.viz import data3d as d3
from pyfds.results.viz import timelines as tml
from pyfds.results.viz import transform as xf
from pyfds.results.viz import views as vw
from pyfds.results.viz.floors import FloorLayout
from pyfds.results.viz.primitives import RectilinearVolume
from pyfds.results.viz.tree import NavNode, RESULT_KINDS

from .viewer_types import Frame


class ViewerManagerPlaybackMixin:
    # -- time ---------------------------------------------------------------------------------------------
    def timeline(self) -> np.ndarray:
        if self.dataset is None:
            return np.array([])
        return self.dataset.timeline(self.active_leaves())

    def time_range(self) -> Tuple[float, float]:
        tl = self.timeline()
        tour = vw.active_tour(self.viz)
        tr = tour.time_range if tour is not None else None
        active = (float(tl[0]), float(tl[-1])) if len(tl) else None
        if active is None and self.run is not None and len(self.run.times):
            active = (float(self.run.times[0]), float(self.run.times[-1]))
        return tml.view_range(self.viz.timelines, active, tr)

    @property
    def playback(self) -> Optional[Playback]:
        """Playback over the current timeline; ``None`` when nothing animated is active. The position survives changes."""
        tl = self.timeline()
        lo, hi = self.time_range()
        if len(tl):
            tl = tl[(tl >= lo - 1e-9) & (tl <= hi + 1e-9)]
        if len(tl) == 0:
            self._playback = None
            return None
        if self._playback is None or not np.array_equal(self._playback.times, tl):
            old = self._playback
            self._playback = Playback(tl)
            self._playback.seek_time(old.time if old is not None else self.time)
            self._playback.set_speed(self.viz.playback_speed)
            self._playback.set_loop(self.viz.playback_loop)
        return self._playback

    def set_time(self, t: float) -> float:
        pb = self.playback
        if pb is not None:
            pb.seek_time(t)
            self.time = float(pb.time)
        else:
            self.time = float(t)
        return self.time

    def set_speed(self, speed: float) -> None:
        if not speed > 0:
            raise ValueError("speed must be positive")
        self.viz.playback_speed = float(speed)
        if self._playback is not None:
            self._playback.set_speed(speed)

    def set_loop(self, loop: bool) -> None:
        self.viz.playback_loop = bool(loop)
        if self._playback is not None:
            self._playback.set_loop(loop)

    # -- frames --------------------------------------------------------------------------------------------
    def _layout(self) -> Optional[FloorLayout]:
        f = self.viz.floors
        if len(f.floors) < 2 or self.run is None:
            return None
        return FloorLayout(f, self.run.bounds())

    def frame(self, t: Optional[float] = None) -> Frame:
        with self.lock:
            return self._frame(t)

    def _frame(self, t: Optional[float] = None) -> Frame:
        """Shapes of every active result at time *t* (default: the current time), clipped by the active view's
        section box and arranged by the floor layout."""
        t = self.time if t is None else float(t)
        fr = Frame(t)
        if self.dataset is None:
            return fr
        planes = vw.clip_planes(vw.active_section(self.viz))
        layout = self._layout()
        for leaf in self.active_leaves():
            if leaf.kind == "view":
                continue
            prims = self._primitives(leaf, t)
            for p in prims:
                p = xf.clip_primitive(p, planes) if planes else p
                if p is not None and layout is not None:
                    p = xf.layout_primitive(p, layout)
                if p is not None:
                    fr.items.append((leaf, p))
        fr.overlay = tml.overlay_text(self.viz.timelines, self.viz.time_display, t)
        tour = vw.active_tour(self.viz)
        fr.camera = vw.camera_at(tour, t) if tour is not None and tour.keyframes else copy.deepcopy(self.viz.camera)
        fr.colorbars = self.colorbars()
        return fr

    def _primitives(self, leaf: NavNode, t: float) -> List[Any]:
        """Shapes of one result at *t*: skipped when its renderer is set to "disabled" (Preferences ▸ Rendering), large
        volumes thinned when level of detail is on, and the last few frames remembered so playback and scrubbing back
        and forth do not read the files again."""
        setting = self._DISABLED.get(leaf.kind)
        if setting and getattr(self.viz.rendering, setting) == "disabled":
            return []
        key = (leaf.id, round(float(t), 6))
        hit = self._pcache.get(key)
        if hit is not None:
            self._pcache.move_to_end(key)
            return hit
        prims = (self._data3d_primitives(leaf, t) if leaf.kind.startswith("data3d_") else self.dataset.primitives(leaf, t))
        if self.viz.rendering.level_of_detail:
            prims = [xf.thin_volume(p) if isinstance(p, RectilinearVolume) else p for p in prims]
        self._pcache[key] = prims
        while len(self._pcache) > self.PCACHE_SIZE:
            self._pcache.popitem(last=False)
        return prims

    def cache_frames(self, node_ids: Optional[Sequence[str]] = None, progress: Optional[Callable[[int, int], bool]] = None) -> int:
        """"Cache results for smooth playback": read every frame of the given (default: all active) results into the frame
        memory. *progress(done, total)* may return False to stop. Returns the number of frames now cached; the memory
        holds ``PCACHE_SIZE`` frames, so longer animations keep the most recent ones."""
        leaves = [self.node(i) for i in node_ids] if node_ids else self.active_leaves()
        leaves = [l for l in leaves if l.kind in RESULT_KINDS]
        work = [(l, float(t)) for l in leaves for t in self.dataset.leaf_times(l) + self.dataset.offset] if self.dataset else []
        done = 0
        for leaf, t in work:
            with self.lock:
                self._primitives(leaf, t)
            done += 1
            if progress is not None and progress(done, len(work)) is False:
                break
        return done

    def prefetch_async(self, ahead: int = 8) -> Optional[threading.Thread]:
        """Load the next *ahead* frames on a background thread (Preferences ▸ Rendering ▸ asynchronous frame loading).
        Does nothing, and returns ``None``, when that option is off."""
        if not self.viz.rendering.async_frames or self._playback is None:
            return None
        pb = self._playback
        times = [float(t) for t in pb.times[pb.index + 1:pb.index + 1 + ahead]]
        leaves = list(self.active_leaves())

        def work() -> None:
            for t in times:
                for leaf in leaves:
                    if leaf.kind in RESULT_KINDS:
                        with self.lock:
                            try:
                                self._primitives(leaf, t)
                            except Exception:
                                return
        th = threading.Thread(target=work, daemon=True)
        th.start()
        return th

    def point_series(self, obj_id: str) -> Tuple[np.ndarray, np.ndarray]:
        """Value of a Data3D point at every frame of its data (what Show Plot / Export Data use)."""
        o = next((p for p in self.viz.data3d_points if p.id == obj_id), None)
        if o is None:
            raise KeyError(f"no Data3D point {obj_id!r}")
        leaves = self._group_leaves(o.group)
        times = np.unique(np.concatenate([self.dataset.leaf_times(l) for l in leaves])) + self.dataset.offset
        vals = []
        for t in times:
            v = [d3.sample_point(vol, o.xyz) for l in leaves for vol in self.dataset.primitives(l, float(t)) if d3.inside(vol, o.xyz)]
            vals.append(v[0] if v else np.nan)
        return times, np.array(vals)
