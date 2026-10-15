"""Move / rotate / scale / mirror several objects as one rigid unit: ``api.transform`` (UX-13).

Selecting one member of a group pulls in the whole group; rotate, scale and mirror pivot about the
combined centre of everything transformed (not each object's own centre); the whole operation is ONE
undo step. An object that cannot take the transform (a rotation that is not a multiple of 90 degrees
on a box-shaped object, a surface or material that has no position) is skipped and counted.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

_AXES = {"X": 0, "Y": 1, "Z": 2}


def point_xyz(entity: Any) -> Optional[Tuple[float, float, float]]:
    """Current (x, y, z) of a point-like object, or None. Prefers ``xyz`` (devices) over x/y/z (HVAC nodes)."""
    xyz = getattr(entity, "xyz", None)
    if xyz is not None:
        return (float(xyz[0]), float(xyz[1]), float(xyz[2]))
    if hasattr(entity, "x") and hasattr(entity, "y") and hasattr(entity, "z"):
        return (float(entity.x), float(entity.y), float(entity.z))
    return None


def transform_kind(entity: Any) -> Optional[str]:
    """``"geom"`` | ``"xb"`` | ``"point"`` | None (not transformable: surfaces, materials, ramps ...)."""
    if hasattr(entity, "verts"):
        return "geom"
    if all(hasattr(entity, a) for a in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")):
        return "xb"
    if point_xyz(entity) is not None:
        return "point"
    return None


def selection_bbox(entities: Iterable[Any]) -> Tuple[float, float, float, float, float, float]:
    """Combined bounding box of a multi-object selection: the shared pivot of a group transform."""
    boxes = []
    for e in entities:
        box = e.bbox() if hasattr(e, "bbox") else None
        if box is None:
            p = point_xyz(e)
            if p is not None:
                box = (p[0], p[0], p[1], p[1], p[2], p[2])
        if box is not None:
            boxes.append(box)
    if not boxes:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return (min(b[0] for b in boxes), max(b[1] for b in boxes), min(b[2] for b in boxes),
            max(b[3] for b in boxes), min(b[4] for b in boxes), max(b[5] for b in boxes))


class TransformManager:
    def __init__(self, api) -> None:
        self._api = api

    def expand_groups(self, entities: Iterable[Any]) -> List[Any]:
        """The objects plus every member of any group they belong to (no duplicates, order kept)."""
        out, seen = [], set()
        for e in entities:
            gname = self._api.groups.group_of(e)
            for m in (self._api.groups.members(gname) if gname else [e]):
                if id(m) not in seen:
                    seen.add(id(m))
                    out.append(m)
        return out

    def _apply(self, entities: Iterable[Any], title: str, build: Callable[[str, Any, tuple], Any],
               expand_groups: bool) -> Dict[str, int]:
        from pyfds.automation.commands import GroupCommand
        targets = self.expand_groups(entities) if expand_groups else list(entities)
        bbox = selection_bbox(targets)
        commands, skipped = [], 0
        for e in targets:
            kind = transform_kind(e)
            cmd = None
            if kind is not None:
                try:
                    cmd = build(kind, e, bbox)
                except Exception:
                    cmd = None
            if cmd is None:
                skipped += 1
            else:
                commands.append(cmd)
        if not commands:
            raise ValueError("nothing in the selection can be transformed")
        result = self._api.history.execute(GroupCommand(commands, label=title))
        if result is not None and getattr(result, "success", True) is False:
            raise ValueError(result.message)
        return {"transformed": len(commands), "skipped": skipped}

    def move(self, entities: Iterable[Any], dx: float = 0.0, dy: float = 0.0, dz: float = 0.0,
             expand_groups: bool = True) -> Dict[str, int]:
        from pyfds.automation.commands import MoveObstCommand, TranslateGeomCommand, TranslatePointCommand

        def build(kind, e, bbox):
            cls = {"xb": MoveObstCommand, "geom": TranslateGeomCommand, "point": TranslatePointCommand}[kind]
            return cls(e, dx=dx, dy=dy, dz=dz)
        return self._apply(entities, "Move Selected", build, expand_groups)

    def rotate(self, entities: Iterable[Any], degrees: float, expand_groups: bool = True) -> Dict[str, int]:
        """About Z through the selection's centre. Box-shaped objects accept multiples of 90 only."""
        from pyfds.automation.commands import RotateCommand, RotateGeomCommand, TranslatePointCommand

        def build(kind, e, bbox):
            ox, oy = (bbox[0] + bbox[1]) / 2, (bbox[2] + bbox[3]) / 2
            if kind == "xb":
                return RotateCommand(e, degrees=degrees, origin=(ox, oy))
            if kind == "geom":
                return RotateGeomCommand(e, degrees=degrees, origin=(ox, oy))
            x, y, _z = point_xyz(e)
            rad = math.radians(degrees)
            nx = ox + (x - ox) * math.cos(rad) - (y - oy) * math.sin(rad)
            ny = oy + (x - ox) * math.sin(rad) + (y - oy) * math.cos(rad)
            return TranslatePointCommand(e, dx=nx - x, dy=ny - y, dz=0.0)
        return self._apply(entities, "Rotate Selected", build, expand_groups)

    def scale(self, entities: Iterable[Any], factor: float, expand_groups: bool = True) -> Dict[str, int]:
        """Uniform scale about the selection's centre."""
        from pyfds.automation.commands import ScaleCommand, ScaleGeomCommand, TranslatePointCommand
        if factor <= 0:
            raise ValueError("the scale factor must be positive")

        def build(kind, e, bbox):
            origin = ((bbox[0] + bbox[1]) / 2, (bbox[2] + bbox[3]) / 2, (bbox[4] + bbox[5]) / 2)
            if kind == "xb":
                return ScaleCommand(e, factor=factor, origin=origin)
            if kind == "geom":
                return ScaleGeomCommand(e, factor=factor, origin=origin)
            p = point_xyz(e)
            n = [o + (c - o) * factor for c, o in zip(p, origin)]
            return TranslatePointCommand(e, dx=n[0] - p[0], dy=n[1] - p[1], dz=n[2] - p[2])
        return self._apply(entities, "Scale Selected", build, expand_groups)

    def mirror(self, entities: Iterable[Any], axis: str = "X", expand_groups: bool = True) -> Dict[str, int]:
        """Mirror across the plane through the selection's centre, perpendicular to *axis* (X, Y or Z)."""
        from pyfds.automation.commands import MirrorCommand, MirrorGeomCommand, TranslatePointCommand
        try:
            idx = _AXES[str(axis).upper()]
        except KeyError:
            raise ValueError("axis must be X, Y or Z") from None

        def build(kind, e, bbox):
            position = (bbox[idx * 2] + bbox[idx * 2 + 1]) / 2
            if kind == "xb":
                return MirrorCommand(e, axis=idx, position=position)
            if kind == "geom":
                return MirrorGeomCommand(e, axis=idx, position=position)
            p = point_xyz(e)
            d = [0.0, 0.0, 0.0]
            d[idx] = 2 * position - 2 * p[idx]
            return TranslatePointCommand(e, dx=d[0], dy=d[1], dz=d[2])
        return self._apply(entities, "Mirror Selected", build, expand_groups)
