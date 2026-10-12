"""Geometric transforms (move, scale, mirror, rotate) for obstructions, meshes, geoms and points."""
from __future__ import annotations

from typing import Any, Optional

from .base import Command, CommandResult


class MoveObstCommand(Command):
    """
    Translate an Obstruction by (dx, dy, dz) offsets applied to its coordinate bounds.

    Works with the Obstruction domain model which stores bounds as
    x_min/x_max/y_min/y_max/z_min/z_max attributes.
    """
    def __init__(self, obst: Any, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        self._obst = obst
        self._dx, self._dy, self._dz = dx, dy, dz
        self._old_coords = (
            obst.x_min, obst.x_max, obst.y_min, obst.y_max, obst.z_min, obst.z_max
        )
        self.description = (f"move Obstruction '{getattr(obst, 'name', '?')}' "
                            f"by ({dx},{dy},{dz})")

    def execute(self) -> CommandResult:
        try:
            self._obst.x_min += self._dx; self._obst.x_max += self._dx
            self._obst.y_min += self._dy; self._obst.y_max += self._dy
            self._obst.z_min += self._dz; self._obst.z_max += self._dz
            return CommandResult.ok(self.description)
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            x0, x1, y0, y1, z0, z1 = self._old_coords
            self._obst.x_min = x0; self._obst.x_max = x1
            self._obst.y_min = y0; self._obst.y_max = y1
            self._obst.z_min = z0; self._obst.z_max = z1
            return CommandResult.ok(f"Undone: {self.description}")
        except Exception as exc:
            return CommandResult.fail(str(exc))


class MoveHvacNodeCommand(Command):
    """
    Translate an HvacNode by (dx, dy) — used by the HVAC Network Editor's
    drag-to-reposition, where x/y double as 2D schematic-canvas coordinates.
    """
    def __init__(self, node: Any, dx: float = 0.0, dy: float = 0.0) -> None:
        self._node = node
        self._dx, self._dy = dx, dy
        self._old_xy = (node.x, node.y)
        self.description = f"move HvacNode '{getattr(node, 'name', '?')}' by ({dx},{dy})"

    def execute(self) -> CommandResult:
        try:
            self._node.x += self._dx
            self._node.y += self._dy
            return CommandResult.ok(self.description)
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            self._node.x, self._node.y = self._old_xy
            return CommandResult.ok(f"Undone: {self.description}")
        except Exception as exc:
            return CommandResult.fail(str(exc))


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


class TranslateGeomCommand(Command):
    """
    Translate every vertex of a Geom mesh by (dx, dy, dz).

    XB-box entities have ``MoveObstCommand`` for this; a Geom's extent
    lives in its vertex cloud (``verts``) instead of x_min/x_max-style
    bounds, so it needs its own command.
    """
    def __init__(self, geom: Any, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        self._geom = geom
        self._dx, self._dy, self._dz = dx, dy, dz
        self._old_verts = list(geom.verts) if geom.verts else []
        self.description = f"translate Geom '{getattr(geom, 'name', '?')}' by ({dx},{dy},{dz})"

    def execute(self) -> CommandResult:
        try:
            dx, dy, dz = self._dx, self._dy, self._dz
            self._geom.verts = [(x + dx, y + dy, z + dz) for x, y, z in self._old_verts]
            return CommandResult.ok(self.description)
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            self._geom.verts = list(self._old_verts)
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


class TranslatePointCommand(Command):
    """Translate a point entity (Device, HvacNode, ...) by (dx, dy, dz).
    Rotate/Scale/Mirror of a point entity only ever relocates it (zero
    size), so callers compute the rotated/scaled/mirrored delta and reuse
    this one command rather than three more command classes.

    Updates *both* representations a point entity might carry its
    position in — plain ``x``/``y``/``z`` attributes (what ``HvacNode``
    uses, and what the FDS writer reads for some namelists) and an
    ``xyz`` tuple field (what ``Device.add_device()`` populates instead,
    and what the base ``FdsEntity.bbox()`` reads) — whichever are present,
    so the move takes effect regardless of which one a given entity type's
    writer/consumer ultimately looks at."""
    def __init__(self, entity: Any, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        self._entity = entity
        self._dx, self._dy, self._dz = dx, dy, dz
        self._old_x = getattr(entity, "x", None)
        self._old_y = getattr(entity, "y", None)
        self._old_z = getattr(entity, "z", None)
        self._old_xyz = getattr(entity, "xyz", None)
        self.description = (f"translate {type(entity).__name__} "
                            f"'{getattr(entity, 'name', '?')}' by ({dx},{dy},{dz})")

    def _shift(self, dx: float, dy: float, dz: float) -> None:
        e = self._entity
        if self._old_x is not None:
            e.x = self._old_x + dx
        if self._old_y is not None:
            e.y = self._old_y + dy
        if self._old_z is not None:
            e.z = self._old_z + dz
        if self._old_xyz is not None:
            ox, oy, oz = self._old_xyz
            e.xyz = (ox + dx, oy + dy, oz + dz)

    def execute(self) -> CommandResult:
        try:
            self._shift(self._dx, self._dy, self._dz)
            return CommandResult.ok(self.description)
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            e = self._entity
            if self._old_x is not None:
                e.x = self._old_x
            if self._old_y is not None:
                e.y = self._old_y
            if self._old_z is not None:
                e.z = self._old_z
            if self._old_xyz is not None:
                e.xyz = self._old_xyz
            return CommandResult.ok(f"Undone: {self.description}")
        except Exception as exc:
            return CommandResult.fail(str(exc))


def _verts_centroid(verts: list) -> tuple:
    """Bbox centroid of a vertex list — shared default-origin helper for
    the Geom transform commands above. (0, 0, 0) for an empty mesh."""
    if not verts:
        return (0.0, 0.0, 0.0)
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
