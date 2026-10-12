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


# -- colorbars and per-kind properties -----------------------------------------------------------------
RANGE_MODES = ("percentile_rounded", "percentile", "global_rounded", "global", "custom")
OPACITY_SOURCES = ("constant", "gradient", "feather_below", "feather_above")
COLOR_SOURCES = ("colormap", "constant")


@dataclass
class ColorbarProps:
    """One colorbar per FDS quantity (the 'Quantity Colors' of FDS Preferences)."""
    range_mode: str = "percentile_rounded"
    minimum: Optional[float] = None               # used when range_mode == "custom"
    maximum: Optional[float] = None
    truncate: bool = False
    hide_below: Optional[float] = None
    hide_above: Optional[float] = None
    color_source: str = "colormap"
    colormap: str = "turbo"
    invert: bool = False
    color: str = "#000000"                        # for color_source == "constant"
    opacity_source: str = "constant"
    opacity: float = 1.0
    opacity_at_min: float = 0.0
    opacity_at_max: float = 0.75
    feather_threshold: float = 0.25
    n_colors: int = 256
    highlight_enabled: bool = False
    highlight_value: float = 0.0
    highlight_width: float = 0.0
    highlight_color: str = "#ffffff"

    def problems(self) -> List[str]:
        out = []
        if self.range_mode not in RANGE_MODES:
            out.append(f"range_mode must be one of {', '.join(RANGE_MODES)}")
        if self.range_mode == "custom" and (self.minimum is None or self.maximum is None or not self.minimum < self.maximum):
            out.append("a custom range needs minimum < maximum")
        if self.truncate and self.hide_below is not None and self.hide_above is not None and self.hide_below >= self.hide_above:
            out.append("hide_below must be smaller than hide_above")
        if self.color_source not in COLOR_SOURCES:
            out.append(f"color_source must be one of {', '.join(COLOR_SOURCES)}")
        if self.opacity_source not in OPACITY_SOURCES:
            out.append(f"opacity_source must be one of {', '.join(OPACITY_SOURCES)}")
        for name in ("opacity", "opacity_at_min", "opacity_at_max", "feather_threshold"):
            if not -10.0 <= getattr(self, name) <= 10.0:
                out.append(f"{name} is out of range")
        if not 0.0 <= self.feather_threshold <= 1.0:
            out.append("feather_threshold must be between 0 and 1")
        if not isinstance(self.n_colors, int) or not 2 <= self.n_colors <= 1024:
            out.append("n_colors must be a whole number from 2 to 1024")
        if self.highlight_enabled and self.highlight_width <= 0:
            out.append("highlight_width must be positive")
        return out


@dataclass
class FdsPreferences:
    time_offset: float = 0.0
    interpolate: bool = True
    obscure_types: List[str] = field(default_factory=lambda: ["slices2d"])
    colorbars: Dict[str, ColorbarProps] = field(default_factory=dict)

    def colorbar(self, quantity: str) -> ColorbarProps:
        return self.colorbars.setdefault(quantity, default_colorbar(quantity))


def default_colorbar(quantity: str) -> ColorbarProps:
    q = quantity.upper()
    cmap = "turbo_r" if "VISIBILITY" in q else "turbo"
    p = ColorbarProps(colormap=cmap)
    if "SOOT" in q or "SMOKE" in q or q == "HRRPUV":
        p.opacity_source = "gradient"
    return p


SMOKE_PRESETS = ("default", "smokeview_default_pre_6_4_4", "smoke_default", "custom")


@dataclass
class Smoke3DProps:
    preset: str = "default"
    fire_rendering: str = "radiant"               # radiant | volumetric
    sampling_factor: float = 1.0
    fire_brightness: float = 1.0
    smoke_brightness: float = 1.0
    smoke_opacity: float = 1.0                    # 1.0 = as simulated; anything else must be annotated
    smoke_determines_fire_transparency: bool = True
    transparency_distance: float = 0.5            # 50 % transparency distance, metres (volumetric fire)
    hrrpuv_cutoff: Optional[float] = None         # None = the run's own cutoff
    smoke_color: str = "#000000"
    mass_extinction: float = 8700.0

    def problems(self) -> List[str]:
        out = []
        if self.preset not in SMOKE_PRESETS:
            out.append(f"preset must be one of {', '.join(SMOKE_PRESETS)}")
        if self.fire_rendering not in ("radiant", "volumetric"):
            out.append("fire_rendering must be radiant or volumetric")
        for name in ("sampling_factor", "transparency_distance", "mass_extinction"):
            if not getattr(self, name) > 0:
                out.append(f"{name} must be positive")
        for name in ("fire_brightness", "smoke_brightness"):
            if getattr(self, name) < 0:
                out.append(f"{name} must not be negative")
        if not 0.0 <= self.smoke_opacity <= 1.0:
            out.append("smoke_opacity must be between 0 and 1")
        return out


def apply_smoke_preset(p: Smoke3DProps, preset: str) -> Smoke3DProps:
    """The three pre-defined looks of the Smoke3D Properties dialog."""
    if preset not in SMOKE_PRESETS:
        raise ValueError(f"unknown preset {preset!r}")
    p.preset = preset
    if preset == "default":
        p.fire_rendering, p.smoke_determines_fire_transparency = "radiant", True
    elif preset == "smokeview_default_pre_6_4_4":
        p.fire_rendering, p.smoke_determines_fire_transparency = "volumetric", False
    elif preset == "smoke_default":
        p.fire_rendering, p.smoke_determines_fire_transparency = "volumetric", False
    return p


@dataclass
class Data3DProps:
    sample_factor: float = 1.0


@dataclass
class SliceVectorProps:
    factor: float = 1.0
    step: int = 2


@dataclass
class ParticleProps:
    trail_time: float = 0.0
    color: str = "default"                        # "default" or the name of a particle quantity
    size: float = 3.0


# -- views, tours, sections --------------------------------------------------------------------------------
@dataclass
class Viewpoint:
    position: Tuple[float, float, float] = (10.0, -10.0, 8.0)
    target: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    up: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    fov_deg: float = 45.0
    zoom: float = 1.0
    projection: str = "perspective"               # perspective | orthogonal
    navigation: str = "orbit"


@dataclass
class Keyframe:
    time: float
    viewpoint: Viewpoint = field(default_factory=Viewpoint)
    transition: str = "move_to_next"              # move_to_next | stationary


@dataclass
class Tour:
    timeline: str = "fds"
    repeat: bool = False
    repeat_delay: float = 0.0
    keyframes: List[Keyframe] = field(default_factory=list)

    @property
    def time_range(self) -> Optional[Tuple[float, float]]:
        if not self.keyframes:
            return None
        return self.keyframes[0].time, self.keyframes[-1].time


PLANES = ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")


@dataclass
class SectionBox:
    """Up to six planes; a plane clips only when enabled. Everything outside the box is hidden."""
    planes: Dict[str, Tuple[bool, float]] = field(default_factory=dict)
    enabled: bool = True

    def active(self) -> Dict[str, float]:
        return {k: v[1] for k, v in self.planes.items() if v[0]} if self.enabled else {}


@dataclass
class View:
    name: str
    origin: str = "pyfds"                         # "fds" for views read from FDS / Smokeview files (read-only)
    viewpoint: Optional[Viewpoint] = None
    tour: Optional[Tour] = None
    section_box: Optional[SectionBox] = None


# -- annotations, floors, skybox, time, units -----------------------------------------------------------------
@dataclass
class Dimension:
    p1: Tuple[float, float, float]
    p2: Tuple[float, float, float]
    mode: str = "feature"                         # feature | along_x | along_y | along_z
    offset: float = 0.0


@dataclass
class Label:
    text: str
    anchor: Tuple[float, float, float]
    position: Optional[Tuple[float, float, float]] = None   # None = label sits on the anchor (no leader line)


@dataclass
class FloorSettings:
    floors: List[float] = field(default_factory=list)      # Z of each floor, ascending
    layout: str = "vertical"                      # vertical | horizontal
    separation: float = 0.0
    clip_walls: bool = False
    wall_height: float = 2.0
    visible: Optional[List[int]] = None           # indices of visible floors; None = all


@dataclass
class Skybox:
    kind: str = "none"                            # none | predefined | image360 | cubemap | split_cubemap
    files: List[str] = field(default_factory=list)
    z_rotation: float = 0.0
    show: bool = True
    compress_textures: bool = False


@dataclass
class Timelines:
    reference_time: str = "2000-01-01T00:00:00"
    display_format: str = "regional"              # regional | iso8601
    fds_offset: float = 0.0
    view_timeline: str = "automatic"              # automatic | custom
    begin: float = 0.0
    end: float = 0.0


@dataclass
class Units:
    temperature: str = "C"                        # C | F
    concentration: str = "mol/mol"                # mol/mol | ppm
    mass_fraction: str = "kg/kg"                  # kg/kg | ppm

    def problems(self) -> List[str]:
        out = []
        if self.temperature not in ("C", "F"):
            out.append("temperature unit must be C or F")
        if self.concentration not in ("mol/mol", "ppm"):
            out.append("concentration unit must be mol/mol or ppm")
        if self.mass_fraction not in ("kg/kg", "ppm"):
            out.append("mass fraction unit must be kg/kg or ppm")
        return out


@dataclass
class CsvFileRef:
    path: str
    csv_type: str = "custom"
    time_column: int = 1
    header_rows: int = 2
    description_row: int = 2
    quantity_row: Optional[int] = None
    unit_row: Optional[int] = 1


@dataclass
class Data3DPoint:
    id: str
    group: str                                    # node id of the Data3D group it was made from
    quantity: str
    xyz: Tuple[float, float, float]


@dataclass
class Data3DSlice:
    id: str
    group: str
    quantity: str
    origin: Tuple[float, float, float]
    normal: Tuple[float, float, float]


@dataclass
class Data3DIso:
    id: str
    group: str
    quantity: str
    value: float


@dataclass
class GeneralPreferences:
    one_geometry_at_a_time: bool = True
    show_previous_on_open: bool = True
    allow_multiple_quantities: bool = True
    allow_conflicting_results: bool = True
    begin_playback_on_activation: bool = False
    dimension_precision: int = 3


@dataclass
class RenderingPreferences:
    level_of_detail: bool = True
    vertex_buffers: bool = True
    async_frames: bool = True
    ambient_occlusion: bool = False
    antialiasing: str = "smaa_1x"                 # disabled | smaa_1x | smaa_2tx | msaa_2 | msaa_4 | msaa_8 | msaa_16
    anisotropic_filtering: int = 1
    image_based_lighting: bool = False
    slice_renderer: str = "hardware"              # hardware | compatibility
    data3d_slice_renderer: str = "hardware"       # hardware | compatibility | disabled
    smoke_renderer: str = "hardware"              # hardware | compatibility | smokeview
    data3d_renderer: str = "hardware"             # hardware | compatibility | disabled
    reduce_banding: bool = True
    advanced_lighting: bool = False

    def problems(self) -> List[str]:
        out = []
        ok = ("disabled", "smaa_1x", "smaa_2tx", "msaa_2", "msaa_4", "msaa_8", "msaa_16")
        if self.antialiasing not in ok:
            out.append(f"antialiasing must be one of {', '.join(ok)}")
        if not 1 <= self.anisotropic_filtering <= 16:
            out.append("anisotropic_filtering must be 1 to 16")
        return out

    def max_quality(self) -> None:
        self.level_of_detail = self.vertex_buffers = self.async_frames = True
        self.ambient_occlusion = self.image_based_lighting = self.advanced_lighting = True
        self.antialiasing, self.anisotropic_filtering = "msaa_4", 16
        self.slice_renderer = self.data3d_slice_renderer = self.smoke_renderer = self.data3d_renderer = "hardware"
        self.reduce_banding = True

    def max_compatibility(self) -> None:
        self.level_of_detail = True
        self.vertex_buffers = self.ambient_occlusion = self.image_based_lighting = self.advanced_lighting = False
        self.async_frames = False
        self.antialiasing, self.anisotropic_filtering = "disabled", 1
        self.slice_renderer = self.smoke_renderer = "compatibility"
        self.data3d_slice_renderer = self.data3d_renderer = "compatibility"
        self.reduce_banding = False


GEOMETRY_SETS = ("fds_actual", "fds_requested", "pyfds_geometry", "ge1")
RENDER_MODES = ("solid", "solid_outlines", "realistic", "realistic_outlines", "wireframe")


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
