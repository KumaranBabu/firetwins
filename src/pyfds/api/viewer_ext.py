"""Views, tours, section boxes, annotations, floors, skybox, preferences, CSV data, screenshots and movies
for ``api.viewer`` (a mixin of :class:`~pyfds.api.viewer.ViewerManager`)."""
from __future__ import annotations

import copy
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from pyfds.results.viz import annotations as an
from pyfds.results.viz import capture as cap
from pyfds.results.viz import csvload as cl
from pyfds.results.viz import floors as fl
from pyfds.results.viz import model as vm
from pyfds.results.viz import views as vw
from pyfds.results.viz.tree import NavNode

#: ``renderer(path, size, time, view_name) -> None``: draws the current scene to an image file
Renderer = Callable[[str, Tuple[int, int], float, str], None]


class ViewerExtras:
    def _init_extras(self) -> None:
        self.viz_listeners: List[Callable[[], None]] = []
        #: set by whoever can draw (the results window, the command line); scripts and the agent call it through screenshot()
        self.renderer: Optional[Renderer] = None
        self.motion_blur_span = 0.0                # simulated seconds one movie frame's shutter stays open

    # -- camera and standard views ---------------------------------------------------------------------------
    @property
    def camera(self) -> vm.Viewpoint:
        return self.viz.camera

    def set_camera(self, vp: vm.Viewpoint) -> None:
        self.viz.camera = copy.deepcopy(vp)
        self.dirty = True

    def set_projection(self, projection: str) -> None:
        """Perspective ⇄ Orthogonal (the viewpoint is kept)."""
        if projection not in ("perspective", "orthogonal"):
            raise ValueError("projection must be perspective or orthogonal")
        self.viz.camera.projection = projection
        self.dirty = True

    def set_navigation(self, tool: str) -> None:
        if tool not in ("orbit", "pan", "zoom", "roam", "smokeview"):
            raise ValueError("navigation tool must be orbit, pan, zoom, roam or smokeview")
        if tool == "roam" and self.viz.camera.projection == "orthogonal":
            raise ValueError("the roam tool cannot be used with the orthogonal view")
        self.viz.camera.navigation = tool
        self.dirty = True

    def standard_view(self, name: str) -> vm.Viewpoint:
        """Top, Front or Side (left) of the model (``Reset Camera`` = isometric), looking at its centre."""
        b = self.run.bounds() if self.run else (0, 1, 0, 1, 0, 1)
        c = np.array([(b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2])
        d = float(np.linalg.norm([b[1] - b[0], b[3] - b[2], b[5] - b[4]])) * 1.3 + 1e-6
        views = {"top": ((0, 0, d), (0, 1, 0)), "front": ((0, -d, 0), (0, 0, 1)), "side": ((-d, 0, 0), (0, 0, 1)),
                 "isometric": ((d * 0.7, -d * 0.7, d * 0.5), (0, 0, 1))}
        if name not in views:
            raise ValueError(f"view must be one of {', '.join(views)}")
        off, up = views[name]
        vp = copy.deepcopy(self.viz.camera)
        vp.position, vp.target, vp.up = tuple(c + o for c, o in zip(c, off)), tuple(c), up      # type: ignore
        self.viz.camera = vp
        self.dirty = True
        return vp

    def reset_camera(self) -> vm.Viewpoint:
        return self.standard_view("isometric")

    # -- geometry set and rendering mode --------------------------------------------------------------------------
    def set_geometry_set(self, name: str) -> None:
        if name not in vm.GEOMETRY_SETS:
            raise ValueError(f"geometry set must be one of {', '.join(vm.GEOMETRY_SETS)}")
        node = self.tree.find(f"geometry/{name}")
        if node is None:
            raise KeyError(f"this run has no {name} geometry")
        self.activation.activate(node.id)
        self.viz.geometry_set = name
        self.dirty = True

    def set_rendering_mode(self, mode: str) -> None:
        if mode not in vm.RENDER_MODES:
            raise ValueError(f"rendering mode must be one of {', '.join(vm.RENDER_MODES)}")
        self.viz.rendering_mode = mode
        self.dirty = True

    # -- views, tours, section boxes -------------------------------------------------------------------------------
    def new_view(self, name: Optional[str] = None) -> vm.View:
        v = vw.new_view(self.viz, name, self.viz.camera, vw.active_section(self.viz))
        self._views_changed()
        return v

    def new_tour(self, name: Optional[str] = None) -> vm.View:
        v = vw.new_tour(self.viz, name, vw.active_section(self.viz))
        self._views_changed()
        return v

    def activate_view(self, name: Optional[str]) -> Optional[vm.View]:
        v = vw.activate(self.viz, name)
        self._views_changed(rebuild=False)
        return v

    def save_viewpoint(self, name: Optional[str] = None) -> None:
        vw.save_viewpoint(self.viz, name or self.viz.active_view or "")
        self.dirty = True

    def delete_view(self, name: str) -> None:
        vw.delete_view(self.viz, name)
        self._views_changed()

    def duplicate_views(self, names: Sequence[str]) -> List[vm.View]:
        out = vw.duplicate_views(self.viz, names)
        self._views_changed()
        return out

    def _tour(self, view: Optional[str]) -> vm.Tour:
        v = self.viz.view(view or self.viz.active_view or "")
        if v.tour is None:
            raise ValueError(f"view {v.name!r} has no tour")
        if v.origin != "pyfds":
            raise ValueError("views from FDS or Smokeview cannot be edited; duplicate the view first")
        return v.tour

    def add_keyframe(self, time: Optional[float] = None, view: Optional[str] = None, transition: str = "move_to_next") -> vm.Keyframe:
        """Tour Editor ▸ Add: record the current camera at *time* (default the playback time)."""
        k = vw.add_keyframe(self._tour(view), self.time if time is None else time, self.viz.camera, transition)
        self.dirty = True
        return k

    def set_keyframe(self, index: int, view: Optional[str] = None, time: Optional[float] = None,
                     transition: Optional[str] = None, record_camera: bool = False) -> None:
        t = self._tour(view)
        k = t.keyframes[index]
        if transition is not None:
            if transition not in ("move_to_next", "stationary"):
                raise ValueError("transition must be move_to_next or stationary")
            k.transition = transition
        if record_camera:
            vw.record_camera(t, index, self.viz.camera)
        if time is not None:
            vw.shift_keyframes(t, [index], new_time=time)
        self.dirty = True

    def remove_keyframes(self, indices: Sequence[int], view: Optional[str] = None) -> None:
        vw.remove_keyframes(self._tour(view), indices)
        self.dirty = True

    def shift_keyframes(self, indices: Sequence[int], new_time: Optional[float] = None, offset: Optional[float] = None,
                        view: Optional[str] = None) -> None:
        vw.shift_keyframes(self._tour(view), indices, new_time, offset)
        self.dirty = True

    def duplicate_keyframes(self, indices: Sequence[int], mode: str = "end_of_tour", at_time: Optional[float] = None,
                            last_delay: float = 0.0, view: Optional[str] = None) -> List[vm.Keyframe]:
        out = vw.duplicate_keyframes(self._tour(view), indices, mode, at_time, last_delay)
        self.dirty = True
        return out

    def set_tour(self, view: Optional[str] = None, repeat: Optional[bool] = None, repeat_delay: Optional[float] = None) -> vm.Tour:
        t = self._tour(view)
        if repeat is not None:
            t.repeat = bool(repeat)
        if repeat_delay is not None:
            if repeat_delay < 0:
                raise ValueError("repeat delay must not be negative")
            t.repeat_delay = float(repeat_delay)
        self.dirty = True
        return t

    def add_section_box(self, selection_bounds: Optional[Sequence[float]] = None) -> vm.SectionBox:
        """View ▸ Add section box: around everything visible, or around the selected objects."""
        if self.viz.active_view is None:
            self.new_view()
        bounds = selection_bounds or (self.run.bounds() if self.run else (0, 1, 0, 1, 0, 1))
        box = vw.new_section_box(bounds, enabled_planes=())
        vw.set_section_box(self.viz, None, box)
        self.dirty = True
        return box

    def set_section_plane(self, plane: str, value: float, enabled: bool = True) -> vm.SectionBox:
        box = vw.active_section(self.viz)
        if box is None:
            raise ValueError("the active view has no section box; add one first")
        trial = copy.deepcopy(box)
        vw.set_plane(trial, plane, value, enabled)
        vw.set_section_box(self.viz, None, trial)
        self.dirty = True
        return trial

    def set_section_planes(self, planes: Dict[str, Tuple[bool, float]]) -> vm.SectionBox:
        """Set several planes at once (the Section Box dialog); nothing changes when the result is not a valid box."""
        box = vw.active_section(self.viz)
        if box is None:
            raise ValueError("the active view has no section box; add one first")
        trial = copy.deepcopy(box)
        for name, (on, value) in planes.items():
            trial.planes[name] = (bool(on), float(value))
        for axis in "xyz":
            a, b = trial.planes.get(axis + "_min"), trial.planes.get(axis + "_max")
            if a and b and a[0] and b[0] and a[1] >= b[1]:
                raise ValueError(f"{axis}_min must be smaller than {axis}_max")
        vw.set_section_box(self.viz, None, trial)
        self.dirty = True
        return trial

    def remove_section_box(self) -> None:
        vw.set_section_box(self.viz, None, None)
        self.dirty = True

    def enable_section_boxes(self, enabled: bool) -> None:
        box = vw.active_section(self.viz)
        if box is not None:
            box.enabled = bool(enabled)
            self.dirty = True

    def import_views(self, path: str) -> List[vm.View]:
        """File ▸ Import ▸ Import Views (from a views file or another visualization)."""
        out = vw.import_views(self.viz, Path(path).read_text(encoding="utf-8"))
        self._views_changed()
        return out

    def export_views(self, path: str) -> str:
        Path(path).write_text(vw.export_views(self.viz), encoding="utf-8")
        return path

    def camera_for_time(self, t: Optional[float] = None) -> vm.Viewpoint:
        tour = vw.active_tour(self.viz)
        return vw.camera_at(tour, self.time if t is None else t) if tour and tour.keyframes else copy.deepcopy(self.viz.camera)

    def _views_changed(self, rebuild: bool = True) -> None:
        self.dirty = True
        if rebuild:
            self._rebuild()
        self._playback = None

    # -- annotations -----------------------------------------------------------------------------------------------
    def add_dimension(self, p1: Sequence[float], p2: Sequence[float], mode: str = "feature", offset: float = 0.0) -> vm.Dimension:
        d = an.add_dimension(self.viz, p1, p2, mode, offset)
        self._rebuild()
        self.dirty = True
        return d

    def add_label(self, text: str, anchor: Sequence[float], position: Optional[Sequence[float]] = None) -> vm.Label:
        lab = an.add_label(self.viz, text, anchor, position)
        self._rebuild()
        self.dirty = True
        return lab

    def remove_annotation(self, kind: str, index: int) -> None:
        an.remove_annotation(self.viz, kind, index)
        self._rebuild()
        self.dirty = True

    def rename_label(self, index: int, text: str) -> None:
        an.rename_label(self.viz, index, text)
        self._rebuild()
        self.dirty = True

    def dimension_geometry(self, index: int) -> an.DimensionGeometry:
        return an.dimension_geometry(self.viz.dimensions[index], self.viz.general.dimension_precision)

    def show_annotations(self, dimensions: Optional[bool] = None, labels: Optional[bool] = None) -> None:
        if dimensions is not None:
            self.viz.show_dimensions = bool(dimensions)
        if labels is not None:
            self.viz.show_labels = bool(labels)
        self.dirty = True

    # -- floors --------------------------------------------------------------------------------------------------------
    def set_floors(self, levels: Sequence[float]) -> vm.FloorSettings:
        fl.set_floors(self.viz.floors, levels)
        self.dirty = True
        return self.viz.floors

    def set_floor_layout(self, layout: Optional[str] = None, separation: Optional[float] = None,
                         clip_walls: Optional[bool] = None, wall_height: Optional[float] = None) -> vm.FloorSettings:
        trial = copy.deepcopy(self.viz.floors)
        if layout is not None:
            trial.layout = layout
        if separation is not None:
            trial.separation = float(separation)
        if clip_walls is not None:
            trial.clip_walls = bool(clip_walls)
        if wall_height is not None:
            trial.wall_height = float(wall_height)
        bad = fl.validate(trial)
        if bad:
            raise ValueError("; ".join(bad))
        self.viz.floors = trial
        self.dirty = True
        return trial

    def show_floors(self, floors: Optional[Sequence[int]]) -> None:
        fl.set_visible(self.viz.floors, floors)
        self.dirty = True

    def show_floors_for_selection(self, z_min: float, z_max: float) -> List[int]:
        idx = fl.floors_for_selection(self.viz.floors, z_min, z_max)
        fl.set_visible(self.viz.floors, idx)
        self.dirty = True
        return idx

    # -- skybox, display, units, preferences -------------------------------------------------------------------------------
    def set_skybox(self, kind: str, files: Sequence[str] = (), z_rotation: float = 0.0, show: bool = True,
                   compress_textures: bool = False) -> vm.Skybox:
        need = {"none": 0, "predefined": 0, "image360": 1, "cubemap": 1, "split_cubemap": 6}
        if kind not in need:
            raise ValueError(f"skybox must be one of {', '.join(need)}")
        if len(files) != need[kind]:
            raise ValueError(f"a {kind} skybox needs {need[kind]} image file(s), got {len(files)}")
        missing = [f for f in files if not Path(f).exists()]
        if missing:
            raise FileNotFoundError(f"skybox image not found: {missing[0]}")
        self.viz.skybox = vm.Skybox(kind, [str(Path(f).resolve()) for f in files], float(z_rotation), bool(show), bool(compress_textures))
        self.dirty = True
        return self.viz.skybox

    def set_units(self, temperature: Optional[str] = None, concentration: Optional[str] = None,
                  mass_fraction: Optional[str] = None) -> vm.Units:
        trial = copy.deepcopy(self.viz.units)
        for k, v in (("temperature", temperature), ("concentration", concentration), ("mass_fraction", mass_fraction)):
            if v is not None:
                setattr(trial, k, v)
        bad = trial.problems()
        if bad:
            raise ValueError("; ".join(bad))
        self.viz.units = trial
        self.dirty = True
        return trial

    def set_time_display(self, mode: str) -> None:
        if mode not in ("none", "time", "date_time"):
            raise ValueError("time display must be none, time or date_time")
        self.viz.time_display = mode
        self.dirty = True

    def set_timelines(self, **fields: Any) -> vm.Timelines:
        from pyfds.results.viz import timelines as tml
        trial = copy.deepcopy(self.viz.timelines)
        for k, v in fields.items():
            if k not in vm.Timelines.__dataclass_fields__:
                raise AttributeError(f"unknown timeline setting {k!r}")
            setattr(trial, k, v)
        bad = tml.check(trial)
        if bad:
            raise ValueError("; ".join(bad))
        if trial.view_timeline == "custom" and trial.end <= trial.begin:
            raise ValueError("a custom timeline needs End Time after Begin Time")
        self.viz.timelines = trial
        self._playback = None
        self.dirty = True
        return trial

    def set_motion_blur(self, on: bool) -> None:
        self.viz.motion_blur = bool(on)
        self.dirty = True

    def set_general(self, **fields: Any) -> vm.GeneralPreferences:
        for k in fields:
            if k not in vm.GeneralPreferences.__dataclass_fields__:
                raise AttributeError(f"unknown preference {k!r}")
        for k, v in fields.items():
            setattr(self.viz.general, k, v)
        self.dirty = True
        return self.viz.general

    def set_rendering(self, preset: Optional[str] = None, **fields: Any) -> vm.RenderingPreferences:
        trial = copy.deepcopy(self.viz.rendering)
        if preset == "max_quality":
            trial.max_quality()
        elif preset == "max_compatibility":
            trial.max_compatibility()
        elif preset is not None:
            raise ValueError("preset must be max_quality or max_compatibility")
        for k, v in fields.items():
            if k not in vm.RenderingPreferences.__dataclass_fields__:
                raise AttributeError(f"unknown rendering option {k!r}")
            setattr(trial, k, v)
        bad = trial.problems()
        if bad:
            raise ValueError("; ".join(bad))
        self.viz.rendering = trial
        self.dirty = True
        return trial

    # -- CSV time series ----------------------------------------------------------------------------------------------
    def load_csv(self, path: str, **fields: Any) -> cl.CsvData:
        """File ▸ Load CSV File: a known FDS file is recognised by its name; otherwise give the header layout."""
        ref = cl.guess_type(path)
        for k, v in fields.items():
            if k not in vm.CsvFileRef.__dataclass_fields__ or k == "path":
                raise AttributeError(f"unknown CSV setting {k!r}")
            setattr(ref, k, v)
        data = cl.load(ref)                                     # raises with a plain message when unusable
        ref.path = str(Path(path).resolve())
        self.viz.csv_files = [c for c in self.viz.csv_files if c.path != ref.path] + [ref]
        self.csv_cache[ref.path] = data
        self._rebuild()
        self.dirty = True
        return data

    def remove_csv(self, path: str) -> None:
        p = str(Path(path).resolve())
        n = len(self.viz.csv_files)
        self.viz.csv_files = [c for c in self.viz.csv_files if c.path != p]
        if len(self.viz.csv_files) == n:
            raise KeyError(f"{path} is not loaded")
        self.csv_cache.pop(p, None)
        self._rebuild()
        self.dirty = True

    def csv_series(self) -> Dict[str, cl.TimeSeries]:
        """``{id: series}`` of every loaded CSV column and every Data3D point."""
        out: Dict[str, cl.TimeSeries] = {}
        for ref in self.viz.csv_files:
            data = self.csv_cache.get(ref.path)
            if data is None:
                try:
                    data = self.csv_cache[ref.path] = cl.load(ref)
                except (OSError, ValueError):
                    continue
            for s in data.series:
                out[f"{Path(ref.path).name}/{s.label}"] = s
        for p in self.viz.data3d_points:
            t, v = self.point_series(p.id)
            out[f"Data3D/{p.id}"] = cl.TimeSeries(p.id, p.quantity, "", t, v)
        return out

    def time_history(self, ids: Sequence[str]) -> List[cl.TimeSeries]:
        allv = self.csv_series()
        missing = [i for i in ids if i not in allv]
        if missing:
            raise KeyError(f"no time series {missing[0]!r}; have {sorted(allv)[:6]}")
        return [allv[i] for i in ids]

    def export_data(self, ids: Sequence[str], path: str, tab_separated: bool = False) -> int:
        return cl.export(self.time_history(ids), path, "\t" if tab_separated else ",")

    # -- screenshots and movies ------------------------------------------------------------------------------------------
    def _tour_ranges(self) -> Dict[str, Tuple[float, float]]:
        return {v.name: v.tour.time_range for v in self.viz.views if v.tour is not None and v.tour.time_range}

    def screenshot_plan(self, path: str, mode: str = "single", time: Optional[float] = None, view: str = cap.CURRENT,
                        start: Optional[float] = None, end: Optional[float] = None, interval: float = 1.0,
                        views: Sequence[str] = (cap.CURRENT,), tsv: Optional[str] = None) -> List[cap.Shot]:
        lo, hi = self.time_range()
        if mode == "single":
            return cap.single(path, self.time if time is None else time, view)
        if mode == "multiple":
            return cap.multiple(path, lo if start is None else start, hi if end is None else end, interval, views,
                                self._tour_ranges())
        if mode == "file":
            if not tsv:
                raise ValueError("file mode needs a .tsv file")
            return cap.from_file(path, Path(tsv).read_text(encoding="utf-8"), self._tour_ranges())
        raise ValueError("mode must be single, multiple or file")

    def screenshot(self, path: str, time: Optional[float] = None, view: str = cap.CURRENT,
                   size: Tuple[int, int] = (1280, 720)) -> str:
        """One image of the current scene (needs a renderer: open the results window or use the command line)."""
        if self.renderer is None:
            raise RuntimeError("no renderer is attached: open the results window (or run pyfds.gui.results.cli) first")
        return self.render_screenshots(self.screenshot_plan(path, "single", time, view), self.renderer, size)[0]

    def render_screenshots(self, shots: Sequence[cap.Shot], renderer: Renderer, size: Tuple[int, int] = (1920, 1080)) -> List[str]:
        """Draw each planned image with *renderer* (the 3D window's off-screen drawing)."""
        if size[0] < 16 or size[1] < 16:
            raise ValueError("the screenshot size is too small")
        views = {v.name for v in self.viz.views} | {cap.CURRENT, "Default"}
        out = []
        for s in shots:
            if s.view not in views:
                raise KeyError(f"no view called {s.view!r}")
            Path(s.path).parent.mkdir(parents=True, exist_ok=True)
            renderer(s.path, size, s.time, s.view)
            out.append(s.path)
        return out

    def render_movie(self, plan: cap.MoviePlan, renderer: Renderer, view: str = cap.CURRENT,
                     keep_frames: bool = False) -> Dict[str, Any]:
        """Render every frame and join them into the movie (MP4 through the bundled ffmpeg when available).

        Returns ``{"path", "frames", "encoded", "frames_dir"}``; ``encoded`` is False (and the PNG frames are kept
        beside the movie) when no encoder is available."""
        out = Path(plan.path)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=out.stem + "_frames_", dir=str(out.parent)))
        self.motion_blur_span = 0.5 * plan.speed / plan.fps if self.viz.motion_blur else 0.0     # half-frame shutter
        try:
            for i, t in enumerate(plan.times):
                renderer(cap.frame_path(str(tmp), out.stem, i), plan.size, t, view)
            rc = self.encode_frames(str(tmp), out.stem, str(out), plan.fps)
            encoded = rc == 0
            keep = keep_frames or not encoded
            if keep:
                keep_dir = out.parent / f"{out.stem}_frames"
                shutil.rmtree(keep_dir, ignore_errors=True)
                shutil.move(str(tmp), str(keep_dir))
                return {"path": str(out), "frames": len(plan.times), "encoded": encoded, "frames_dir": str(keep_dir)}
            return {"path": str(out), "frames": len(plan.times), "encoded": True, "frames_dir": None}
        finally:
            self.motion_blur_span = 0.0
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def encoder_path() -> Optional[str]:
        """An ffmpeg to join frames: the bundled one (``imageio-ffmpeg``) or one on the PATH."""
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return shutil.which("ffmpeg")

    def encode_frames(self, frames_dir: str, stem: str, output: str, fps: int = 30, bitrate_kbps: int = 6000) -> int:
        """Join ``stem_00000.png ...`` into an MP4. Returns 0 on success, 127 when no encoder is available."""
        ff = self.encoder_path()
        if ff is None:
            return 127
        cmd = [ff, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(Path(frames_dir) / f"{stem}_%05d.png"),
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", f"{bitrate_kbps}k", str(output)]
        return subprocess.run(cmd, capture_output=True, text=True).returncode
