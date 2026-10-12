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

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Command model
# ---------------------------------------------------------------------------

@dataclass
class _SsfCommand:
    verb: str
    args: List[str] = field(default_factory=list)
    comment: str = ""

    def render(self) -> str:
        """Real SSF layout (checked against Smokeview 6): the keyword on one line, then each argument line
        on its own line below it. ``comment`` is kept for readers of the builder but not written, because
        Smokeview would take a trailing comment as part of the argument."""
        return "\n".join([self.verb] + [f" {a}" for a in self.args])


# ---------------------------------------------------------------------------
# SsfScriptBuilder
# ---------------------------------------------------------------------------

class SsfScriptBuilder:
    """
    Builds a Smokeview Script File (SSF) incrementally.

    All methods return ``self`` for optional chaining.
    """

    def __init__(self) -> None:
        self._commands: List[_SsfCommand] = []
        self._render_width  = 800
        self._render_height = 600
        self._image_format  = "png"

    # ── Render configuration ──────────────────────────────────────────────────

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

    # ── Time navigation ───────────────────────────────────────────────────────

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

    # ── Camera / viewpoint ────────────────────────────────────────────────────

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

    # ── Object loading ────────────────────────────────────────────────────────

    def unload_all(self) -> "SsfScriptBuilder":
        """Deactivate all currently-loaded visualization objects."""
        self._commands.append(_SsfCommand("UNLOADALL"))
        return self

    def load_slice(
        self,
        quantity: str,
        mesh: int = 1,
        index: int = 1,
        axis: int = 2,
        position: float = 0.0,
    ) -> "SsfScriptBuilder":
        """
        Load the slice of *quantity* on the plane ``axis`` (1=x, 2=y, 3=z) at coordinate *position* (metres).
        (*mesh* and *index* are kept for old callers and not used by Smokeview's script.)

        Parameters
        ----------
        quantity : str
            FDS quantity string e.g. ``"TEMPERATURE"``.
        mesh : int
            1-based mesh index.
        index : int
            nth occurrence of this quantity for this mesh.
        """
        if axis not in (1, 2, 3):
            raise ValueError("axis must be 1 (x), 2 (y) or 3 (z)")
        self._commands.append(_SsfCommand(
            "LOADSLICE", [quantity, f"{axis} {position:g}"],
            comment=f"slice {quantity!r} mesh {mesh}",
        ))
        return self

    def load_boundary(self, quantity: Optional[str] = None, mesh: int = 1) -> "SsfScriptBuilder":
        """Activate a boundary quantity visualization."""
        args = [str(mesh), "1"]
        if quantity:
            args.append(quantity)
        self._commands.append(_SsfCommand(
            "LOADBOUNDARY", args,
            comment=f"boundary {quantity!r} mesh {mesh}",
        ))
        return self

    def load_isosurface(self, quantity: str, mesh: int = 1) -> "SsfScriptBuilder":
        """Activate an isosurface visualization."""
        self._commands.append(_SsfCommand(
            "LOADISOSURFACE", [str(mesh), "1", quantity],
            comment=f"isosurface {quantity!r} mesh {mesh}",
        ))
        return self

    def load_smoke3d(self, quantity: str, mesh: int = 1) -> "SsfScriptBuilder":
        """Activate a 3-D smoke/fire visualization."""
        self._commands.append(_SsfCommand(
            "LOADSMOKE3D", [str(mesh), "1", quantity],
        ))
        return self

    def load_particle(self, mesh: int = 1, index: int = 1) -> "SsfScriptBuilder":
        """Activate particle visualization for *mesh*."""
        self._commands.append(_SsfCommand(
            "LOADPARTICLE", [str(mesh), str(index)],
            comment=f"particles mesh {mesh}",
        ))
        return self

    def load_plot3d(self, quantity: str, mesh: int = 1,
                    index: int = 1) -> "SsfScriptBuilder":
        """Activate a Plot3D quantity visualization."""
        self._commands.append(_SsfCommand(
            "LOADPLOT3D", [str(mesh), str(index), quantity],
            comment=f"plot3d {quantity!r} mesh {mesh}",
        ))
        return self

    def load_vector(self, quantity: str = "VELOCITY",
                    mesh: int = 1) -> "SsfScriptBuilder":
        """Activate a vector-field visualization."""
        self._commands.append(_SsfCommand(
            "LOADVECTOR", [str(mesh), "1", quantity],
            comment=f"vector {quantity!r} mesh {mesh}",
        ))
        return self

    def show_geometry(self, show: bool = True) -> "SsfScriptBuilder":
        """Toggle solid geometry (obstructions) visibility."""
        state = "1" if show else "0"
        self._commands.append(_SsfCommand("SHOWGEOM", [state]))
        return self

    def show_obstruction(self, obst_id: str,
                         show: bool = True) -> "SsfScriptBuilder":
        """Show or hide a named obstruction."""
        self._commands.append(_SsfCommand(
            "SHOWOBST", [obst_id, "1" if show else "0"],
        ))
        return self

    def show_vent(self, vent_id: str, show: bool = True) -> "SsfScriptBuilder":
        """Show or hide a named vent."""
        self._commands.append(_SsfCommand(
            "SHOWVENT", [vent_id, "1" if show else "0"],
        ))
        return self

    def show_mesh(self, mesh: int = 1, show: bool = True) -> "SsfScriptBuilder":
        """Show or hide a mesh boundary."""
        self._commands.append(_SsfCommand(
            "SHOWMESH", [str(mesh), "1" if show else "0"],
        ))
        return self

    def show_zone(self, zone_id: str, show: bool = True) -> "SsfScriptBuilder":
        """Show or hide a pressure zone."""
        self._commands.append(_SsfCommand(
            "SHOWZONE", [zone_id, "1" if show else "0"],
        ))
        return self

    # ── Time / frame navigation ───────────────────────────────────────────────

    def set_frame(self, frame: int) -> "SsfScriptBuilder":
        """Jump to a specific output frame number (0-based)."""
        self._commands.append(_SsfCommand(
            "SETFRAME", [str(frame)],
            comment=f"frame {frame}",
        ))
        return self

    # ── Colour scale ──────────────────────────────────────────────────────────

    def set_colorbar_range(
        self,
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
        *,
        auto: bool = False,
    ) -> "SsfScriptBuilder":
        """Set the colour-scale range for the active visualization."""
        if auto:
            self._commands.append(_SsfCommand("SETCOLORBARAUTO"))
        else:
            self._commands.append(_SsfCommand(
                "SETCOLORBARRANGE", [f"{vmin:.6g}", f"{vmax:.6g}"],
            ))
        return self

    def set_colormap(self, colormap: str) -> "SsfScriptBuilder":
        """
        Set the colormap for the currently active visualization.

        Parameters
        ----------
        colormap : str
            Smokeview colormap name: ``"rainbow"``, ``"greyscale"``,
            ``"hsv"``, ``"fire"``, ``"cool"``, ``"jet"``, etc.
        """
        self._commands.append(_SsfCommand("SETCOLORMAP", [colormap]))
        return self

    def set_contour_type(self, contour_type: str = "SLICE") -> "SsfScriptBuilder":
        """
        Set how contours are drawn.

        Parameters
        ----------
        contour_type : str
            ``"SLICE"`` (flat), ``"SMOOTH"`` (interpolated), or ``"SOLID"``.
        """
        self._commands.append(_SsfCommand("SETCONTOURTYPE", [contour_type.upper()]))
        return self

    def set_contour_levels(self, n: int) -> "SsfScriptBuilder":
        """Set the number of contour levels for the active colorbar."""
        self._commands.append(_SsfCommand("SETCONTOURLEVELS", [str(n)]))
        return self

    def set_transparency(self, surface_id: str,
                         value: float) -> "SsfScriptBuilder":
        """
        Set the transparency of a named surface/obstruction.

        Parameters
        ----------
        surface_id : str
            FDS surface ID.
        value : float
            0.0 = opaque, 1.0 = fully transparent.
        """
        self._commands.append(_SsfCommand(
            "SETTRANSPARENCY", [surface_id, f"{value:.4f}"],
        ))
        return self

    def set_background_color(
        self, r: int, g: int, b: int
    ) -> "SsfScriptBuilder":
        """Set the scene background colour (RGB 0–255)."""
        self._commands.append(_SsfCommand(
            "SETBACKGROUNDCOLOR", [str(r), str(g), str(b)],
        ))
        return self

    def set_foreground_color(
        self, r: int, g: int, b: int
    ) -> "SsfScriptBuilder":
        """Set the scene foreground (text/axes) colour (RGB 0–255)."""
        self._commands.append(_SsfCommand(
            "SETFOREGROUNDCOLOR", [str(r), str(g), str(b)],
        ))
        return self

    def set_clip_plane(
        self,
        axis: str,
        position: float,
        *,
        clip_min: bool = True,
    ) -> "SsfScriptBuilder":
        """
        Set a clipping plane perpendicular to *axis* at *position*.

        Parameters
        ----------
        axis : str
            ``"X"``, ``"Y"``, or ``"Z"``.
        position : float
            World-space coordinate of the cutting plane.
        clip_min : bool
            If True, clip the negative side; if False, clip the positive side.
        """
        side = "MIN" if clip_min else "MAX"
        self._commands.append(_SsfCommand(
            "CLIP", [axis.upper(), f"{position:.6g}", side],
        ))
        return self

    # ── Labels ────────────────────────────────────────────────────────────────

    def add_label(
        self,
        text: str,
        x: float = 0.05,
        y: float = 0.95,
        *,
        size: int = 14,
        color: str = "white",
    ) -> "SsfScriptBuilder":
        """
        Add a text overlay label at normalised screen coordinates.

        Parameters
        ----------
        text : str
        x, y : float
            Normalised screen position (0–1).
        size : int
            Font size.
        color : str
            ``"white"``, ``"black"``, ``"red"``, etc.
        """
        self._commands.append(_SsfCommand(
            "LABEL", [f"{x:.3f}", f"{y:.3f}", str(size), color, f'"{text}"'],
        ))
        return self

    # ── Capture ───────────────────────────────────────────────────────────────

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

    # ── Utility ───────────────────────────────────────────────────────────────

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

    # ── Output ────────────────────────────────────────────────────────────────

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
