"""The results visualization: everything a user sets while looking at a run, saved as a ``.pyfdsv`` file.

A visualization stores *what* is loaded and *how it is displayed* - active results, colorbars, smoke / fire
and Data3D properties, views, tours, section boxes, annotations, floors, skybox, time and unit settings,
loaded CSV files - never the result data itself. The file is plain JSON (``format: pyfds-visualization``)
so it can be read, diffed and edited by hand. Paths to results are stored relative to the visualization
file when possible, so a whole folder can be moved or copied.
"""
from __future__ import annotations

import dataclasses
import json
import os
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .model_scene import (  # noqa: F401  (re-exported)
    CsvFileRef,
    Data3DIso,
    Data3DPoint,
    Data3DSlice,
    Dimension,
    FloorSettings,
    Keyframe,
    Label,
    PLANES,
    SectionBox,
    Skybox,
    Timelines,
    Tour,
    Units,
    View,
    Viewpoint,
)
from .model_prefs import (  # noqa: F401  (re-exported)
    COLOR_SOURCES,
    ColorbarProps,
    Data3DProps,
    FdsPreferences,
    GEOMETRY_SETS,
    GeneralPreferences,
    OPACITY_SOURCES,
    ParticleProps,
    RANGE_MODES,
    RENDER_MODES,
    RenderingPreferences,
    SMOKE_PRESETS,
    SliceVectorProps,
    Smoke3DProps,
    apply_smoke_preset,
    default_colorbar,
)



FORMAT = "pyfds-visualization"


VERSION = 1


EXTENSION = ".pyfdsv"


# -- generic (de)serialisation ---------------------------------------------------------------------------
def to_plain(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_plain(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [to_plain(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): to_plain(v) for k, v in obj.items()}
    return obj


def from_plain(tp: Any, data: Any) -> Any:
    """Build ``tp`` from plain JSON data: missing keys take defaults, unknown keys are ignored."""
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if data is None:
        return None
    if origin is typing.Union:
        inner = [a for a in args if a is not type(None)]
        return from_plain(inner[0], data) if len(inner) == 1 else data
    if origin in (list, List):
        return [from_plain(args[0], x) for x in data]
    if origin in (tuple, Tuple):
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(from_plain(args[0], x) for x in data)
        return tuple(from_plain(a, x) for a, x in zip(args, data))
    if origin in (dict, Dict):
        return {k: from_plain(args[1], v) for k, v in data.items()}
    if dataclasses.is_dataclass(tp):
        hints = typing.get_type_hints(tp)
        kwargs = {}
        for f in dataclasses.fields(tp):
            if f.name in data:
                kwargs[f.name] = from_plain(hints[f.name], data[f.name])
        return tp(**kwargs)
    if tp is float and isinstance(data, int):
        return float(data)
    return data


@dataclass
class ResultsVisualization:
    format: str = FORMAT
    version: int = VERSION
    results: Optional[str] = None                 # path of the .smv, relative to this file when possible
    active: List[str] = field(default_factory=list)
    geometry_set: str = "fds_actual"
    rendering_mode: str = "solid_outlines"
    camera: Viewpoint = field(default_factory=Viewpoint)
    views: List[View] = field(default_factory=list)
    active_view: Optional[str] = None             # None = the Default view
    fds: FdsPreferences = field(default_factory=FdsPreferences)
    smoke3d: Smoke3DProps = field(default_factory=Smoke3DProps)
    data3d: Dict[str, Data3DProps] = field(default_factory=dict)
    slice_vectors: Dict[str, SliceVectorProps] = field(default_factory=dict)
    particles: Dict[str, ParticleProps] = field(default_factory=dict)
    data3d_points: List[Data3DPoint] = field(default_factory=list)
    data3d_slices: List[Data3DSlice] = field(default_factory=list)
    data3d_isos: List[Data3DIso] = field(default_factory=list)
    dimensions: List[Dimension] = field(default_factory=list)
    labels: List[Label] = field(default_factory=list)
    show_dimensions: bool = True
    show_labels: bool = True
    floors: FloorSettings = field(default_factory=FloorSettings)
    skybox: Skybox = field(default_factory=Skybox)
    timelines: Timelines = field(default_factory=Timelines)
    units: Units = field(default_factory=Units)
    time_display: str = "time"                    # none | time | date_time
    motion_blur: bool = False
    csv_files: List[CsvFileRef] = field(default_factory=list)
    general: GeneralPreferences = field(default_factory=GeneralPreferences)
    rendering: RenderingPreferences = field(default_factory=RenderingPreferences)
    playback_speed: float = 1.0
    playback_loop: bool = False

    # -- views --------------------------------------------------------------------------------------
    def view(self, name: str) -> View:
        for v in self.views:
            if v.name == name:
                return v
        raise KeyError(f"no view called {name!r}; have {[v.name for v in self.views]}")

    def problems(self) -> List[str]:
        out: List[str] = []
        if self.geometry_set not in GEOMETRY_SETS:
            out.append(f"geometry_set must be one of {', '.join(GEOMETRY_SETS)}")
        if self.rendering_mode not in RENDER_MODES:
            out.append(f"rendering_mode must be one of {', '.join(RENDER_MODES)}")
        for q, cb in self.fds.colorbars.items():
            out += [f"colorbar {q}: {m}" for m in cb.problems()]
        out += [f"smoke3d: {m}" for m in self.smoke3d.problems()]
        out += self.units.problems()
        out += [f"rendering: {m}" for m in self.rendering.problems()]
        names = [v.name for v in self.views]
        if len(set(names)) != len(names):
            out.append("view names must be unique")
        if self.active_view is not None and self.active_view not in names:
            out.append(f"active view {self.active_view!r} does not exist")
        if not self.playback_speed > 0:
            out.append("playback_speed must be positive")
        return out


# -- file ------------------------------------------------------------------------------------------------
class VisualizationFileError(ValueError):
    pass


def _relative(target: str, base_dir: Path) -> str:
    try:
        return os.path.relpath(os.path.abspath(target), base_dir).replace("\\", "/")
    except ValueError:                           # different drive: only an absolute path can refer to it
        return os.path.abspath(target).replace("\\", "/")


def save(viz: ResultsVisualization, path: str) -> str:
    """Write *viz* to *path* (``.pyfdsv`` added when missing); the results path is stored relative to it."""
    p = Path(path if path.lower().endswith(EXTENSION) else path + EXTENSION)
    data = to_plain(viz)
    if viz.results:
        data["results"] = _relative(viz.results, p.resolve().parent)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return str(p)


def load(path: str) -> ResultsVisualization:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"visualization not found: {path}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VisualizationFileError(f"{p.name} is not valid JSON: {exc}") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise VisualizationFileError(f"{p.name} is not a {FORMAT} file")
    if data.get("version", 0) > VERSION:
        raise VisualizationFileError(f"{p.name} was saved by a newer version (file version {data['version']})")
    viz = from_plain(ResultsVisualization, data)
    if viz.results and not os.path.isabs(viz.results):
        viz.results = str((p.resolve().parent / viz.results).resolve())
    return viz
