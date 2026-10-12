"""Building generators, boolean operations and block conversion on ``api.geom`` (B2).

A mixin for ``GeomManager``. Every generator turns a few parameters into ``&OBST`` boxes
(see :mod:`pyfds.domain.building_shapes`) inside one history transaction, so one Ctrl+Z
removes a whole wall/room/roof.
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence

from pyfds.domain import building_shapes as shapes

from .species import _unique


class BuildingGenerators:
    """Mixin for ``GeomManager`` (needs ``_api``, ``_project``, ``all()``)."""

    # -- helpers ---------------------------------------------------------------------
    def _resolution(self, res: Optional[float]) -> float:
        """Stair-step pitch: explicit, else the smallest cell of the first mesh, else 0.1 m."""
        if res is not None:
            if res <= 0:
                raise ValueError("res must be positive")
            return float(res)
        meshes = self._project.meshes
        if meshes:
            m = meshes[0]
            return min((m.x_max - m.x_min) / m.cell_count[0], (m.y_max - m.y_min) / m.cell_count[1],
                       (m.z_max - m.z_min) / m.cell_count[2])
        return 0.1

    def _add_boxes(self, boxes: Sequence[Sequence[float]], prefix: str, surf_id: str,
                   color: Optional[str], label: str, extra_boxes=()) -> List[Any]:
        """Add one obstruction per box, plus *extra_boxes* given as (name, box, surf_id)."""
        if not boxes and not extra_boxes:
            raise ValueError(f"{label}: nothing was generated (too thin for the resolution?)")
        out: List[Any] = []
        with self._api.history.transaction(label):
            for k, b in enumerate(boxes, 1):
                out.append(self._api.obstructions.add_obstruction(
                    list(b), surf_id=surf_id, name=_unique(self._api.obstructions, f"{prefix}_{k}"),
                    **({"color": color} if color else {})))
            for name, b, sid in extra_boxes:
                out.append(self._api.obstructions.add_obstruction(
                    list(b), surf_id=sid, name=_unique(self._api.obstructions, f"{prefix}_{name}"),
                    **({"color": color} if color else {})))
        return out

    # -- walls, slabs, rooms (GEO-01, GEO-05, GEO-06) ---------------------------------
    def add_wall(self, path: Sequence[Sequence[float]], thickness: float, height: float, z: float = 0.0,
                 align: str = "C", surf_id: str = "INERT", name: str = "WALL",
                 res: Optional[float] = None, closed: bool = False, color: Optional[str] = None) -> List[Any]:
        """Wall along a polyline. *align* L/C/R = thickness left of / centred on / right of the
        walking direction. Straight runs are exact boxes; diagonal runs are stair-stepped."""
        boxes = shapes.wall([tuple(p[:2]) for p in path], thickness, z, height, align,
                            self._resolution(res), closed)
        return self._add_boxes(boxes, name, surf_id, color, f"add wall {name}")

    def add_curved_wall(self, center: Sequence[float], radius: float, start_deg: float, end_deg: float,
                        thickness: float, height: float, z: float = 0.0, align: str = "C",
                        surf_id: str = "INERT", name: str = "ARC_WALL", res: Optional[float] = None,
                        color: Optional[str] = None) -> List[Any]:
        """Wall along an arc (degrees, counter-clockwise from +X; a 360 degree sweep is a ring)."""
        boxes = shapes.curved_wall(tuple(center[:2]), radius, start_deg, end_deg, thickness, z, height,
                                   align, self._resolution(res))
        return self._add_boxes(boxes, name, surf_id, color, f"add curved wall {name}")

    def add_slab(self, polygon: Sequence[Sequence[float]], z_top: float, thickness: float,
                 surf_id: str = "INERT", name: str = "SLAB", res: Optional[float] = None,
                 color: Optional[str] = None) -> List[Any]:
        """Floor/ceiling slab: a polygon (x, y points) extruded down from *z_top*."""
        boxes = shapes.slab([tuple(p[:2]) for p in polygon], z_top, thickness, self._resolution(res))
        return self._add_boxes(boxes, name, surf_id, color, f"add slab {name}")

    def add_room(self, xb: Sequence[float], height: float, wall_thickness: float = 0.2,
                 z: float = 0.0, position: str = "inside", floor_thickness: float = 0.0,
                 ceiling_thickness: float = 0.0, surf_id: str = "INERT", name: str = "ROOM",
                 openings: Optional[List[dict]] = None, color: Optional[str] = None) -> dict:
        """Four walls round the rectangle ``xb = [x0, x1, y0, y1]`` (extra values ignored), with an
        optional floor and ceiling and doors/windows.

        *openings*: dicts ``{"side": "S"|"E"|"N"|"W", "centre": m along that wall, "width": m,
        "height": m, "sill": m above the room floor (default 0)}``, each cut as a ``&HOLE``.
        Returns ``{"walls": [...], "holes": [...], "interior": [x0, x1, y0, y1, z0, z1]}``."""
        parts, interior = shapes.room(xb[0], xb[1], xb[2], xb[3], z, height, wall_thickness, position,
                                      floor_thickness, ceiling_thickness)
        holes_xb = [shapes.opening_box(parts, o["side"], o["centre"], o["width"], o["height"],
                                       o.get("sill", 0.0), z) for o in (openings or [])]
        with self._api.history.transaction(f"add room {name}"):
            walls = self._add_boxes([], name, surf_id, color, "", extra_boxes=[(p, b, surf_id) for p, b in parts])
            holes = [self._api.holes.add_hole(list(b), name=_unique(self._api.holes, f"{name}_OPENING"))
                     for b in holes_xb]
        return {"walls": walls, "holes": holes, "interior": list(interior)}

    # -- stairs, roofs, trusses (GEO-07, GEO-08, GEO-09) ------------------------------
    def add_stairs(self, x: float, y: float, z: float, direction: str, width: float, steps: int,
                   riser: float = 0.18, tread: float = 0.28, landing: float = 0.0,
                   surf_id: str = "INERT", name: str = "STAIR", color: Optional[str] = None) -> List[Any]:
        """Straight flight of solid steps climbing from (x, y) towards +X/-X/+Y/-Y."""
        boxes = shapes.stairs(x, y, z, direction, width, steps, riser, tread, landing)
        return self._add_boxes(boxes, name, surf_id, color, f"add stairs {name}")

    def add_roof(self, xb: Sequence[float], z_eave: float, pitch_deg: float, thickness: float = 0.2,
                 kind: str = "gable", ridge_axis: str = "X", overhang: float = 0.0,
                 surf_id: str = "INERT", name: str = "ROOF", res: Optional[float] = None,
                 color: Optional[str] = None) -> List[Any]:
        """Pitched roof over the rectangle ``xb = [x0, x1, y0, y1]``: ``gable`` or ``shed``."""
        boxes = shapes.roof(xb[0], xb[1], xb[2], xb[3], z_eave, pitch_deg, thickness, kind, ridge_axis,
                            overhang, self._resolution(res))
        return self._add_boxes(boxes, name, surf_id, color, f"add roof {name}")

    def add_truss(self, x: float, y: float, z: float, span: float, rise: float, panels: int = 6,
                  member: float = 0.1, depth: float = 0.1, along: str = "X", surf_id: str = "INERT",
                  name: str = "TRUSS", res: Optional[float] = None, color: Optional[str] = None) -> List[Any]:
        """Planar Warren truss starting at (x, y, z) running along X or Y."""
        boxes = shapes.truss(x, y, z, span, rise, panels, member, depth, along,
                             self._resolution(res) if res else min(member / 2, 0.05))
        return self._add_boxes(boxes, name, surf_id, color, f"add truss {name}")

    # -- boolean (GEO-15) ------------------------------------------------------------
    def _geom(self, geom_or_name):
        g = next((x for x in self.all() if x is geom_or_name or x.name == geom_or_name), None) \
            if isinstance(geom_or_name, str) else geom_or_name
        if g is None or g not in self.all():
            raise KeyError(f"geometry {geom_or_name!r} not found")
        return g

    def boolean(self, op: str, a, b, name: str = "Boolean", surf_id: Optional[str] = None,
                remove_inputs: bool = False) -> Any:
        """``union`` / ``difference`` (a minus b) / ``intersection`` of two closed ``&GEOM`` surfaces.

        One undo step; with *remove_inputs* both operands are deleted in the same step."""
        from pyfds.domain.geometry_tools import GeometryTools
        ga, gb = self._geom(a), self._geom(b)
        if ga is gb:
            raise ValueError("pick two different geometries")
        result = GeometryTools.boolean(op, ga, gb, name=_unique(self, name), surf_id=surf_id or ga.surf_id)
        with self._api.history.transaction(f"geometry {op} {ga.name}/{gb.name}"):
            from pyfds.automation.commands import AddEntityCommand, RemoveEntityCommand
            self._api.history.execute(AddEntityCommand(self._project, result))
            if remove_inputs:
                for g in (ga, gb):
                    self._api.history.execute(RemoveEntityCommand(self._project, g))
        return result

    # -- blocks (GEO-12) -------------------------------------------------------------
    def preview_blocks(self, geom_or_name, mesh=None, mode: str = "surface") -> dict:
        """What *convert_to_blocks* would make, without touching the project:
        ``{"count": n, "boxes": [[xmin, xmax, ymin, ymax, zmin, zmax], ...]}``."""
        g = self._geom(geom_or_name)
        obsts = self.voxelize(g, mesh, mode=mode, add_to_project=False)
        return {"count": len(obsts),
                "boxes": [[o.x_min, o.x_max, o.y_min, o.y_max, o.z_min, o.z_max] for o in obsts]}

    def convert_to_blocks(self, geom_or_name, mesh=None, mode: str = "surface", surf_id: Optional[str] = None,
                          name_prefix: str = "blk", remove_geom: bool = True) -> List[Any]:
        """Replace a ``&GEOM`` with grid-aligned obstructions (one undo step)."""
        g = self._geom(geom_or_name)
        with self._api.history.transaction(f"convert {g.name} to blocks"):
            obsts = self.voxelize(g, mesh, surf_id=surf_id or g.surf_id, name_prefix=name_prefix, mode=mode)
            if remove_geom:
                self.remove(g)
        return obsts
