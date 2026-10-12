"""In-app results scene: ``api.scene`` (C2).

Builds a renderer-agnostic :class:`~pyfds.results.scene.ResultsScene` from a case's output files, with
playback, a camera path, saved views, clip planes and probing. A view (PyVista, Qt3D ...) only has to
draw ``api.scene.frame(t)`` and listen to ``api.scene.playback``.
"""
from __future__ import annotations

import glob
import os
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from pyfds.core.viewport import ViewportCamera
from pyfds.results import scene as sc
from pyfds.results.playback import CameraPath, Playback, SavedViews
from pyfds.results.scene import ResultsScene


class SceneManager:
    def __init__(self, api) -> None:
        self._api = api
        self.scene = ResultsScene()
        self.camera_path = CameraPath()
        self.views = SavedViews()
        self._playback: Optional[Playback] = None

    # -- helpers ---------------------------------------------------------------------
    def _written_meshes(self) -> List[Any]:
        return sorted(self._api.meshes.all(), key=lambda m: (m.priority is None, m.priority or 0))

    def _mesh(self, mesh: Any = None, mesh_id: Optional[int] = None):
        if isinstance(mesh, str):
            m = self._api.meshes.get(mesh)
            if m is None:
                raise KeyError(f"mesh {mesh!r} not found")
            return m
        if mesh is not None:
            return mesh
        ordered = self._written_meshes()
        if mesh_id is not None and 1 <= mesh_id <= len(ordered):
            return ordered[mesh_id - 1]
        return ordered[0] if len(ordered) == 1 else None

    def _index(self):
        idx = self._api.results.index
        if idx is None:
            raise RuntimeError("no results opened: call api.scene.open_results(output_dir_or_smv) first")
        return idx

    # -- opening ---------------------------------------------------------------------
    def open_results(self, source: str):
        """Index a results directory or a ``.smv`` file (replaces the index, keeps existing layers)."""
        if source.lower().endswith(".smv"):
            return self._api.results.build_index_from_smv(source)
        if not os.path.isdir(source):
            raise FileNotFoundError(f"not a directory or .smv file: {source}")
        return self._api.results.build_index(source)

    def clear(self) -> None:
        self.scene = ResultsScene()
        self._playback = None

    # -- adding layers ---------------------------------------------------------------
    def _add(self, layer):
        self.scene.add(layer)
        return layer

    def add_slice_result(self, result: Any, name: Optional[str] = None, mesh: Any = None, opacity: float = 1.0):
        """Add an already-read slice (``SliceReader.read`` result)."""
        base = name or f"{result.quantity or 'slice'}"
        return self._add(sc.SliceLayer(self.scene.unique_name(base), result, self._mesh(mesh), opacity))

    def add_slices(self, quantity: Optional[str] = None, planar_only: bool = True, opacity: float = 1.0) -> List[Any]:
        """One layer per indexed slice file (optionally only a quantity)."""
        from pyfds.results.reader import SliceReader
        entries = self._index().find_slices(quantity=quantity, planar_only=planar_only)
        if not entries:
            raise LookupError("no slice files match" + (f" quantity {quantity!r}" if quantity else ""))
        out = []
        for e in entries:
            base = f"{e.short_name or e.quantity}_{os.path.splitext(os.path.basename(e.filepath))[0]}"
            out.append(self._add(sc.SliceLayer(self.scene.unique_name(base), SliceReader.read(e.filepath),
                                               self._mesh(None, e.mesh_id), opacity)))
        return out

    def add_boundary(self, quantity: Optional[str] = None, opacity: float = 1.0) -> List[Any]:
        from pyfds.results.reader import BoundaryReader
        entries = self._index().find_boundaries(quantity=quantity)
        if not entries:
            raise LookupError("no boundary files match" + (f" quantity {quantity!r}" if quantity else ""))
        out = []
        for e in entries:
            header, patches, frames = BoundaryReader().read(e.filepath)
            name = self.scene.unique_name(f"{header.short_name or header.quantity}_bndf")
            out.append(self._add(sc.BoundaryLayer(name, header, patches, frames, self._written_meshes(), opacity)))
        return out

    def add_particles(self, class_name: Optional[str] = None, quantity: Optional[str] = None,
                      diameter: float = 0.01) -> List[Any]:
        from pyfds.results.particle_reader import ParticleReader
        files = self._index().find_particles()
        if not files:
            raise LookupError("no particle files found")
        out = []
        for f in files:
            res = ParticleReader.read(f)
            classes = [res.get_class(class_name)] if class_name else res.classes
            for c in classes:
                if c is None or c.n_frames == 0:
                    continue
                out.append(self._add(sc.ParticleLayer(self.scene.unique_name(f"particles_{c.name}"), c, quantity, diameter)))
        if not out:
            raise LookupError("no particle class matched")
        return out

    def add_isosurface(self, path: str, level: Optional[float] = None, name: Optional[str] = None, opacity: float = 1.0):
        from pyfds.smokeview.binary import SmvBinaryExtractor
        iso = SmvBinaryExtractor().read_isosurface(path)
        if not iso.frames:
            raise ValueError(f"{path}: no isosurface frames")
        return self._add(sc.IsoLayer(self.scene.unique_name(name or os.path.splitext(os.path.basename(path))[0]), iso,
                                     level, opacity))

    def add_volume(self, values: np.ndarray, times: Sequence[float], mesh: Any, quantity: str = "", units: str = "",
                   kind: str = "scalar", name: Optional[str] = None, opacity: float = 1.0, **transfer_options):
        """Smoke (``kind="smoke"``, soot density kg/m3), fire (``"fire"``, HRRPUV kW/m3) or scalar volume from an
        array ``(frames, ni, nj, nk)`` on *mesh*."""
        m = self._mesh(mesh)
        if m is None:
            raise ValueError("a volume needs the mesh it lives on")
        return self._add(sc.VolumeLayer(self.scene.unique_name(name or kind), values, times, m, quantity, units, kind,
                                        opacity, **transfer_options))

    def add_volume_from_plot3d(self, quantity: str, kind: str = "scalar", path: Optional[str] = None, mesh: Any = None,
                               name: Optional[str] = None, opacity: float = 1.0, **transfer_options):
        """A volume layer from one quantity of a Plot3D file (default: the first one the index found)."""
        res = self._api.results.read_plot3d(path)
        if res is None:
            raise LookupError("no Plot3D file available")
        data = res.get_quantity(quantity)
        if data is None:
            raise KeyError(f"Plot3D file has no quantity {quantity!r}; has {res.quantities}")
        qi = res.quantity_index(quantity)
        return self.add_volume(data, res.times, mesh, quantity, res.units[qi], kind, name or f"{kind}_{quantity}",
                               opacity, **transfer_options)

    # -- layers / clips ---------------------------------------------------------------
    def layers(self) -> List[Dict[str, Any]]:
        return [l.describe() for l in self.scene.layers]

    def remove(self, name: str) -> None:
        self.scene.remove(name)

    def set_visible(self, name: str, visible: bool) -> None:
        self.scene.set_visible(name, visible)

    def set_opacity(self, name: str, opacity: float) -> None:
        self.scene.set_opacity(name, opacity)

    def add_clip(self, axis: str, position: float, keep: str = "above"):
        return self.scene.add_clip(axis, position, keep)

    def clear_clips(self) -> None:
        self.scene.clear_clips()

    def frame(self, t: float):
        return self.scene.frame(t)

    def probe(self, point: Sequence[float], t: Optional[float] = None, tol: Optional[float] = None) -> List[Dict[str, Any]]:
        return self.scene.probe(point, self.playback.time if t is None else t, tol)

    def summary(self) -> Dict[str, Any]:
        return self.scene.summary()

    # -- playback and camera -----------------------------------------------------------
    @property
    def playback(self) -> Playback:
        """Playback over the current timeline (rebuilt when layers change; position is kept by time)."""
        ts = self.scene.times
        if self._playback is None or not np.array_equal(self._playback.times, ts):
            old = self._playback
            self._playback = Playback(ts)
            if old is not None:
                self._playback.seek_time(old.time)
                self._playback.speed, self._playback.loop = old.speed, old.loop
        return self._playback

    def camera_at(self, t: Optional[float] = None) -> ViewportCamera:
        return self.camera_path.at(self.playback.time if t is None else t)

    def save_view(self, name: str, camera: Optional[ViewportCamera] = None, overwrite: bool = False) -> None:
        """Save a camera (default: the viewport's current one) under *name*."""
        self.views.save(name, camera or self._api.viewport.state.camera, overwrite)

    def apply_view(self, name: str) -> ViewportCamera:
        cam = self.views.get(name)
        self._api.viewport.set_camera(cam)
        return cam

    def render_frame(self, t: float, filepath: str, layer: Optional[str] = None, **display) -> str:
        """Quick 2-D image of one planar slice layer at time *t* (uses ``api.slice_view``)."""
        layers = [l for l in self.scene.layers if isinstance(l, sc.SliceLayer) and l.planar and
                  (layer is None or l.name == layer)]
        if not layers:
            raise LookupError("no planar slice layer to render")
        l = layers[0]
        return self._api.slice_view.render(l.result, filepath, l.index_at(t), l.mesh, **display)
