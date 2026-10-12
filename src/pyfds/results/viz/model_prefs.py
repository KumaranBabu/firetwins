"""Visualization model: colour bars and preferences."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


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
