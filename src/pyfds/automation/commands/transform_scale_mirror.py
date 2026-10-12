"""Scale and mirror commands."""
from __future__ import annotations

from typing import Any, Optional

from .base import Command, CommandResult

from .transform_common import _verts_centroid


class ScaleCommand(Command):
    """
    Scale the XB bounds of an Obstruction or Mesh by a uniform factor,
    optionally anchored to a specific origin point.

    Parameters
    ----------
    entity : Obstruction or Mesh
        Entity with x_min/x_max/y_min/y_max/z_min/z_max attributes.
    factor : float
        Uniform scale factor.
    origin : (x, y, z), optional
        Anchor point for the scale operation. Defaults to the entity's centroid.
    """
    def __init__(self, entity: Any, factor: float,
                 origin: Optional[tuple] = None) -> None:
        self._entity = entity
        self._factor = factor
        self._old_bounds = (
            entity.x_min, entity.x_max,
            entity.y_min, entity.y_max,
            entity.z_min, entity.z_max,
        )
        if origin is None:
            cx = (entity.x_min + entity.x_max) * 0.5
            cy = (entity.y_min + entity.y_max) * 0.5
            cz = (entity.z_min + entity.z_max) * 0.5
            self._origin = (cx, cy, cz)
        else:
            self._origin = origin
        self.description = (
            f"scale {type(entity).__name__} '{getattr(entity, 'name', '?')}' "
            f"× {factor}"
        )

    def execute(self) -> CommandResult:
        try:
            ox, oy, oz = self._origin
            f = self._factor
            e = self._entity
            e.x_min = ox + (e.x_min - ox) * f
            e.x_max = ox + (e.x_max - ox) * f
            e.y_min = oy + (e.y_min - oy) * f
            e.y_max = oy + (e.y_max - oy) * f
            e.z_min = oz + (e.z_min - oz) * f
            e.z_max = oz + (e.z_max - oz) * f
            return CommandResult.ok(self.description)
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            x0, x1, y0, y1, z0, z1 = self._old_bounds
            e = self._entity
            e.x_min = x0; e.x_max = x1
            e.y_min = y0; e.y_max = y1
            e.z_min = z0; e.z_max = z1
            return CommandResult.ok(f"Undone: {self.description}")
        except Exception as exc:
            return CommandResult.fail(str(exc))


class MirrorCommand(Command):
    """
    Mirror an XB entity across an axis-aligned plane.

    Parameters
    ----------
    entity : Obstruction | Mesh | Vent | …
        Any entity with ``x_min/x_max/y_min/y_max/z_min/z_max`` attributes.
    axis : int
        Plane normal axis: ``0`` → YZ plane (mirror in X), ``1`` → XZ (Y),
        ``2`` → XY (Z).
    position : float, optional
        Coordinate of the mirror plane along *axis*.  Defaults to the entity's
        centroid in that axis.
    """

    def __init__(self, entity: Any, axis: int, position: Optional[float] = None) -> None:
        if axis not in (0, 1, 2):
            raise ValueError(f"axis must be 0, 1, or 2, got {axis!r}")
        self._entity = entity
        self._axis = axis
        self._old_bounds = (
            entity.x_min, entity.x_max,
            entity.y_min, entity.y_max,
            entity.z_min, entity.z_max,
        )
        pairs = [
            (entity.x_min, entity.x_max),
            (entity.y_min, entity.y_max),
            (entity.z_min, entity.z_max),
        ]
        lo, hi = pairs[axis]
        self._position = position if position is not None else (lo + hi) * 0.5
        self.description = (
            f"mirror {type(entity).__name__} '{getattr(entity, 'name', '?')}' "
            f"axis={axis} pos={self._position}"
        )

    def _apply(self, bounds: tuple) -> None:
        x0, x1, y0, y1, z0, z1 = bounds
        p = self._position
        e = self._entity
        if self._axis == 0:
            e.x_min = 2 * p - x1
            e.x_max = 2 * p - x0
            e.y_min = y0; e.y_max = y1
            e.z_min = z0; e.z_max = z1
        elif self._axis == 1:
            e.x_min = x0; e.x_max = x1
            e.y_min = 2 * p - y1
            e.y_max = 2 * p - y0
            e.z_min = z0; e.z_max = z1
        else:
            e.x_min = x0; e.x_max = x1
            e.y_min = y0; e.y_max = y1
            e.z_min = 2 * p - z1
            e.z_max = 2 * p - z0

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


class ScaleGeomCommand(Command):
    """Scale every vertex of a Geom mesh by a uniform factor about *origin*
    (defaults to the mesh's own bbox centroid)."""
    def __init__(self, geom: Any, factor: float, origin: Optional[tuple] = None) -> None:
        self._geom = geom
        self._factor = factor
        self._old_verts = list(geom.verts) if geom.verts else []
        if origin is None:
            origin = _verts_centroid(self._old_verts)
        self._origin = origin
        self.description = f"scale Geom '{getattr(geom, 'name', '?')}' × {factor}"

    def execute(self) -> CommandResult:
        try:
            ox, oy, oz = self._origin
            f = self._factor
            self._geom.verts = [
                (ox + (x - ox) * f, oy + (y - oy) * f, oz + (z - oz) * f)
                for x, y, z in self._old_verts
            ]
            return CommandResult.ok(self.description)
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            self._geom.verts = list(self._old_verts)
            return CommandResult.ok(f"Undone: {self.description}")
        except Exception as exc:
            return CommandResult.fail(str(exc))


class MirrorGeomCommand(Command):
    """Mirror every vertex of a Geom mesh across an axis-aligned plane
    (axis: 0=X, 1=Y, 2=Z; position defaults to the mesh's own centroid on
    that axis). Also reverses each face's winding order, since a
    reflection flips handedness — without this, normals (and FDS's
    inside/outside solid test) would point the wrong way after mirroring."""
    def __init__(self, geom: Any, axis: int, position: Optional[float] = None) -> None:
        if axis not in (0, 1, 2):
            raise ValueError(f"axis must be 0, 1, or 2, got {axis!r}")
        self._geom = geom
        self._axis = axis
        self._old_verts = list(geom.verts) if geom.verts else []
        self._old_faces = list(geom.faces) if geom.faces else []
        if position is None:
            centroid = _verts_centroid(self._old_verts)
            position = centroid[axis]
        self._position = position
        self.description = f"mirror Geom '{getattr(geom, 'name', '?')}' axis={axis} pos={position}"

    def execute(self) -> CommandResult:
        try:
            p, axis = self._position, self._axis
            new_verts = []
            for v in self._old_verts:
                v = list(v)
                v[axis] = 2 * p - v[axis]
                new_verts.append(tuple(v))
            self._geom.verts = new_verts
            self._geom.faces = [(f[0], f[2], f[1]) for f in self._old_faces]
            return CommandResult.ok(self.description)
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            self._geom.verts = list(self._old_verts)
            self._geom.faces = list(self._old_faces)
            return CommandResult.ok(f"Undone: {self.description}")
        except Exception as exc:
            return CommandResult.fail(str(exc))
