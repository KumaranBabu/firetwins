"""SsfScriptBuilder: show/hide, clip planes, labels."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .scripting_common import _SsfCommand

if TYPE_CHECKING:
    from .scripting import SsfScriptBuilder


class SsfScriptBuilderShowMixin:
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
