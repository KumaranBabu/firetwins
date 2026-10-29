"""
PyFDS Smokeview INI File Writer
================================
Writes and reads Smokeview ``.ini`` settings files in the format Smokeview 6.10.1 itself reads and writes:
each keyword on a line of its own, its values on the next line(s), indented by one space::

    WINDOWWIDTH
     1280
    V2_SLICE
     0 20.000000 0 300.000000 temp

Save the file as ``<casename>.ini`` beside ``<casename>.smv`` and Smokeview loads it when it opens the case, or load it
from a script with ``LOADINIFILE``. Only the settings you set are written; everything else keeps the user's own
Smokeview settings.

This is **separate** from the SSF script file:
- ``.ini``  — persistent scene settings (colours, labels, colour bar, data bounds, picture size)
- ``.ssf``  — automated script commands executed during a session (camera, time, loading data, rendering)

Every keyword written here was checked by rendering the demo cases with Smokeview 6.10.1 and comparing the pictures.
Settings that Smokeview 6.10.1 accepts but ignores (``SHOWBLOCKS``, ``SHOWTRANSPARENT``, ``SHOWVENTS``,
``OBSTSURFCOLORS``) or that have no ``.ini`` keyword are refused with :class:`SmvIniUnsupported`.

Example
-------
>>> from pyfds.smokeview.ini_writer import SmvIniConfig, SmvIniWriter
>>>
>>> cfg = SmvIniConfig()
>>> cfg.background_color = (0, 0, 0)          # black background
>>> cfg.foreground_color = (255, 255, 255)     # white text and outlines
>>> cfg.colormap = "Rainbow"
>>> cfg.add_colorbar("temp", vmin=20, vmax=600)   # Smokeview's short name of the slice quantity
>>>
>>> SmvIniWriter().write(cfg, "case.ini")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .scripting_common import SmokeviewScriptUnsupported


class SmvIniUnsupported(SmokeviewScriptUnsupported):
    """A scene setting that Smokeview 6.10.1 ``.ini`` files cannot carry (no keyword, or the keyword is ignored)."""


def _unsupported(what: str, instead: str) -> SmvIniUnsupported:
    return SmvIniUnsupported(f"Smokeview 6.10.1 .ini files cannot {what}. {instead}")


# Settings the old (invented) format offered, and why they are gone.
_REMOVED = {
    "show_geometry": ("hide the geometry (SHOWBLOCKS is ignored)", "Clip it away in a script (SETCLIPMODE / SETCLIPX)."),
    "show_obstructions": ("hide obstructions (SHOWBLOCKS is ignored)", "Clip them away in a script (SETCLIPMODE)."),
    "transparency_mode": ("make obstructions transparent (SHOWTRANSPARENT is ignored)",
                          "Give the SURF or OBST a TRANSPARENCY in the FDS input."),
    "show_mesh_boundaries": ("draw mesh boundaries", "show_frame draws the outline of the whole domain."),
    "render_width": ("set a render size apart from the window size", "Use window_width."),
    "render_height": ("set a render size apart from the window size", "Use window_height."),
    "animation_fps": ("set an animation frame rate", "Pass fps when making the movie from the rendered frames."),
    "smoke3d_opacity_cutoff": ("set a 3D smoke opacity cutoff", "Leave it to Smokeview."),
    "smoke3d_max_opacity": ("set a 3D smoke maximum opacity", "Leave it to Smokeview."),
    "viewpoints": ("hold named viewpoints PyFDS can write (VIEWPOINT6 stores Smokeview's internal view matrices)",
                   "Save viewpoints from Smokeview's own View menu, or set the camera in a script (set_camera / set_view)."),
    "surface_colors": ("recolour surfaces (OBSTSURFCOLORS is ignored)", "Set COLOR or RGB on the SURF in the FDS input."),
}


@dataclass
class SmvColorbarConfig:
    """Colour-bar bounds of one slice quantity (``V2_SLICE``).

    *quantity* is Smokeview's short name of the quantity, as listed in the ``.smv`` file under each SLCF entry
    (``temp`` for TEMPERATURE, ``VIS_C`` for SOOT VISIBILITY, ...). With *auto_range* Smokeview uses the bounds of the
    loaded data instead of *vmin*/*vmax*.
    """
    quantity: str
    vmin: float = 0.0
    vmax: float = 100.0
    auto_range: bool = False


@dataclass
class SmvSurfaceColor:
    """Kept for imports only: Smokeview 6.10.1 ignores per-surface colours from an ``.ini`` file."""
    surface_id: str
    rgb: Tuple[int, int, int] = (128, 128, 128)
    transparency: float = 0.0
    show: bool = True


@dataclass
class SmvIniConfig:
    """
    The scene settings of a Smokeview ``.ini`` file. ``None`` leaves a setting as the user's Smokeview has it.

    Colours are 0-255 RGB. Setting either colour also writes ``FLIP 0``, so the background really is
    *background_color* even when the user has Smokeview's white-background option on.
    """
    # Scene colours                                               keyword(s)
    background_color: Optional[Tuple[int, int, int]] = None      # BACKGROUNDCOLOR (+ FLIP 0)
    foreground_color: Optional[Tuple[int, int, int]] = None      # FOREGROUNDCOLOR (+ FLIP 0)

    # Geometry display
    show_frame: Optional[bool] = None                            # SHOWFRAME: outline of the domain
    show_vents: Optional[bool] = None                            # SHOWOTHERVENTS: vents other than open ones
    show_open_vents: Optional[bool] = None                       # SHOWOPENVENTS

    # Lighting (0-1, grey)
    ambient_light: Optional[float] = None                        # LIGHTPROP line 1
    diffuse_light: Optional[float] = None                        # LIGHTPROP line 2

    # Labels
    show_time: Optional[bool] = None                             # SHOWTIMEBAR + SHOWTIMELABEL
    show_colorbar: Optional[bool] = None                         # SHOWCOLORBARS (vertical)
    show_title: Optional[bool] = None                            # SHOWTITLE: Smokeview version and FDS title

    # Rendering: the picture is the size of the window
    window_width: Optional[int] = None                           # WINDOWWIDTH
    window_height: Optional[int] = None                          # WINDOWHEIGHT
    render_format: Optional[str] = None                          # RENDERFILETYPE: "png" or "jpg"

    # Colour bar
    colormap: Optional[str] = None                               # COLORBARTYPE: a name from Smokeview's Colorbar menu
    colorbars: List[SmvColorbarConfig] = field(default_factory=list)   # V2_SLICE, one per quantity

    def __setattr__(self, name: str, value) -> None:
        if name in _REMOVED:
            raise _unsupported(*_REMOVED[name])
        super().__setattr__(name, value)

    def __getattr__(self, name: str):          # only called for attributes that do not exist
        if name in _REMOVED:
            raise _unsupported(*_REMOVED[name])
        raise AttributeError(f"{type(self).__name__!s} has no attribute {name!r}")

    def add_viewpoint(self, name: str, *args, **kwargs) -> "SmvIniConfig":
        """Not possible: see :data:`_REMOVED` ``viewpoints``."""
        raise _unsupported(*_REMOVED["viewpoints"])

    def add_colorbar(
        self,
        quantity: str,
        vmin: float = 0.0,
        vmax: float = 100.0,
        auto_range: bool = False,
    ) -> "SmvIniConfig":
        """Set the colour-bar bounds of slice quantity *quantity* (Smokeview's short name, e.g. ``temp``).
        Returns self for chaining."""
        if not quantity or quantity.split()[0] != quantity:
            raise ValueError(f"quantity must be Smokeview's short name without spaces (e.g. 'temp'), not {quantity!r}")
        self.colorbars.append(SmvColorbarConfig(quantity=quantity, vmin=vmin, vmax=vmax, auto_range=auto_range))
        return self

    def add_surface_color(self, surface_id: str, *args, **kwargs) -> "SmvIniConfig":
        """Not possible: see :data:`_REMOVED` ``surface_colors``."""
        raise _unsupported(*_REMOVED["surface_colors"])


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

_FORMATS = {"png": 0, "jpg": 1, "jpeg": 1}      # RENDERFILETYPE first value
# Smokeview's own defaults, written for the half of a two-line or multi-value keyword that is not set.
_DEFAULT_AMBIENT, _DEFAULT_DIFFUSE = 0.6, 0.5


def _bit(flag: bool) -> str:
    return "1" if flag else "0"


def _rgb(rgb: Tuple[int, int, int]) -> str:
    if len(rgb) != 3 or any(not 0 <= int(c) <= 255 for c in rgb):
        raise ValueError(f"colour must be three 0-255 values, not {rgb!r}")
    return " ".join(f"{int(c) / 255:.6f}" for c in rgb)


def _grey(value: float) -> str:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"light must be between 0 and 1, not {value!r}")
    return " ".join([f"{value:.6f}"] * 3)


class SmvIniWriter:
    """Writes a Smokeview ``.ini`` file from a :class:`SmvIniConfig`."""

    def write(self, config: SmvIniConfig, filepath: str) -> None:
        """Write *config* to *filepath* (name it ``<casename>.ini`` for Smokeview to load it with the case)."""
        Path(filepath).write_text(self.generate(config), encoding="utf-8")

    def generate(self, config: SmvIniConfig) -> str:
        """Return the INI file content as a string."""
        return "".join(f"{key}\n" + "".join(f" {v}\n" for v in values) for key, values in self.entries(config))

    def entries(self, config: SmvIniConfig) -> List[Tuple[str, List[str]]]:
        """The (keyword, value lines) pairs *config* sets, in writing order."""
        out: List[Tuple[str, List[str]]] = []
        c = config

        if c.background_color is not None or c.foreground_color is not None:
            out.append(("FLIP", ["0"]))
        if c.background_color is not None:
            out.append(("BACKGROUNDCOLOR", [_rgb(c.background_color)]))
        if c.foreground_color is not None:
            out.append(("FOREGROUNDCOLOR", [_rgb(c.foreground_color)]))

        if c.show_frame is not None:
            out.append(("SHOWFRAME", [_bit(c.show_frame)]))
        if c.show_vents is not None:
            out.append(("SHOWOTHERVENTS", [_bit(c.show_vents)]))
        if c.show_open_vents is not None:
            out.append(("SHOWOPENVENTS", [f"{_bit(c.show_open_vents)} 0"]))

        if c.ambient_light is not None or c.diffuse_light is not None:
            ambient = _DEFAULT_AMBIENT if c.ambient_light is None else c.ambient_light
            diffuse = _DEFAULT_DIFFUSE if c.diffuse_light is None else c.diffuse_light
            out.append(("LIGHTPROP", [_grey(ambient), _grey(diffuse)]))

        if c.show_time is not None:
            out.append(("SHOWTIMEBAR", [f"{_bit(c.show_time)} 2"]))
            out.append(("SHOWTIMELABEL", [_bit(c.show_time)]))
        if c.show_colorbar is not None:
            out.append(("SHOWCOLORBARS", [f"{_bit(c.show_colorbar)} 0"]))
        if c.show_title is not None:
            out.append(("SHOWTITLE", ["1 0 1" if c.show_title else "0 0 0"]))

        if c.window_width is not None:
            out.append(("WINDOWWIDTH", [str(int(c.window_width))]))
        if c.window_height is not None:
            out.append(("WINDOWHEIGHT", [str(int(c.window_height))]))
        if c.render_format is not None:
            fmt = c.render_format.lower()
            if fmt not in _FORMATS:
                raise ValueError(f"render_format must be 'png' or 'jpg', not {c.render_format!r}")
            out.append(("RENDERFILETYPE", [f"{_FORMATS[fmt]} 0 2"]))

        if c.colormap is not None:
            out.append(("COLORBARTYPE", [f"0 % {c.colormap}"]))
        for cb in c.colorbars:
            flag = "1" if cb.auto_range else "0"      # 0: use the value given, 1: the bounds of the loaded data
            out.append(("V2_SLICE", [f"{flag} {cb.vmin:.6f} {flag} {cb.vmax:.6f} {cb.quantity}"]))
        return out


# ---------------------------------------------------------------------------
# Parser (round-trip support)
# ---------------------------------------------------------------------------

# keyword -> number of value lines, for the keywords the parser reads (as Smokeview does, a known keyword is
# followed by a fixed number of value lines; any other line is skipped).
_VALUE_LINES: Dict[str, int] = {
    "FLIP": 1, "BACKGROUNDCOLOR": 1, "FOREGROUNDCOLOR": 1, "SHOWFRAME": 1, "SHOWOTHERVENTS": 1, "SHOWOPENVENTS": 1,
    "LIGHTPROP": 2, "SHOWTIMEBAR": 1, "SHOWTIMELABEL": 1, "SHOWCOLORBARS": 1, "SHOWTITLE": 1,
    "WINDOWWIDTH": 1, "WINDOWHEIGHT": 1, "RENDERFILETYPE": 1, "COLORBARTYPE": 1, "V2_SLICE": 1,
}


class SmvIniParser:
    """
    Reads the settings :class:`SmvIniConfig` covers from a Smokeview ``.ini`` file (one PyFDS wrote, or one
    Smokeview saved). Other keywords are skipped.
    """

    def parse(self, filepath: str) -> SmvIniConfig:
        """Parse *filepath* and return a :class:`SmvIniConfig`."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"INI file not found: {filepath}")
        return self.parse_string(path.read_text(encoding="utf-8", errors="replace"))

    def parse_string(self, text: str) -> SmvIniConfig:
        """Parse INI content from a string."""
        cfg = SmvIniConfig()
        lines = text.splitlines()
        flip = None
        i = 0
        while i < len(lines):
            raw = lines[i]
            i += 1
            key = raw.strip()
            if raw[:1].isspace() or key not in _VALUE_LINES:
                continue
            n = _VALUE_LINES[key]
            values = [v.strip() for v in lines[i:i + n]]
            i += n
            if len(values) < n:
                break
            try:
                flip = self._apply(cfg, key, values, flip)
            except (ValueError, IndexError):
                continue                    # a malformed value: Smokeview would read garbage, we skip it
        if flip not in (None, 0):
            # With FLIP 1 Smokeview draws BACKGROUNDCOLOR as the foreground and the other way round.
            cfg.background_color, cfg.foreground_color = cfg.foreground_color, cfg.background_color
        return cfg

    def _apply(self, cfg: SmvIniConfig, key: str, values: List[str], flip):
        first = values[0].split()
        if key == "FLIP":
            return int(first[0])
        if key == "BACKGROUNDCOLOR":
            cfg.background_color = self._rgb(first)
        elif key == "FOREGROUNDCOLOR":
            cfg.foreground_color = self._rgb(first)
        elif key == "SHOWFRAME":
            cfg.show_frame = first[0] != "0"
        elif key == "SHOWOTHERVENTS":
            cfg.show_vents = first[0] != "0"
        elif key == "SHOWOPENVENTS":
            cfg.show_open_vents = first[0] != "0"
        elif key == "LIGHTPROP":
            cfg.ambient_light = float(first[0])
            cfg.diffuse_light = float(values[1].split()[0])
        elif key == "SHOWTIMEBAR":
            cfg.show_time = first[0] != "0"
        elif key == "SHOWCOLORBARS":
            cfg.show_colorbar = first[0] != "0" or (len(first) > 1 and first[1] != "0")
        elif key == "SHOWTITLE":
            cfg.show_title = any(v != "0" for v in first)
        elif key == "WINDOWWIDTH":
            cfg.window_width = int(first[0])
        elif key == "WINDOWHEIGHT":
            cfg.window_height = int(first[0])
        elif key == "RENDERFILETYPE":
            cfg.render_format = "jpg" if first[0] == "1" else "png"
        elif key == "COLORBARTYPE":
            if "%" in values[0]:
                cfg.colormap = values[0].split("%", 1)[1].strip()
        elif key == "V2_SLICE":
            body = values[0].split(":", 1)[0].split()       # anything after ':' is contour-line settings
            if len(body) >= 5:
                cfg.colorbars.append(SmvColorbarConfig(
                    quantity=body[4], vmin=float(body[1]), vmax=float(body[3]),
                    auto_range=body[0] != "0" or body[2] != "0"))
        return flip

    @staticmethod
    def _rgb(parts: List[str]) -> Tuple[int, int, int]:
        return tuple(int(round(float(p) * 255)) for p in parts[:3])  # type: ignore[return-value]
