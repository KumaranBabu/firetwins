"""SsfScriptBuilder: colour bars, colour maps, contours, transparency, colours."""
from __future__ import annotations

from typing import TYPE_CHECKING

from typing import Optional

from .scripting_common import _SsfCommand

if TYPE_CHECKING:
    from .scripting import SsfScriptBuilder


class SsfScriptBuilderStyleMixin:
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
