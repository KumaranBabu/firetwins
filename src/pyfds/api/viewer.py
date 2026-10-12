"""The results viewer's API: ``api.viewer``.

One object owns the *visualization* (what is loaded and how it is shown), the parsed run, the navigation
tree, the data set and the playback clock. The desktop window, scripts, the command line and the agent all
drive the viewer through it, so a script and a mouse click do exactly the same thing. Nothing here draws:
``frame(t)`` returns shapes, and whatever owns a 3D window (or a test) draws them.
"""
from __future__ import annotations

import collections
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from pyfds.results.playback import Playback
from pyfds.results.viz import model as vm
from pyfds.results.viz.dataset import ResultsDataset
from pyfds.results.viz.fds_run import FdsRun, parse_smv
from pyfds.results.viz.primitives import GeometryBoxes
from pyfds.results.viz.tree import ActivationModel, ActivationResult, NavNode, build_tree
from .viewer_ext import ViewerExtras

from .viewer_colorbars import (  # noqa: F401  (re-exported)
    ViewerManagerColorbarsMixin,
)
from .viewer_data3d import (  # noqa: F401  (re-exported)
    ViewerManagerData3DMixin,
)
from .viewer_playback import (  # noqa: F401  (re-exported)
    ViewerManagerPlaybackMixin,
)
from .viewer_prefs import (  # noqa: F401  (re-exported)
    ViewerManagerPrefsMixin,
)
from .viewer_types import (  # noqa: F401  (re-exported)
    Frame,
)

from .viewer_types import (  # noqa: F401  (re-exported)
    Frame,
)


class ViewerManager(ViewerManagerPlaybackMixin, ViewerManagerColorbarsMixin, ViewerManagerPrefsMixin, ViewerManagerData3DMixin, ViewerExtras):
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

    _DISABLED = {"data3d_slice": "data3d_slice_renderer", "data3d_iso": "data3d_renderer", "data3d_point": "data3d_renderer"}

    PCACHE_SIZE = 96
