"""SsfScriptBuilder: colour bars, colour maps, contours, transparency, colours."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .scripting_common import _SsfCommand, _unsupported

if TYPE_CHECKING:
    from .scripting import SsfScriptBuilder

# common names -> Smokeview's own colour bar names (each checked against Smokeview 6.10.1's SETCBAR)
_COLORBARS = {"rainbow": "Rainbow", "greyscale": "black->white", "grayscale": "black->white",
              "black->white": "black->white", "fire": "fire", "cool": "cool"}


class SsfScriptBuilderStyleMixin:
    def set_colorbar_range(
        self,
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
        *,
        auto: bool = False,
    ) -> "SsfScriptBuilder":
        """Not available: Smokeview 6.10.1's SETSLICEBOUNDS either has no effect or sets the bounds to 0,
        whatever argument order is used."""
        raise _unsupported("set a colour bar range", "Set the bounds in Smokeview (Dialogs > Data Bounds), or in "
                                                     "PyFDS Results (Preferences > Colorbar).")

    def set_colormap(self, colormap: str) -> "SsfScriptBuilder":
        """
        Use Smokeview colour bar *colormap* for the data shown.

        Parameters
        ----------
        colormap : str
            ``"rainbow"``, ``"greyscale"``, ``"fire"`` or ``"cool"``; any other text is passed to Smokeview as a
            colour bar name (as listed in its Colorbar dialog, e.g. ``"blue->red split"``).
        """
        self._commands.append(_SsfCommand("SETCBAR", [_COLORBARS.get(colormap.lower(), colormap)]))
        return self

    def set_contour_type(self, contour_type: str = "SLICE") -> "SsfScriptBuilder":
        """Not available in Smokeview scripts."""
        raise _unsupported("change how contours are drawn", "Use Smokeview's Dialogs > Display menu.")

    def set_contour_levels(self, n: int) -> "SsfScriptBuilder":
        """Not available in Smokeview scripts."""
        raise _unsupported("change the number of colour bar levels", "Use Smokeview's Colorbar dialog.")

    def set_transparency(self, surface_id: str, value: float) -> "SsfScriptBuilder":
        """Not available in Smokeview scripts."""
        raise _unsupported("make a surface transparent", "Set the surface's TRANSPARENCY on its &SURF line.")

    def set_background_color(self, r: int, g: int, b: int) -> "SsfScriptBuilder":
        """Not available: there is no script command, and the .ini colours swap roles with Smokeview's
        white/black background setting."""
        raise _unsupported("set the background colour", "Use Smokeview's Dialogs > Display > Colors.")

    def set_foreground_color(self, r: int, g: int, b: int) -> "SsfScriptBuilder":
        """Not available (see :meth:`set_background_color`)."""
        raise _unsupported("set the foreground colour", "Use Smokeview's Dialogs > Display > Colors.")
