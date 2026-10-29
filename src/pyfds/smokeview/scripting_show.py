"""SsfScriptBuilder: show/hide, clip planes, labels."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .scripting_common import _SsfCommand, _unsupported

if TYPE_CHECKING:
    from .scripting import SsfScriptBuilder

# Smokeview's SETCLIPMODE: 1 clips blockages and data (2 = blockages only, 3 = data only; 0 = off)
_CLIP_BOTH = "1"


class SsfScriptBuilderShowMixin:
    def show_geometry(self, show: bool = True) -> "SsfScriptBuilder":
        """Not available: there is no script command for it (SHOWBLOCKS in an .ini had no effect either)."""
        raise _unsupported("hide or show the geometry", "Use Smokeview's Show/Hide menu, or a clip plane "
                                                        "(set_clip_plane) to cut it away.")

    def show_obstruction(self, obst_id: str, show: bool = True) -> "SsfScriptBuilder":
        """Not available in Smokeview scripts."""
        raise _unsupported("show or hide a single obstruction", "Use a clip plane (set_clip_plane).")

    def show_vent(self, vent_id: str, show: bool = True) -> "SsfScriptBuilder":
        """Not available in Smokeview scripts."""
        raise _unsupported("show or hide a single vent", "Use Smokeview's Show/Hide > Geometry > Vents menu.")

    def show_mesh(self, mesh: int = 1, show: bool = True) -> "SsfScriptBuilder":
        """Not available in Smokeview scripts."""
        raise _unsupported("show or hide a mesh", "Data is loaded on every mesh; use a clip plane to cut it.")

    def show_zone(self, zone_id: str, show: bool = True) -> "SsfScriptBuilder":
        """Not available in Smokeview scripts."""
        raise _unsupported("show or hide a pressure zone", "Use Smokeview's Show/Hide menu.")

    def set_clip_plane(
        self,
        axis: str,
        position: float,
        *,
        clip_min: bool = True,
    ) -> "SsfScriptBuilder":
        """
        Cut the scene (geometry and data) with a plane perpendicular to *axis* at *position*.

        Parameters
        ----------
        axis : str
            ``"X"``, ``"Y"``, or ``"Z"``.
        position : float
            World-space coordinate of the cutting plane.
        clip_min : bool
            True removes everything below *position* (the near side when looking along +axis); False removes
            everything above it.
        """
        axis = axis.upper()
        if axis not in ("X", "Y", "Z"):
            raise ValueError(f"axis must be X, Y or Z, not {axis!r}")
        # SETCLIPx takes: use-min min use-max max (checked against Smokeview 6.10.1)
        bounds = f"1 {position:g} 0 0" if clip_min else f"0 0 1 {position:g}"
        self._commands.append(_SsfCommand("SETCLIPMODE", [_CLIP_BOTH]))
        self._commands.append(_SsfCommand(f"SETCLIP{axis}", [bounds], comment=f"clip {axis} at {position}"))
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
        """Not available: Smokeview's LABEL script keyword names a script step; it draws nothing on the image."""
        raise _unsupported("draw text on the rendered image", "Add the text to the pictures afterwards, or use "
                                                              "PyFDS Results (Tools > Add Label).")
