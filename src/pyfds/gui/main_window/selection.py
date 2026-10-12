"""Entity-shape helpers for Move / Rotate / Scale / Mirror Selected and Group naming (pure functions)."""
from __future__ import annotations

from typing import Any, List, Optional, Tuple


def _point_xyz(entity: Any) -> Optional[Tuple[float, float, float]]:
    """Current (x, y, z) of a point entity, or None if it isn't one.
    Prefers ``xyz`` when present (what Device.add_device() populates and
    what FdsEntity.bbox()'s point-entity branch already reads) over plain
    x/y/z (what HvacNode uses instead)."""
    xyz = getattr(entity, "xyz", None)
    if xyz is not None:
        return (float(xyz[0]), float(xyz[1]), float(xyz[2]))
    if hasattr(entity, "x") and hasattr(entity, "y") and hasattr(entity, "z"):
        return (float(entity.x), float(entity.y), float(entity.z))
    return None


def _transform_kind(entity: Any) -> Optional[str]:
    """"geom" | "xb" | "point" | None (not transformable — Surface,
    Material, Ramp, ...)."""
    if hasattr(entity, "verts"):
        return "geom"
    if all(hasattr(entity, a) for a in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")):
        return "xb"
    if _point_xyz(entity) is not None:
        return "point"
    return None


def _selection_bbox(entities: List[Any]) -> Tuple[float, float, float, float, float, float]:
    """Combined bounding box across a whole multi-entity selection — the
    key correctness point for a *group* transform: rotating/scaling/
    mirroring must pivot the whole selection around ONE shared point, not
    each entity's own centroid independently (which would spin/scale every
    object in place instead of moving as one rigid group)."""
    boxes = []
    for entity in entities:
        box = entity.bbox() if hasattr(entity, "bbox") else None
        if box is None:
            xyz = _point_xyz(entity)
            if xyz is not None:
                x, y, z = xyz
                box = (x, x, y, y, z, z)
        if box is not None:
            boxes.append(box)
    if not boxes:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return (
        min(b[0] for b in boxes), max(b[1] for b in boxes),
        min(b[2] for b in boxes), max(b[3] for b in boxes),
        min(b[4] for b in boxes), max(b[5] for b in boxes),
    )


def _next_group_name(existing: set) -> str:
    n = 1
    while f"Group {n}" in existing:
        n += 1
    return f"Group {n}"
