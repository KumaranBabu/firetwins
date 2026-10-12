"""Geometric transforms (move, scale, mirror, rotate) for obstructions, meshes, geoms and points."""
from __future__ import annotations

from typing import Any

from .base import Command, CommandResult

from .transform_scale_mirror import (  # noqa: F401  (re-exported)
    MirrorCommand,
    MirrorGeomCommand,
    ScaleCommand,
    ScaleGeomCommand,
)
from .transform_rotate import (  # noqa: F401  (re-exported)
    RotateCommand,
    RotateGeomCommand,
)
from .transform_common import (  # noqa: F401  (re-exported)
    _verts_centroid,
)

from .transform_scale_mirror import (  # noqa: F401  (re-exported)
    MirrorCommand,
    MirrorGeomCommand,
    ScaleCommand,
    ScaleGeomCommand,
)
from .transform_rotate import (  # noqa: F401  (re-exported)
    RotateCommand,
    RotateGeomCommand,
)
from .transform_common import (  # noqa: F401  (re-exported)
    _verts_centroid,
)


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
