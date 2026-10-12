"""Rotate commands."""
from __future__ import annotations

from typing import Any, Optional

from .base import Command, CommandResult

from .transform_common import _verts_centroid


class RotateCommand(Command):
    """
    Rotate an XB entity in the XY plane by 90, 180, or 270 degrees.

    The Z coordinates are unchanged.  The bounding box is re-computed so
    it remains axis-aligned after rotation (the XY extent may swap).

    Parameters
    ----------
    entity : Obstruction | Mesh | Vent | …
        Any entity with XB-style coordinate attributes.
    degrees : float
        Rotation angle — must be a multiple of 90 (90, 180, or 270).
    origin : (x, y), optional
        XY pivot point.  Defaults to the entity's XY centroid.
    """

    def __init__(
        self,
        entity: Any,
        degrees: float,
        origin: Optional[tuple] = None,
    ) -> None:
        if degrees % 90 != 0:
            raise ValueError(f"degrees must be a multiple of 90, got {degrees!r}")
        self._entity = entity
        self._degrees = float(degrees) % 360
        self._old_bounds = (
            entity.x_min, entity.x_max,
            entity.y_min, entity.y_max,
            entity.z_min, entity.z_max,
        )
        if origin is None:
            cx = (entity.x_min + entity.x_max) * 0.5
            cy = (entity.y_min + entity.y_max) * 0.5
            self._origin = (cx, cy)
        else:
            self._origin = (float(origin[0]), float(origin[1]))
        self.description = (
            f"rotate {type(entity).__name__} '{getattr(entity, 'name', '?')}' "
            f"{self._degrees}°"
        )

    @staticmethod
    def _rotate_point(px: float, py: float, ox: float, oy: float, deg: float):
        import math
        rad = math.radians(deg)
        cos_r = round(math.cos(rad))
        sin_r = round(math.sin(rad))
        dx, dy = px - ox, py - oy
        return ox + dx * cos_r - dy * sin_r, oy + dx * sin_r + dy * cos_r

    def _apply(self, bounds: tuple) -> None:
        x0, x1, y0, y1, z0, z1 = bounds
        ox, oy = self._origin
        deg = self._degrees
        corners = [
            self._rotate_point(x0, y0, ox, oy, deg),
            self._rotate_point(x1, y0, ox, oy, deg),
            self._rotate_point(x0, y1, ox, oy, deg),
            self._rotate_point(x1, y1, ox, oy, deg),
        ]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        e = self._entity
        e.x_min = min(xs); e.x_max = max(xs)
        e.y_min = min(ys); e.y_max = max(ys)
        e.z_min = z0;       e.z_max = z1

    def execute(self) -> "CommandResult":
        try:
            self._apply(self._old_bounds)
            return CommandResult.ok(self.description)
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> "CommandResult":
        try:
            x0, x1, y0, y1, z0, z1 = self._old_bounds
            e = self._entity
            e.x_min = x0; e.x_max = x1
            e.y_min = y0; e.y_max = y1
            e.z_min = z0; e.z_max = z1
            return CommandResult.ok(f"Undone: {self.description}")
        except Exception as exc:
            return CommandResult.fail(str(exc))


class RotateGeomCommand(Command):
    """Rotate every vertex of a Geom mesh about the Z axis by an arbitrary
    angle in degrees (unlike the XB ``RotateCommand``, a mesh has no
    axis-alignment to preserve, so this isn't restricted to multiples of
    90), around an XY pivot defaulting to the mesh's own XY centroid."""
    def __init__(self, geom: Any, degrees: float, origin: Optional[tuple] = None) -> None:
        self._geom = geom
        self._degrees = float(degrees)
        self._old_verts = list(geom.verts) if geom.verts else []
        if origin is None:
            cx, cy, _ = _verts_centroid(self._old_verts)
            origin = (cx, cy)
        self._origin = (float(origin[0]), float(origin[1]))
        self.description = f"rotate Geom '{getattr(geom, 'name', '?')}' {self._degrees}° about Z"

    def execute(self) -> CommandResult:
        try:
            import math
            ox, oy = self._origin
            rad = math.radians(self._degrees)
            cos_r, sin_r = math.cos(rad), math.sin(rad)
            new_verts = []
            for x, y, z in self._old_verts:
                dx, dy = x - ox, y - oy
                new_verts.append((ox + dx * cos_r - dy * sin_r, oy + dx * sin_r + dy * cos_r, z))
            self._geom.verts = new_verts
            return CommandResult.ok(self.description)
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            self._geom.verts = list(self._old_verts)
            return CommandResult.ok(f"Undone: {self.description}")
        except Exception as exc:
            return CommandResult.fail(str(exc))
