"""
PyFDS SMV Script Builder (SSF)
===============================
Programmatic construction of Smokeview Script Files (``*.ssf``) for
headless/automated rendering, movie generation, and scene configuration.

SSF is a line-oriented command language read by ``smokeview -ini <file>``.
This builder provides a fluent API that validates command combinations and
emits well-formed SSF text.

Supported SSF commands
----------------------
SETTIMEVAL          — jump to a specific simulation time
SETVIEWPOINT        — load a named camera viewpoint
LOADSLICE           — activate a slice file by quantity + mesh
LOADBOUNDARY        — activate a boundary file by quantity + mesh
LOADISOSURFACE      — activate an isosurface
LOADSMOKE3D         — activate a smoke-3D file
RENDERONCE          — capture a single PNG/JPEG screenshot
RENDERMOVIE         — render all frames as a movie
SETRENDER           — configure render parameters (resolution, format)
LABEL               — add overlay text label
UNLOADALL           — deactivate all currently-loaded visualization objects

Example::

    from pyfds.smokeview.scripting import SsfScriptBuilder

    builder = SsfScriptBuilder()
    builder.set_render_options(width=1920, height=1080, image_format="png")
    builder.load_slice(quantity="TEMPERATURE", mesh=1)
    builder.set_viewpoint("front")

    for t in [30, 60, 90, 120]:
        builder.set_time(t)
        builder.screenshot(f"temp_{t:03d}s.png")

    print(builder.build())

    # Or write directly to a file
    builder.write("render_script.ssf")
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

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
    _SsfCommand,
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

    def set_render_options(
        self,
        *,
        width: int = 800,
        height: int = 600,
        image_format: str = "png",
    ) -> "SsfScriptBuilder":
        """
        Configure output image dimensions and format.

        Parameters
        ----------
        width, height : int
            Pixel dimensions of rendered images.
        image_format : str
            ``"png"`` or ``"jpg"`` / ``"jpeg"``.
        """
        self._render_width  = width
        self._render_height = height
        self._image_format  = image_format.lower().replace("jpeg", "jpg")
        self._commands.append(_SsfCommand(
            "SETRENDER",
            [str(width), str(height), self._image_format.upper()],
            comment="render options",
        ))
        return self

    def set_time(self, sim_time: float) -> "SsfScriptBuilder":
        """Jump to *sim_time* seconds in the simulation."""
        self._commands.append(_SsfCommand(
            "SETTIMEVAL", [f"{sim_time:.4f}"],
            comment=f"t = {sim_time} s",
        ))
        return self

    def step_forward(self, n_steps: int = 1) -> "SsfScriptBuilder":
        """Advance *n_steps* time steps."""
        for _ in range(n_steps):
            self._commands.append(_SsfCommand("STEP_FORWARD"))
        return self

    def set_viewpoint(self, name: str) -> "SsfScriptBuilder":
        """Load a named viewpoint defined in the ``.smv`` file."""
        self._commands.append(_SsfCommand("SETVIEWPOINT", [name]))
        return self

    def set_camera(
        self,
        eye: tuple,
        target: tuple,
        up: tuple = (0.0, 0.0, 1.0),
    ) -> "SsfScriptBuilder":
        """
        Set camera position / target / up-vector explicitly.

        Parameters
        ----------
        eye    : (x, y, z) — camera position
        target : (x, y, z) — look-at point
        up     : (x, y, z) — up direction vector
        """
        args = [
            f"{eye[0]:.4f}",    f"{eye[1]:.4f}",    f"{eye[2]:.4f}",
            f"{target[0]:.4f}", f"{target[1]:.4f}", f"{target[2]:.4f}",
            f"{up[0]:.4f}",     f"{up[1]:.4f}",     f"{up[2]:.4f}",
        ]
        self._commands.append(_SsfCommand("SETCAMERA", args))
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

    def build(self) -> str:
        """Render all commands to a SSF-formatted string."""
        if not self._commands:
            return ""
        lines = []
        for cmd in self._commands:
            lines.append(cmd.render())
        lines.append("")
        return "\n".join(lines)

    def write(self, filepath: str) -> None:
        """Write the script to *filepath*."""
        Path(filepath).write_text(self.build(), encoding="utf-8")

    def __repr__(self) -> str:
        return f"<SsfScriptBuilder commands={len(self._commands)}>"
