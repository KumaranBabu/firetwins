"""
PyFDS Smokeview INI File Writer
================================
Generates a Smokeview ``.ini`` (initialization) file that configures the
scene displayed when Smokeview opens a ``.smv`` case.

This is **separate** from the SSF script file:
- ``.ini``  — persistent scene configuration (colors, camera, colorbars, …)
- ``.ssf``  — automated script commands executed during a session

PyroSim writes this file to control how Smokeview initially displays the
case.  PyFDS implements the same capability.

Reference
---------
Smokeview User Manual 6.x, Chapter 9: "Smokeview INI File".

Example
-------
>>> from pyfds.smokeview.ini_writer import SmvIniConfig, SmvIniWriter
>>>
>>> cfg = SmvIniConfig()
>>> cfg.background_color = (0, 0, 0)          # black background
>>> cfg.foreground_color = (255, 255, 255)     # white text
>>> cfg.add_viewpoint("Front", eye=(15,0,3), target=(0,0,2))
>>> cfg.add_colorbar("TEMPERATURE", vmin=20, vmax=600, colormap="rainbow")
>>> cfg.add_surface_color("FireSource", rgb=(255, 64, 0))
>>>
>>> SmvIniWriter().write(cfg, "case.ini")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class SmvViewpoint:
    """A named camera viewpoint stored in the INI file."""
    name: str
    eye: Tuple[float, float, float] = (10.0, 10.0, 5.0)
    target: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    up: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    zoom: float = 1.0


@dataclass
class SmvColorbarConfig:
    """Colorbar (color scale) settings for one quantity."""
    quantity: str
    vmin: float = 0.0
    vmax: float = 100.0
    n_levels: int = 10
    colormap: str = "rainbow"          # rainbow, greyscale, hsv, fire, etc.
    show: bool = True
    auto_range: bool = False
    units: str = ""


@dataclass
class SmvSurfaceColor:
    """Per-surface display colour override."""
    surface_id: str
    rgb: Tuple[int, int, int] = (128, 128, 128)
    transparency: float = 0.0          # 0 = opaque, 1 = fully transparent
    show: bool = True


@dataclass
class SmvIniConfig:
    """
    Full configuration object for a Smokeview ``.ini`` file.

    Set fields as needed; defaults match Smokeview's built-in defaults.
    """
    # Scene colours
    background_color: Tuple[int, int, int] = (0, 0, 0)        # black
    foreground_color: Tuple[int, int, int] = (255, 255, 255)   # white

    # Geometry display
    show_geometry: bool = True
    show_mesh_boundaries: bool = False
    show_obstructions: bool = True
    show_vents: bool = True
    transparency_mode: bool = False

    # Lighting
    ambient_light: float = 0.3         # 0–1
    diffuse_light: float = 0.7         # 0–1

    # Time display
    show_time: bool = True
    show_colorbar: bool = True
    show_title: bool = True

    # Rendering
    render_width: int = 1280
    render_height: int = 720
    render_format: str = "png"          # png or jpg

    # Animation
    animation_fps: int = 10

    # Smoke3D rendering
    smoke3d_opacity_cutoff: float = 0.95
    smoke3d_max_opacity: float = 1.0

    # Named viewpoints
    viewpoints: List[SmvViewpoint] = field(default_factory=list)

    # Colorbar settings per quantity
    colorbars: List[SmvColorbarConfig] = field(default_factory=list)

    # Per-surface display settings
    surface_colors: List[SmvSurfaceColor] = field(default_factory=list)

    def add_viewpoint(
        self,
        name: str,
        eye: Tuple[float, float, float],
        target: Tuple[float, float, float],
        up: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        zoom: float = 1.0,
    ) -> "SmvIniConfig":
        """Add a named viewpoint. Returns self for chaining."""
        self.viewpoints.append(SmvViewpoint(
            name=name, eye=eye, target=target, up=up, zoom=zoom,
        ))
        return self

    def add_colorbar(
        self,
        quantity: str,
        vmin: float = 0.0,
        vmax: float = 100.0,
        colormap: str = "rainbow",
        n_levels: int = 10,
        auto_range: bool = False,
        units: str = "",
    ) -> "SmvIniConfig":
        """Add colorbar settings for a quantity. Returns self for chaining."""
        self.colorbars.append(SmvColorbarConfig(
            quantity=quantity, vmin=vmin, vmax=vmax,
            colormap=colormap, n_levels=n_levels,
            auto_range=auto_range, units=units,
        ))
        return self

    def add_surface_color(
        self,
        surface_id: str,
        rgb: Tuple[int, int, int],
        transparency: float = 0.0,
        show: bool = True,
    ) -> "SmvIniConfig":
        """Add per-surface colour override. Returns self for chaining."""
        self.surface_colors.append(SmvSurfaceColor(
            surface_id=surface_id, rgb=rgb,
            transparency=transparency, show=show,
        ))
        return self


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

class SmvIniWriter:
    """
    Writes a Smokeview ``.ini`` configuration file from a :class:`SmvIniConfig`.

    The INI format is line-based key=value with section headers in brackets.
    """

    def write(self, config: SmvIniConfig, filepath: str) -> None:
        """Write *config* to *filepath*."""
        text = self.generate(config)
        Path(filepath).write_text(text, encoding="utf-8")

    def generate(self, config: SmvIniConfig) -> str:
        """Return the INI file content as a string."""
        lines: List[str] = []

        lines.append("# Smokeview INI — generated by PyFDS SmvIniWriter")
        lines.append("")

        # Scene / rendering
        lines.append("[SCENE]")
        r, g, b = config.background_color
        lines.append(f"BACKGROUNDCOLOR={r} {g} {b}")
        r, g, b = config.foreground_color
        lines.append(f"FOREGROUNDCOLOR={r} {g} {b}")
        lines.append(f"SHOWGEOMETRY={'1' if config.show_geometry else '0'}")
        lines.append(f"SHOWMESHBOUNDARIES={'1' if config.show_mesh_boundaries else '0'}")
        lines.append(f"SHOWOBSTRUCTIONS={'1' if config.show_obstructions else '0'}")
        lines.append(f"SHOWVENTS={'1' if config.show_vents else '0'}")
        lines.append(f"TRANSPARENCYMODE={'1' if config.transparency_mode else '0'}")
        lines.append(f"SHOWTIME={'1' if config.show_time else '0'}")
        lines.append(f"SHOWCOLORBAR={'1' if config.show_colorbar else '0'}")
        lines.append(f"SHOWTITLE={'1' if config.show_title else '0'}")
        lines.append("")

        # Lighting
        lines.append("[LIGHTING]")
        lines.append(f"AMBIENTLIGHT={config.ambient_light:.4f}")
        lines.append(f"DIFFUSELIGHT={config.diffuse_light:.4f}")
        lines.append("")

        # Rendering options
        lines.append("[RENDER]")
        lines.append(f"RENDERWIDTH={config.render_width}")
        lines.append(f"RENDERHEIGHT={config.render_height}")
        lines.append(f"RENDERFORMAT={config.render_format.upper()}")
        lines.append(f"ANIMATIONFPS={config.animation_fps}")
        lines.append("")

        # Smoke3D
        lines.append("[SMOKE3D]")
        lines.append(f"SMOKE3DOPACITYCUTOFF={config.smoke3d_opacity_cutoff:.4f}")
        lines.append(f"SMOKE3DMAXOPACITY={config.smoke3d_max_opacity:.4f}")
        lines.append("")

        # Viewpoints
        if config.viewpoints:
            lines.append("[VIEWPOINTS]")
            lines.append(f"NVIEWPOINTS={len(config.viewpoints)}")
            for vp in config.viewpoints:
                ex, ey, ez = vp.eye
                tx, ty, tz = vp.target
                ux, uy, uz = vp.up
                lines.append(f"VIEWPOINT {vp.name}")
                lines.append(f"  EYE {ex:.6f} {ey:.6f} {ez:.6f}")
                lines.append(f"  TARGET {tx:.6f} {ty:.6f} {tz:.6f}")
                lines.append(f"  UP {ux:.6f} {uy:.6f} {uz:.6f}")
                lines.append(f"  ZOOM {vp.zoom:.6f}")
            lines.append("")

        # Colorbar settings
        if config.colorbars:
            lines.append("[COLORBARS]")
            lines.append(f"NCOLORBARS={len(config.colorbars)}")
            for cb in config.colorbars:
                lines.append(f"COLORBAR {cb.quantity}")
                lines.append(f"  COLORMAP {cb.colormap}")
                lines.append(f"  VMIN {cb.vmin:.6g}")
                lines.append(f"  VMAX {cb.vmax:.6g}")
                lines.append(f"  NLEVELS {cb.n_levels}")
                lines.append(f"  AUTORANGE {'1' if cb.auto_range else '0'}")
                lines.append(f"  SHOW {'1' if cb.show else '0'}")
                if cb.units:
                    lines.append(f"  UNITS {cb.units}")
            lines.append("")

        # Per-surface colours
        if config.surface_colors:
            lines.append("[SURFACECOLORS]")
            lines.append(f"NSURFACECOLORS={len(config.surface_colors)}")
            for sc in config.surface_colors:
                r, g, b = sc.rgb
                lines.append(f"SURFACECOLOR {sc.surface_id}")
                lines.append(f"  RGB {r} {g} {b}")
                lines.append(f"  TRANSPARENCY {sc.transparency:.4f}")
                lines.append(f"  SHOW {'1' if sc.show else '0'}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parser (round-trip support)
# ---------------------------------------------------------------------------

class SmvIniParser:
    """
    Parses a Smokeview ``.ini`` file back into an :class:`SmvIniConfig`.

    Tolerant parser — unknown keys are silently skipped.
    """

    def parse(self, filepath: str) -> SmvIniConfig:
        """Parse *filepath* and return a :class:`SmvIniConfig`."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"INI file not found: {filepath}")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return self._parse_lines(lines)

    def parse_string(self, text: str) -> SmvIniConfig:
        """Parse INI content from a string."""
        return self._parse_lines(text.splitlines())

    def _parse_lines(self, lines: List[str]) -> SmvIniConfig:
        cfg = SmvIniConfig()
        section = ""
        vp: Optional[SmvViewpoint] = None
        cb: Optional[SmvColorbarConfig] = None
        sc: Optional[SmvSurfaceColor] = None

        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            # Section header
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].upper()
                # Flush any in-progress block
                if vp is not None: cfg.viewpoints.append(vp); vp = None
                if cb is not None: cfg.colorbars.append(cb); cb = None
                if sc is not None: cfg.surface_colors.append(sc); sc = None
                continue

            # Block headers within sections
            parts = line.split(None, 1)
            key = parts[0].upper()
            val = parts[1] if len(parts) > 1 else ""

            if section == "SCENE":
                if key == "BACKGROUNDCOLOR":
                    cfg.background_color = self._rgb(val)
                elif key == "FOREGROUNDCOLOR":
                    cfg.foreground_color = self._rgb(val)
                elif key == "SHOWGEOMETRY":       cfg.show_geometry = val.strip() == "1"
                elif key == "SHOWMESHBOUNDARIES": cfg.show_mesh_boundaries = val.strip() == "1"
                elif key == "SHOWOBSTRUCTIONS":   cfg.show_obstructions = val.strip() == "1"
                elif key == "SHOWVENTS":          cfg.show_vents = val.strip() == "1"
                elif key == "TRANSPARENCYMODE":   cfg.transparency_mode = val.strip() == "1"
                elif key == "SHOWTIME":           cfg.show_time = val.strip() == "1"
                elif key == "SHOWCOLORBAR":       cfg.show_colorbar = val.strip() == "1"
                elif key == "SHOWTITLE":          cfg.show_title = val.strip() == "1"

            elif section == "LIGHTING":
                if key == "AMBIENTLIGHT": cfg.ambient_light = float(val)
                elif key == "DIFFUSELIGHT": cfg.diffuse_light = float(val)

            elif section == "RENDER":
                if key == "RENDERWIDTH":   cfg.render_width = int(val)
                elif key == "RENDERHEIGHT":cfg.render_height = int(val)
                elif key == "RENDERFORMAT":cfg.render_format = val.strip().lower()
                elif key == "ANIMATIONFPS":cfg.animation_fps = int(val)

            elif section == "SMOKE3D":
                if key == "SMOKE3DOPACITYCUTOFF": cfg.smoke3d_opacity_cutoff = float(val)
                elif key == "SMOKE3DMAXOPACITY":  cfg.smoke3d_max_opacity = float(val)

            elif section == "VIEWPOINTS":
                if key == "VIEWPOINT":
                    if vp is not None: cfg.viewpoints.append(vp)
                    vp = SmvViewpoint(name=val.strip())
                elif vp is not None:
                    if key == "EYE":    vp.eye    = self._xyz(val)
                    elif key == "TARGET": vp.target = self._xyz(val)
                    elif key == "UP":   vp.up     = self._xyz(val)
                    elif key == "ZOOM": vp.zoom   = float(val)

            elif section == "COLORBARS":
                if key == "COLORBAR":
                    if cb is not None: cfg.colorbars.append(cb)
                    cb = SmvColorbarConfig(quantity=val.strip())
                elif cb is not None:
                    if key == "COLORMAP":  cb.colormap   = val.strip()
                    elif key == "VMIN":    cb.vmin        = float(val)
                    elif key == "VMAX":    cb.vmax        = float(val)
                    elif key == "NLEVELS": cb.n_levels    = int(val)
                    elif key == "AUTORANGE": cb.auto_range = val.strip() == "1"
                    elif key == "SHOW":    cb.show        = val.strip() == "1"
                    elif key == "UNITS":   cb.units       = val.strip()

            elif section == "SURFACECOLORS":
                if key == "SURFACECOLOR":
                    if sc is not None: cfg.surface_colors.append(sc)
                    sc = SmvSurfaceColor(surface_id=val.strip())
                elif sc is not None:
                    if key == "RGB":          sc.rgb          = self._rgb(val)
                    elif key == "TRANSPARENCY": sc.transparency = float(val)
                    elif key == "SHOW":        sc.show         = val.strip() == "1"

        # Flush trailing blocks
        if vp is not None: cfg.viewpoints.append(vp)
        if cb is not None: cfg.colorbars.append(cb)
        if sc is not None: cfg.surface_colors.append(sc)

        return cfg

    def _rgb(self, val: str) -> Tuple[int, int, int]:
        p = val.split()
        return (int(p[0]), int(p[1]), int(p[2])) if len(p) >= 3 else (128, 128, 128)

    def _xyz(self, val: str) -> Tuple[float, float, float]:
        p = val.split()
        return (float(p[0]), float(p[1]), float(p[2])) if len(p) >= 3 else (0.0, 0.0, 0.0)
