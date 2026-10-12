"""The results viewer's API: ``api.viewer``.

One object owns the *visualization* (what is loaded and how it is shown), the parsed run, the navigation
tree, the data set and the playback clock. The desktop window, scripts, the command line and the agent all
drive the viewer through it, so a script and a mouse click do exactly the same thing. Nothing here draws:
``frame(t)`` returns shapes, and whatever owns a 3D window (or a test) draws them.
"""
from __future__ import annotations

import collections
import copy
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from pyfds.results.playback import Playback
from pyfds.results.viz import colorbar as cb
from pyfds.results.viz import data3d as d3
from pyfds.results.viz import model as vm
from pyfds.results.viz import timelines as tml
from pyfds.results.viz import transform as xf
from pyfds.results.viz import units as un
from pyfds.results.viz import views as vw
from pyfds.results.viz.dataset import ResultsDataset
from pyfds.results.viz.fds_run import FdsRun, parse_smv
from pyfds.results.viz.floors import FloorLayout
from pyfds.results.viz.primitives import GeometryBoxes, GridSurface, PointCloud, RectilinearVolume
from pyfds.results.viz.tree import ActivationModel, ActivationResult, NavNode, RESULT_KINDS, build_tree

from .viewer_ext import ViewerExtras


@dataclass
class Frame:
    """Everything to draw at one playback time."""
    time: float
    items: List[Tuple[NavNode, Any]] = field(default_factory=list)       # (node, primitive)
    overlay: str = ""
    camera: Optional[vm.Viewpoint] = None
    colorbars: List[Tuple[str, str, cb.ColorbarModel]] = field(default_factory=list)   # (quantity, units, bar)

    def of_kind(self, kind: str) -> List[Any]:
        return [p for n, p in self.items if n.kind == kind]


class ViewerManager(ViewerExtras):
    def __init__(self, api) -> None:
        self._api = api
        self.viz = vm.ResultsVisualization()
        self.path: Optional[str] = None
        self._dirty = False
        self._pcache: "collections.OrderedDict" = collections.OrderedDict()
        self.lock = threading.RLock()                 # guards the dataset: frame() and prefetch() may run on different threads
        self.run: Optional[FdsRun] = None
        self.dataset: Optional[ResultsDataset] = None
        self.tree: NavNode = build_tree(None, self.viz)
        self.activation = ActivationModel(self.tree, self.viz)
        self._playback: Optional[Playback] = None
        self.time = 0.0
        self.csv_cache: Dict[str, Any] = {}
        self._init_extras()

    @property
    def dirty(self) -> bool:
        return self._dirty

    @dirty.setter
    def dirty(self, value: bool) -> None:
        if value:
            self._pcache.clear()                      # any change of settings may change what a frame looks like
        self._dirty = bool(value)

    # -- session --------------------------------------------------------------------------------------
    def new(self) -> vm.ResultsVisualization:
        """File ▸ New Results Visualization: empty, nothing loaded."""
        self.viz = vm.ResultsVisualization()
        self.path, self.dirty, self.run, self.dataset, self.time = None, False, None, None, 0.0
        self._playback = None
        self.csv_cache.clear()
        self._rebuild()
        return self.viz

    def open_visualization(self, path: str) -> vm.ResultsVisualization:
        """File ▸ Open Results Visualization: settings come back, and the results load when they are still there."""
        viz = vm.load(path)
        self.viz, self.path, self.dirty = viz, str(path), False
        self.run = self.dataset = None
        self._playback = None
        self.time = 0.0
        if viz.results and Path(viz.results).exists():
            self._attach_run(viz.results)
        elif viz.results:
            self.missing_results = viz.results
        if not viz.general.show_previous_on_open:
            viz.active = []
        self._rebuild()
        return viz

    def save(self, path: Optional[str] = None) -> str:
        """File ▸ Save Results Visualization (Save As when *path* is given)."""
        target = path or self.path
        if not target:
            raise ValueError("this visualization has no file yet: give a path")
        self.path = vm.save(self.viz, target)
        self.dirty = False
        return self.path

    def default_visualization_path(self, smv: str) -> str:
        """The visualization that belongs to an ``.smv`` (same folder and name), used when results are opened."""
        return str(Path(smv).with_suffix(vm.EXTENSION))

    def open_results(self, smv: str) -> vm.ResultsVisualization:
        """Open a run the way double-clicking its ``.smv`` does: its saved visualization if one exists, else a new one."""
        vis = self.default_visualization_path(smv)
        if Path(vis).exists():
            self.open_visualization(vis)
            if not self.run:
                self.load_results(smv)
        else:
            self.new()
            self.load_results(smv)
            self.path = vis
        return self.viz

    def load_results(self, smv: str) -> FdsRun:
        """File ▸ Load Results: the previous settings are kept and applied to the new run."""
        self._attach_run(smv)
        self.viz.results = str(Path(smv).resolve())
        self.dirty = True
        self._rebuild()
        return self.run

    def unload_results(self) -> None:
        """File ▸ Unload FDS Results: the run goes, the settings stay."""
        self.run = self.dataset = None
        self._playback = None
        self.viz.results = None
        self.dirty = True
        self._rebuild()

    def _attach_run(self, smv: str) -> None:
        self.run = parse_smv(smv)
        self.dataset = ResultsDataset(self.run, self.viz)
        self.dataset.requested_geometry = self._requested_geometry
        self.dataset.model_geometry = self._model_geometry
        self.missing_results = None

    missing_results: Optional[str] = None

    def _rebuild(self) -> None:
        self._pcache.clear()
        have_model = bool(self._api.project.obstructions)
        self.tree = build_tree(self.run, self.viz, have_model)
        self.activation = ActivationModel(self.tree, self.viz)
        self.activation.prune()
        if self.run is not None and not self.viz.active and not self.viz.floors.floors:
            self.viz.floors.floors = []
        if self.dataset is not None:
            self.dataset.viz = self.viz
        self._playback = None

    def refresh(self) -> Dict[str, Any]:
        """File ▸ Refresh Results (F5): new frames of a running case; the playback position is kept."""
        if self.run is None:
            return {"records": 0, "reloaded": False}
        mtime = Path(self.run.path).stat().st_mtime
        reloaded = False
        if mtime != getattr(self, "_smv_mtime", mtime):
            self._attach_run(self.run.path)
            self._rebuild()
            reloaded = True
        self._smv_mtime = mtime
        n = self.dataset.refresh() if self.dataset else 0
        self._pcache.clear()
        self._playback = None
        return {"records": n, "reloaded": reloaded}

    # -- geometry sets that come from a model -------------------------------------------------------------
    def _model_geometry(self) -> GeometryBoxes:
        obs = self._api.project.obstructions
        return GeometryBoxes("Model obstructions", [(o.x_min, o.x_max, o.y_min, o.y_max, o.z_min, o.z_max) for o in obs],
                             [o.name for o in obs])

    def _requested_geometry(self) -> GeometryBoxes:
        """What was asked for in the FDS input file (may not line up with the mesh)."""
        from pyfds.io.fds_parser import FdsParser
        run = self.run
        cand = [Path(run.input_file)] if run.input_file else []
        cand.append(run.directory / f"{run.chid}.fds")
        path = next((c for c in cand if c.exists()), None)
        if path is None:
            return GeometryBoxes("Requested", [])
        proj = FdsParser().parse_string(path.read_text(errors="replace"))
        return GeometryBoxes("Requested obstructions", [(o.x_min, o.x_max, o.y_min, o.y_max, o.z_min, o.z_max)
                                                         for o in proj.obstructions], [o.name for o in proj.obstructions])

    # -- the tree ---------------------------------------------------------------------------------------
    def node(self, node_id: str) -> NavNode:
        n = self.tree.find(node_id)
        if n is None:
            raise KeyError(f"no node {node_id!r}")
        return n

    def toggle(self, node_id: str) -> ActivationResult:
        r = self.activation.toggle(node_id)
        self._changed(r)
        return r

    def activate(self, node_id: str) -> ActivationResult:
        r = self.activation.activate(node_id)
        self._changed(r)
        return r

    def deactivate(self, node_id: str) -> ActivationResult:
        r = self.activation.deactivate(node_id)
        self._changed(r)
        return r

    def _changed(self, r: ActivationResult) -> None:
        self.dirty = True
        self._playback = None
        if r.activated and self.viz.general.begin_playback_on_activation:
            pb = self.playback
            if pb is not None:
                if not (pb.times[0] <= self.time <= pb.times[-1]):
                    pb.seek_index(0)
                    self.time = float(pb.times[0])
                if pb.times[-1] > pb.times[0]:
                    pb.play()

    def active_leaves(self) -> List[NavNode]:
        return self.activation.active_nodes()

    def node_state(self, node_id: str) -> str:
        return self.activation.state(self.node(node_id))

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

    _DISABLED = {"data3d_slice": "data3d_slice_renderer", "data3d_iso": "data3d_renderer", "data3d_point": "data3d_renderer"}
    PCACHE_SIZE = 96

    def _primitives(self, leaf: NavNode, t: float) -> List[Any]:
        """Shapes of one result at *t*: skipped when its renderer is set to "disabled" (Preferences ▸ Rendering), large
        volumes thinned when level of detail is on, and the last few frames remembered so playback and scrubbing back
        and forth do not read the files again."""
        field = self._DISABLED.get(leaf.kind)
        if field and getattr(self.viz.rendering, field) == "disabled":
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

    # -- colorbars -------------------------------------------------------------------------------------------
    def colorbars(self) -> List[Tuple[str, str, cb.ColorbarModel]]:
        """One colorbar per quantity among the active results that use one (smoke and plain particles do not)."""
        out, seen = [], set()
        leaves = [l for l in self.tree.leaves() if l.kind in RESULT_KINDS]
        for leaf in self.active_leaves():
            if leaf.kind not in RESULT_KINDS or leaf.kind in ("max_error",) or leaf.quantity in seen:
                continue
            if leaf.kind == "particles":
                props = self.viz.particles.get(str(leaf.data.get("class")))
                if not props or props.color == "default":
                    continue
            if leaf.kind == "smoke3d" and leaf.quantity.upper() in ("SOOT DENSITY",):
                continue
            if leaf.kind == "isosurface" or leaf.kind.startswith("data3d_"):
                continue
            seen.add(leaf.quantity)
            _, units = un.convert(np.zeros(1), leaf.units, self.viz.units)
            out.append((leaf.quantity, units, self.dataset.colorbar(leaf.quantity, leaf.units, leaves)))
        return out

    def colorbar(self, quantity: str) -> cb.ColorbarModel:
        leaves = [l for l in self.tree.leaves() if l.kind in RESULT_KINDS and l.quantity == quantity]
        if not leaves or self.dataset is None:
            raise KeyError(f"no results of quantity {quantity!r}")
        return self.dataset.colorbar(quantity, leaves[0].units, [l for l in self.tree.leaves() if l.kind in RESULT_KINDS])

    def set_colorbar(self, quantity: str, **fields: Any) -> vm.ColorbarProps:
        """Change colorbar properties; nothing changes when any value is invalid."""
        props = self.viz.fds.colorbar(quantity)
        unknown = set(fields) - set(vm.ColorbarProps.__dataclass_fields__)
        if unknown:
            raise AttributeError(f"unknown colorbar properties: {sorted(unknown)}")
        trial = copy.deepcopy(props)
        for k, v in fields.items():
            setattr(trial, k, v)
        bad = trial.problems()
        if bad:
            raise ValueError("; ".join(bad))
        self.viz.fds.colorbars[quantity] = trial
        self.dirty = True
        return trial

    def copy_colorbar(self, source: str, targets: Sequence[str]) -> None:
        """The Copy button of FDS Preferences: give other quantities the same colorbar settings."""
        src = self.viz.fds.colorbar(source)
        for q in targets:
            self.viz.fds.colorbars[q] = copy.deepcopy(src)
        self.dirty = True

    def reset_colorbar(self, quantity: str) -> None:
        self.viz.fds.colorbars[quantity] = vm.default_colorbar(quantity)
        self.dirty = True

    def highlight_colorbar(self, quantity: str, fraction: Optional[float], width_fraction: float = 0.05) -> None:
        """Click on the colorbar adds a highlight region there; ``None`` (right-click) removes it."""
        props = self.viz.fds.colorbar(quantity)
        if fraction is None:
            cb.clear_highlight(props)
        else:
            bar = self.colorbar(quantity)
            cb.highlight_at(props, bar.lo, bar.hi, fraction, width_fraction)
        self.dirty = True

    def set_fds_preferences(self, time_offset: Optional[float] = None, interpolate: Optional[bool] = None,
                            obscure_types: Optional[Sequence[str]] = None) -> vm.FdsPreferences:
        f = self.viz.fds
        if time_offset is not None:
            f.time_offset = float(time_offset)
        if interpolate is not None:
            f.interpolate = bool(interpolate)
        if obscure_types is not None:
            f.obscure_types = list(obscure_types)
        self._playback = None
        self.dirty = True
        return f

    # -- per-kind properties --------------------------------------------------------------------------------
    def set_smoke3d(self, preset: Optional[str] = None, **fields: Any) -> vm.Smoke3DProps:
        p = copy.deepcopy(self.viz.smoke3d)
        if preset is not None:
            vm.apply_smoke_preset(p, preset)
        for k, v in fields.items():
            if k not in vm.Smoke3DProps.__dataclass_fields__:
                raise AttributeError(f"unknown smoke property {k!r}")
            setattr(p, k, v)
        if fields and preset is None and p.preset != "custom":
            p.preset = "custom"
        bad = p.problems()
        if bad:
            raise ValueError("; ".join(bad))
        self.viz.smoke3d = p
        self.dirty = True
        return p

    def set_slice_vectors(self, node_id: str, factor: Optional[float] = None, step: Optional[int] = None) -> vm.SliceVectorProps:
        node = self.node(node_id)
        p = self.viz.slice_vectors.setdefault(node.quantity + "|" + node.label, vm.SliceVectorProps())
        if factor is not None:
            if factor <= 0:
                raise ValueError("vector factor must be positive")
            p.factor = float(factor)
        if step is not None:
            if step < 1:
                raise ValueError("vector step must be at least 1")
            p.step = int(step)
        self.dirty = True
        return p

    def set_particles(self, class_name: str, trail_time: Optional[float] = None, color: Optional[str] = None,
                      size: Optional[float] = None) -> vm.ParticleProps:
        p = self.viz.particles.setdefault(class_name, vm.ParticleProps())
        if trail_time is not None:
            if trail_time < 0:
                raise ValueError("trail time must not be negative")
            p.trail_time = float(trail_time)
        if color is not None:
            names = {q[0] for c in (self.run.particle_classes if self.run else []) if c.name == class_name for q in c.quantities}
            if color != "default" and self.run is not None and color not in names:
                raise KeyError(f"particle class {class_name!r} has no quantity {color!r}; has {sorted(names)}")
            p.color = color
        if size is not None:
            if size <= 0:
                raise ValueError("particle size must be positive")
            p.size = float(size)
        self.dirty = True
        return p

    def set_data3d_properties(self, group_id: str, sample_factor: float) -> None:
        if sample_factor <= 0:
            raise ValueError("sample factor must be positive")
        self.viz.data3d[group_id] = vm.Data3DProps(float(sample_factor))
        self.dirty = True

    # -- Data3D objects ---------------------------------------------------------------------------------------
    def _group_leaves(self, group_id: str) -> List[NavNode]:
        g = self.node(group_id)
        leaves = [l for l in g.leaves() if l.kind in ("slice3d", "plot3d")]
        if not leaves:
            raise ValueError("Data3D objects are made from a 3D Slices or Plot3D quantity")
        return leaves

    def _next_id(self, prefix: str, items: Sequence[Any]) -> str:
        n = 1
        names = {o.id for o in items}
        while f"{prefix} {n}" in names:
            n += 1
        return f"{prefix} {n}"

    def add_data3d_point(self, group_id: str, xyz: Sequence[float]) -> vm.Data3DPoint:
        leaves = self._group_leaves(group_id)
        t = float(self.timeline()[0]) if len(self.timeline()) else self.run.times[0]
        vols = [v for l in leaves for v in self.dataset.primitives(l, t)]
        if not any(d3.inside(v, xyz) for v in vols):
            raise ValueError("the point must be inside one of the regions of this quantity")
        o = vm.Data3DPoint(self._next_id("Point", self.viz.data3d_points), group_id, leaves[0].quantity,
                           tuple(float(c) for c in xyz))                        # type: ignore[arg-type]
        self.viz.data3d_points.append(o)
        self._rebuild()
        self.dirty = True
        return o

    def add_data3d_slice(self, group_id: str, origin: Sequence[float], normal: Sequence[float]) -> vm.Data3DSlice:
        leaves = self._group_leaves(group_id)
        if np.linalg.norm(normal) == 0:
            raise ValueError("the plane normal must not be zero")
        o = vm.Data3DSlice(self._next_id("Slice", self.viz.data3d_slices), group_id, leaves[0].quantity,
                           tuple(float(c) for c in origin), tuple(float(c) for c in normal))   # type: ignore[arg-type]
        self.viz.data3d_slices.append(o)
        self._rebuild()
        self.dirty = True
        return o

    def add_data3d_isosurface(self, group_id: str, value: float) -> vm.Data3DIso:
        leaves = self._group_leaves(group_id)
        o = vm.Data3DIso(self._next_id("Isosurface", self.viz.data3d_isos), group_id, leaves[0].quantity, float(value))
        self.viz.data3d_isos.append(o)
        self._rebuild()
        self.dirty = True
        return o

    def remove_data3d(self, obj_id: str) -> None:
        for lst in (self.viz.data3d_points, self.viz.data3d_slices, self.viz.data3d_isos):
            for o in lst:
                if o.id == obj_id:
                    lst.remove(o)
                    self.viz.active = [a for a in self.viz.active if not a.endswith("/" + obj_id)]
                    self._rebuild()
                    self.dirty = True
                    return
        raise KeyError(f"no Data3D object {obj_id!r}")

    def _find_data3d(self, leaf: NavNode):
        oid = leaf.data["obj_id"]
        for o in self.viz.data3d_points + self.viz.data3d_slices + self.viz.data3d_isos:
            if o.id == oid:
                return o
        raise KeyError(oid)

    def _data3d_primitives(self, leaf: NavNode, t: float) -> List[Any]:
        o = self._find_data3d(leaf)
        vols = [v for l in self._group_leaves(o.group) for v in self.dataset.primitives(l, t)]
        out: List[Any] = []
        if leaf.kind == "data3d_point":
            vals = [d3.sample_point(v, o.xyz) for v in vols if d3.inside(v, o.xyz)]
            if vals:
                out.append(PointCloud(o.id, o.quantity, vols[0].units, np.array([o.xyz]), np.array([vals[0]]), 8.0))
        elif leaf.kind == "data3d_slice":
            for v in vols:
                s = d3.slice_plane(v, o.origin, o.normal)
                if s is not None:
                    out.append(s)
        else:
            for v in vols:
                m = d3.isosurface(v, o.value)
                if len(m.faces):
                    out.append(m)
        return out

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
