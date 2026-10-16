"""Beams, pipes, ramps, doors and windows on ``api.geom`` (plan step F1, Draw menu). A mixin for ``GeomManager``."""
from __future__ import annotations

from typing import Any, Optional, Sequence

from .species import _unique

#: default size of an opening (width, height, height above the floor), metres
_OPENING = {"door": (0.9, 2.1, 0.0), "window": (1.2, 1.2, 0.9)}


class BuildingElements:
    """Mixin for ``GeomManager`` (needs ``_api`` and ``all()``)."""

    def add_beam(self, start: Sequence[float], end: Sequence[float], width: float, depth: float,
                 surf_id: str = "INERT", name: str = "BEAM", color: Optional[str] = None) -> Any:
        """A straight beam, column or lintel between two points along X, Y or Z, as one obstruction. *width* is across
        the beam horizontally (for a vertical column: along X) and *depth* is its other cross-section size; the beam is
        centred on the line between the points. One undo step."""
        if width <= 0 or depth <= 0:
            raise ValueError("width and depth must be greater than 0")
        d = [abs(e - s) for s, e in zip(start, end)]
        axis = [i for i in range(3) if d[i] > 1e-9]
        if len(axis) != 1:
            raise ValueError("a beam must run along X, Y or Z (give two points that differ in exactly one coordinate)")
        a = axis[0]
        lo = [min(s, e) for s, e in zip(start, end)]
        hi = [max(s, e) for s, e in zip(start, end)]
        across = {0: (1, 2), 1: (0, 2), 2: (0, 1)}[a]                       # which axes carry width and depth
        for ax, size in zip(across, (width, depth)):
            lo[ax] = start[ax] - size / 2.0
            hi[ax] = start[ax] + size / 2.0
        xb = [lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]]
        return self._api.obstructions.add_obstruction(xb, surf_id=surf_id, name=_unique(self._api.obstructions, name),
                                                      **({"color": color} if color else {}))

    def add_pipe(self, start: Sequence[float], end: Sequence[float], outer_radius: float, wall: float,
                 surf_id: str = "INERT", name: str = "PIPE", segments: int = 24) -> Any:
        """A hollow pipe (a solid rod when *wall* is at least the radius) in any direction, as one closed ``Geom``."""
        from pyfds.domain.building_elements import pipe_mesh
        from pyfds.domain.model import Geom
        verts, faces = pipe_mesh(start, end, outer_radius, wall, segments)
        return self._add_shape(Geom(name=_unique(self, name), surf_id=surf_id, verts=verts, faces=faces),
                               f"add pipe {name}")

    def add_sloped_ramp(self, origin: Sequence[float], direction: str, length: float, width: float, rise: float,
                        surf_id: str = "INERT", name: str = "RAMP") -> Any:
        """A solid ramp (a wedge) as one closed ``Geom``: its low edge starts at *origin* and it climbs *rise* over
        *length* in *direction* (+X, -X, +Y, -Y); *width* runs to the left of that direction."""
        from pyfds.domain.building_elements import ramp_mesh
        from pyfds.domain.model import Geom
        verts, faces = ramp_mesh(origin, direction, length, width, rise)
        return self._add_shape(Geom(name=_unique(self, name), surf_id=surf_id, verts=verts, faces=faces),
                               f"add ramp {name}")

    def add_opening(self, kind: str, centre: Sequence[float], wall_axis: str = "X", width: Optional[float] = None,
                    height: Optional[float] = None, sill: Optional[float] = None, wall_thickness: float = 0.3,
                    name: Optional[str] = None) -> Any:
        """A door or window: a ``&HOLE`` cut through a wall.

        *centre* is (x, y, z0): the middle of the opening in plan and the floor level it is measured from. *wall_axis*
        is the direction the wall runs (``X`` or ``Y``). Doors default to 0.9 x 2.1 m on the floor, windows to
        1.2 x 1.2 m with the sill 0.9 m up; *wall_thickness* is how deep the cut is (make it a little more than the
        wall). Returns the ``Hole`` (one undo step)."""
        kind = kind.strip().lower()
        if kind not in _OPENING:
            raise ValueError("kind must be 'door' or 'window'")
        w0, h0, s0 = _OPENING[kind]
        w, h, s = (w0 if width is None else width), (h0 if height is None else height), (s0 if sill is None else sill)
        if min(w, h, wall_thickness) <= 0 or s < 0:
            raise ValueError("width, height and wall thickness must be greater than 0 and the sill cannot be negative")
        axis = wall_axis.strip().upper()
        if axis not in ("X", "Y"):
            raise ValueError("wall_axis must be X or Y")
        x, y, z = centre[0], centre[1], (centre[2] if len(centre) > 2 else 0.0)
        if axis == "X":
            xb = [x - w / 2, x + w / 2, y - wall_thickness / 2, y + wall_thickness / 2, z + s, z + s + h]
        else:
            xb = [x - wall_thickness / 2, x + wall_thickness / 2, y - w / 2, y + w / 2, z + s, z + s + h]
        return self._api.holes.add_hole(xb, name=_unique(self._api.holes, name or kind.upper()))

    def _add_shape(self, geom: Any, label: str) -> Any:
        from pyfds.automation.commands import AddEntityCommand
        with self._api.history.transaction(label):
            self._api.history.execute(AddEntityCommand(self._project, geom))
        return geom
