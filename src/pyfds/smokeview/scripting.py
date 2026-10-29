"""
PyFDS SMV Script Builder (SSF)
===============================
Programmatic construction of Smokeview Script Files (``*.ssf``) for automated rendering: run them with
``smokeview -script <file>.ssf <casename>``.

Every command the builder writes was checked against Smokeview 6.10.1 (an unknown keyword stops the whole
script). Methods for things Smokeview's scripts cannot do raise :class:`SmokeviewScriptUnsupported` instead of
writing a command that would fail or be ignored.

Commands written
----------------
RENDERTYPE              image format (PNG / JPG)
LOADINIFILE             the render settings (picture size, labels off) from a small .ini written beside the script
SETTIMEVAL              jump to a simulation time
SETVIEWPOINT            a named viewpoint from the case
XYZVIEW                 camera position and direction (set_camera)
VIEWXMIN ... VIEWZMAX   look at the scene along an axis (set_view)
LOADSLICE / LOADSLCF    a slice (LOADSLCF for cell-centred slices and vector slices)
LOADBOUNDARY, LOADISO, LOAD3DSMOKE, LOADPARTICLES, LOADPLOT3D
SETCBAR                 colour bar (colour map)
SETCLIPMODE, SETCLIPX/Y/Z   clip planes
RENDERONCE, RENDERALL   one picture / one picture per frame
UNLOADALL

Example::

    from pyfds.smokeview.scripting import SsfScriptBuilder

    builder = SsfScriptBuilder()
    builder.set_render_options(width=1280, height=720)
    builder.load_slice("TEMPERATURE", axis=2, position=2.4)
    for t in [30, 60]:
        builder.set_time(t)
        builder.screenshot(f"temp_{t:03d}s")
    builder.write("render_script.ssf")        # also writes render_script_settings.ini, which the script loads
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional

from .scripting_load import (  # noqa: F401  (re-exported)
    SsfScriptBuilderLoadMixin,
)
from .scripting_show import (  # noqa: F401  (re-exported)
    SsfScriptBuilderShowMixin,
)
from .scripting_style import (  # noqa: F401  (re-exported)
    SsfScriptBuilderStyleMixin,
)
from .scripting_common import (  # noqa: F401  (re-exported)
    SmokeviewScriptUnsupported,
    _SsfCommand,
    _unsupported,
)


class SsfScriptBuilder(SsfScriptBuilderLoadMixin, SsfScriptBuilderShowMixin, SsfScriptBuilderStyleMixin):
    """
    Builds a Smokeview Script File (SSF) incrementally.

    All methods return ``self`` for optional chaining.
    """

    def __init__(self) -> None:
        self._commands: List[_SsfCommand] = []
        self._render_width  = 800
        self._render_height = 600
        self._image_format  = "png"
        self._settings: Dict[str, str] = {}       # Smokeview .ini keyword -> value line (LOADINIFILE)

    def set_render_options(
        self,
        *,
        width: int = 800,
        height: int = 600,
        image_format: str = "png",
        labels: bool = False,
    ) -> "SsfScriptBuilder":
        """
        Configure output image dimensions and format.

        Parameters
        ----------
        width, height : int
            Pixel dimensions of rendered images.
        image_format : str
            ``"png"`` or ``"jpg"`` / ``"jpeg"``.
        labels : bool
            Keep Smokeview's title, frame number and mesh labels on the pictures (False: the time bar and
            colour bar only, whatever the user's own smokeview.ini says).
        """
        self._render_width  = width
        self._render_height = height
        self._image_format  = image_format.lower().replace("jpeg", "jpg")
        # The picture is the size of Smokeview's window. RENDERSIZE is accepted but changes nothing (Smokeview
        # 6.10.1), so the window size goes into the settings .ini that the script loads first.
        self._settings["WINDOWWIDTH"] = str(int(width))
        self._settings["WINDOWHEIGHT"] = str(int(height))
        if not labels:
            self._settings.update({"SHOWTITLE": "0 0 0", "SHOWFRAMELABEL": "0", "SHOWBLOCKLABEL": "0"})
        self._commands.append(_SsfCommand("RENDERTYPE", [self._image_format.upper()]))
        return self

    def set_time(self, sim_time: float) -> "SsfScriptBuilder":
        """Jump to *sim_time* seconds in the simulation."""
        self._commands.append(_SsfCommand(
            "SETTIMEVAL", [f"{sim_time:.4f}"],
            comment=f"t = {sim_time} s",
        ))
        return self

    def step_forward(self, n_steps: int = 1) -> "SsfScriptBuilder":
        """Not available: Smokeview scripts move through a run by time only."""
        raise _unsupported("step through frames", "Use set_time() for each time, or render_movie() for all frames.")

    def set_viewpoint(self, name: str) -> "SsfScriptBuilder":
        """Load a named viewpoint defined in the case (its .ini or the .smv)."""
        self._commands.append(_SsfCommand("SETVIEWPOINT", [name]))
        return self

    def set_view(self, side: str) -> "SsfScriptBuilder":
        """Look at the whole scene from one side: ``"xmin"``, ``"xmax"``, ``"ymin"``, ``"ymax"``, ``"zmin"`` or
        ``"zmax"`` (``"xmin"`` looks from the low-x side towards +x). Use it to see an x- or z-slice face on."""
        side = side.lower()
        if side not in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax"):
            raise ValueError(f"side must be xmin, xmax, ymin, ymax, zmin or zmax, not {side!r}")
        self._commands.append(_SsfCommand(f"VIEW{side.upper()}"))
        return self

    def set_camera(
        self,
        eye: tuple,
        target: tuple,
        up: tuple = (0.0, 0.0, 1.0),
    ) -> "SsfScriptBuilder":
        """
        Put the camera at *eye* looking towards *target* (Smokeview's XYZVIEW).

        Parameters
        ----------
        eye    : (x, y, z) — camera position (metres)
        target : (x, y, z) — look-at point
        up     : kept for old callers; Smokeview keeps the z axis up
        """
        dx, dy, dz = (target[i] - eye[i] for i in range(3))
        if dx == dy == dz == 0:
            raise ValueError("eye and target are the same point")
        # XYZVIEW x y z azimuth elevation: azimuth 0 looks along +y and 90 along +x; elevation is positive upwards
        azimuth = math.degrees(math.atan2(dx, dy))
        elevation = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
        self._commands.append(_SsfCommand(
            "XYZVIEW", [f"{eye[0]:g} {eye[1]:g} {eye[2]:g} {azimuth:.2f} {elevation:.2f}"],
        ))
        return self

    def unload_all(self) -> "SsfScriptBuilder":
        """Deactivate all currently-loaded visualization objects."""
        self._commands.append(_SsfCommand("UNLOADALL"))
        return self

    def screenshot(self, filename: Optional[str] = None) -> "SsfScriptBuilder":
        """Render and save a screenshot. Smokeview takes a base name and adds ``.png`` (or ``.jpg``) itself,
        writing into its working directory, so any folder and extension in *filename* are dropped."""
        if filename:
            self._commands.append(_SsfCommand("RENDERONCE", [Path(filename).stem]))
        else:
            self._commands.append(_SsfCommand("RENDERONCE"))
        return self

    def render_movie(
        self,
        filename: str,
        *,
        fps: int = 10,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> "SsfScriptBuilder":
        """
        Render a movie over the time range [*start_time*, *end_time*].

        Parameters
        ----------
        filename : str
            Output movie filename (``*.avi``, ``*.mp4``).
        fps : int
            Frames per second.
        start_time, end_time : float, optional
            Simulation time range. If None, Smokeview uses the full range.
        """
        # Smokeview's RENDERALL writes one image per frame: <base>_0000.png, <base>_0001.png ...
        # (turning those into a movie file needs an encoder such as ffmpeg - see SmokeviewRunner.encode_frames).
        # *fps*, *start_time* and *end_time* are not part of the script; the caller trims or encodes afterwards.
        self._commands.append(_SsfCommand("RENDERALL", ["1", Path(filename).stem]))
        return self

    def comment(self, text: str) -> "SsfScriptBuilder":
        """Insert a comment line (prefixed with ``#``)."""
        self._commands.append(_SsfCommand(f"# {text}"))
        return self

    def raw(self, line: str) -> "SsfScriptBuilder":
        """Insert a raw SSF line verbatim (escape hatch for unsupported commands)."""
        self._commands.append(_SsfCommand(line))
        return self

    def clear(self) -> "SsfScriptBuilder":
        """Remove all commands from the builder."""
        self._commands.clear()
        return self

    def settings_ini(self) -> str:
        """The render settings (picture size, labels) as Smokeview .ini text, or "" when there are none."""
        return "".join(f"{key}\n {value}\n" for key, value in self._settings.items())

    def build(self, settings_file: Optional[str] = None) -> str:
        """Render all commands to SSF text. With *settings_file* (where :meth:`settings_ini` is written) the
        script loads it first; :meth:`write` and the Smokeview runner do this for you."""
        if not self._commands:
            return ""
        lines = []
        if settings_file and self._settings:
            lines.append(_SsfCommand("LOADINIFILE", [str(settings_file)]).render())
        for cmd in self._commands:
            lines.append(cmd.render())
        lines.append("")
        return "\n".join(lines)

    def write(self, filepath: str) -> None:
        """Write the script to *filepath*, and its render settings to ``<name>_settings.ini`` beside it."""
        path = Path(filepath)
        settings = None
        if self._settings:
            settings = path.with_name(f"{path.stem}_settings.ini").resolve()
            settings.write_text(self.settings_ini(), encoding="utf-8")
        path.write_text(self.build(str(settings) if settings else None), encoding="utf-8")

    def __repr__(self) -> str:
        return f"<SsfScriptBuilder commands={len(self._commands)}>"
