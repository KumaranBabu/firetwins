"""
PyFDS Geometry Primitives
==========================
Helper functions that build ``Geom`` entities from parametric shapes.
No external dependencies — pure Python math only.

Available shapes
----------------
sphere        — UV-sphere from latitude/longitude bands
cylinder      — capped cylinder from n-sided prism
cone          — capped cone
box_geom      — triangulated axis-aligned box (6 faces → 12 triangles)
extrude_polygon — extrude a 2-D polygon along Z to form walls + caps
boolean       — union/difference/intersection of two Geoms (via pyvista/VTK)

Usage::

    from pyfds.domain.geometry_tools import GeometryTools

    geom = GeometryTools.sphere(center=(5, 5, 2), radius=1.0, surf_id="STEEL")
    project.add_entity(geom)
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

_Vertex = Tuple[float, float, float]
_Face   = Tuple[int, int, int]


class GeometryTools:
    """Factory methods for parametric FDS &GEOM primitives."""

    # ── Box ───────────────────────────────────────────────────────────────────

    @staticmethod
    def box_geom(
        xb: Sequence[float],
        surf_id: str = "INERT",
        name: str = "Box",
    ) -> "Geom":  # noqa: F821
        """
        Triangulated axis-aligned box.

        Parameters
        ----------
        xb : (x_min, x_max, y_min, y_max, z_min, z_max)
        surf_id : str
        name : str

        Returns
        -------
        Geom
        """
        from pyfds.domain.model import Geom

        x0, x1, y0, y1, z0, z1 = float(xb[0]), float(xb[1]), float(xb[2]), \
                                    float(xb[3]), float(xb[4]), float(xb[5])
        verts: List[_Vertex] = [
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),  # 0-3 bottom
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),  # 4-7 top
        ]
        # 6 faces × 2 triangles each
        faces: List[_Face] = [
            (0, 2, 1), (0, 3, 2),   # -Z (bottom)
            (4, 5, 6), (4, 6, 7),   # +Z (top)
            (0, 1, 5), (0, 5, 4),   # -Y (front)
            (2, 3, 7), (2, 7, 6),   # +Y (back)
            (1, 2, 6), (1, 6, 5),   # +X (right)
            (0, 4, 7), (0, 7, 3),   # -X (left)
        ]
        return Geom(name=name, surf_id=surf_id, verts=verts, faces=faces)

    # ── Sphere ────────────────────────────────────────────────────────────────

    @staticmethod
    def sphere(
        center: Tuple[float, float, float],
        radius: float,
        surf_id: str = "INERT",
        name: str = "Sphere",
        n_lat: int = 12,
        n_lon: int = 24,
    ) -> "Geom":  # noqa: F821
        """
        UV-sphere centred at *center* with given *radius*.

        Parameters
        ----------
        center : (cx, cy, cz)
        radius : float
        surf_id : str
        name : str
        n_lat : int
            Number of latitude bands (rings), minimum 3.
        n_lon : int
            Number of longitude segments (slices), minimum 3.

        Returns
        -------
        Geom
        """
        from pyfds.domain.model import Geom

        if radius <= 0:
            raise ValueError(f"sphere radius must be > 0 (got {radius})")
        n_lat = max(3, n_lat)
        n_lon = max(3, n_lon)
        cx, cy, cz = center

        verts: List[_Vertex] = []
        faces: List[_Face] = []

        # Poles
        verts.append((cx, cy, cz + radius))  # index 0 — top pole
        for i in range(1, n_lat):
            phi = math.pi * i / n_lat          # 0 (top) → π (bottom)
            for j in range(n_lon):
                theta = 2.0 * math.pi * j / n_lon
                x = cx + radius * math.sin(phi) * math.cos(theta)
                y = cy + radius * math.sin(phi) * math.sin(theta)
                z = cz + radius * math.cos(phi)
                verts.append((x, y, z))
        verts.append((cx, cy, cz - radius))  # bottom pole

        # Top cap (fan from pole index 0)
        for j in range(n_lon):
            a = 1 + j
            b = 1 + (j + 1) % n_lon
            faces.append((0, a, b))

        # Middle bands
        for i in range(n_lat - 2):
            row_start = 1 + i * n_lon
            for j in range(n_lon):
                a = row_start + j
                b = row_start + (j + 1) % n_lon
                c = a + n_lon
                d = b + n_lon
                faces.append((a, b, d))
                faces.append((a, d, c))

        # Bottom cap
        bot_pole = len(verts) - 1
        last_row_start = 1 + (n_lat - 2) * n_lon
        for j in range(n_lon):
            a = last_row_start + j
            b = last_row_start + (j + 1) % n_lon
            faces.append((a, bot_pole, b))

        return Geom(name=name, surf_id=surf_id, verts=verts, faces=faces)

    # ── Cylinder ──────────────────────────────────────────────────────────────

    @staticmethod
    def cylinder(
        center_base: Tuple[float, float, float],
        radius: float,
        height: float,
        surf_id: str = "INERT",
        name: str = "Cylinder",
        n_sides: int = 16,
        cap_top: bool = True,
        cap_bottom: bool = True,
    ) -> "Geom":  # noqa: F821
        """
        Right circular cylinder.

        Parameters
        ----------
        center_base : (cx, cy, cz_bottom)
            Centre of the bottom face.
        radius : float
        height : float
        surf_id : str
        name : str
        n_sides : int
            Number of polygon sides, minimum 3.
        cap_top, cap_bottom : bool
            Include the circular end caps.

        Returns
        -------
        Geom
        """
        from pyfds.domain.model import Geom

        if radius <= 0:
            raise ValueError(f"cylinder radius must be > 0 (got {radius})")
        if height <= 0:
            raise ValueError(f"cylinder height must be > 0 (got {height})")
        n_sides = max(3, n_sides)
        cx, cy, cz = center_base
        cz_top = cz + height

        verts: List[_Vertex] = []
        faces: List[_Face] = []

        # Bottom ring (0..n_sides-1)
        for j in range(n_sides):
            theta = 2.0 * math.pi * j / n_sides
            verts.append((cx + radius * math.cos(theta),
                          cy + radius * math.sin(theta),
                          cz))

        # Top ring (n_sides..2*n_sides-1)
        for j in range(n_sides):
            theta = 2.0 * math.pi * j / n_sides
            verts.append((cx + radius * math.cos(theta),
                          cy + radius * math.sin(theta),
                          cz_top))

        # Side quads → 2 triangles each
        for j in range(n_sides):
            a = j
            b = (j + 1) % n_sides
            c = j + n_sides
            d = (j + 1) % n_sides + n_sides
            faces.append((a, b, d))
            faces.append((a, d, c))

        # Bottom cap (fan)
        if cap_bottom:
            bot_center_idx = len(verts)
            verts.append((cx, cy, cz))
            for j in range(n_sides):
                a = j
                b = (j + 1) % n_sides
                faces.append((bot_center_idx, b, a))  # inward normal

        # Top cap (fan)
        if cap_top:
            top_center_idx = len(verts)
            verts.append((cx, cy, cz_top))
            for j in range(n_sides):
                a = n_sides + j
                b = n_sides + (j + 1) % n_sides
                faces.append((top_center_idx, a, b))

        return Geom(name=name, surf_id=surf_id, verts=verts, faces=faces)

    # ── Cone ─────────────────────────────────────────────────────────────────

    @staticmethod
    def cone(
        center_base: Tuple[float, float, float],
        radius: float,
        height: float,
        surf_id: str = "INERT",
        name: str = "Cone",
        n_sides: int = 16,
        cap_bottom: bool = True,
    ) -> "Geom":  # noqa: F821
        """
        Right circular cone.

        Parameters
        ----------
        center_base : (cx, cy, cz_bottom)
        radius : float
            Radius of the base circle.
        height : float
        surf_id : str
        name : str
        n_sides : int
            Polygon sides for the base ring, minimum 3.
        cap_bottom : bool
            Include the circular base cap.

        Returns
        -------
        Geom
        """
        if radius <= 0:
            raise ValueError(f"cone radius must be > 0 (got {radius})")
        if height <= 0:
            raise ValueError(f"cone height must be > 0 (got {height})")
        from pyfds.domain.model import Geom

        n_sides = max(3, n_sides)
        cx, cy, cz = center_base

        verts: List[_Vertex] = []
        faces: List[_Face] = []

        # Base ring (0..n_sides-1)
        for j in range(n_sides):
            theta = 2.0 * math.pi * j / n_sides
            verts.append((cx + radius * math.cos(theta),
                          cy + radius * math.sin(theta),
                          cz))

        # Apex
        apex = len(verts)
        verts.append((cx, cy, cz + height))

        # Side faces
        for j in range(n_sides):
            a = j
            b = (j + 1) % n_sides
            faces.append((a, b, apex))

        # Bottom cap
        if cap_bottom:
            center_idx = len(verts)
            verts.append((cx, cy, cz))
            for j in range(n_sides):
                a = j
                b = (j + 1) % n_sides
                faces.append((center_idx, b, a))

        return Geom(name=name, surf_id=surf_id, verts=verts, faces=faces)

    # ── Extruded polygon ─────────────────────────────────────────────────────

    @staticmethod
    def extrude_polygon(
        polygon_xy: Sequence[Tuple[float, float]],
        z_bottom: float,
        z_top: float,
        surf_id: str = "INERT",
        name: str = "Extrusion",
        cap_top: bool = True,
        cap_bottom: bool = True,
    ) -> "Geom":  # noqa: F821
        """
        Extrude a 2-D polygon (XY) along Z to create walls and optional caps.

        Useful for building floor plans: pass the perimeter as a list of
        (x, y) coordinates (counter-clockwise when viewed from above).

        Parameters
        ----------
        polygon_xy : list of (x, y)
            Polygon vertices in order (last edge closes back to first).
        z_bottom, z_top : float
        surf_id : str
        name : str

        Returns
        -------
        Geom
        """
        from pyfds.domain.model import Geom

        n = len(polygon_xy)
        if n < 3:
            raise ValueError("extrude_polygon requires at least 3 vertices")

        verts: List[_Vertex] = []
        faces: List[_Face] = []

        # Bottom ring → top ring
        for x, y in polygon_xy:
            verts.append((x, y, z_bottom))
        for x, y in polygon_xy:
            verts.append((x, y, z_top))

        # Wall quads
        for j in range(n):
            a = j
            b = (j + 1) % n
            c = j + n
            d = (j + 1) % n + n
            faces.append((a, b, d))
            faces.append((a, d, c))

        # Simple fan triangulation for caps (works for convex polygons)
        if cap_bottom:
            for j in range(1, n - 1):
                faces.append((0, j + 1, j))  # CCW from below → outward -Z

        if cap_top:
            off = n
            for j in range(1, n - 1):
                faces.append((off, off + j, off + j + 1))

        return Geom(name=name, surf_id=surf_id, verts=verts, faces=faces)

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def merge(*geoms: "Geom", name: str = "Merged", surf_id: str = "INERT") -> "Geom":  # noqa: F821
        """
        Merge multiple ``Geom`` objects into one by concatenating their
        vertex/face lists (vertex indices are offset accordingly).

        Parameters
        ----------
        *geoms : Geom
        name : str
        surf_id : str

        Returns
        -------
        Geom
        """
        from pyfds.domain.model import Geom

        all_verts: List[_Vertex] = []
        all_faces: List[_Face] = []

        for g in geoms:
            offset = len(all_verts)
            if g.verts:
                all_verts.extend(g.verts)
            if g.faces:
                all_faces.extend((f[0] + offset, f[1] + offset, f[2] + offset)
                                  for f in g.faces)

        return Geom(name=name, surf_id=surf_id, verts=all_verts, faces=all_faces)

    @staticmethod
    def bounds(geom: "Geom") -> Tuple[  # noqa: F821
        Tuple[float, float],
        Tuple[float, float],
        Tuple[float, float],
    ]:
        """Return ``((xmin,xmax),(ymin,ymax),(zmin,zmax))`` of a Geom."""
        if not geom.verts:
            return (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)
        xs = [v[0] for v in geom.verts]
        ys = [v[1] for v in geom.verts]
        zs = [v[2] for v in geom.verts]
        return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))

    # ── Boolean CSG ──────────────────────────────────────────────────────────

    @staticmethod
    def boolean(
        op: str,
        geom_a: "Geom",  # noqa: F821
        geom_b: "Geom",  # noqa: F821
        name: str = "Boolean",
        surf_id: str = "INERT",
    ) -> "Geom":  # noqa: F821
        """
        Boolean union/difference/intersection of two Geom meshes.

        Delegates to PyVista's VTK-backed boolean filters — pyvista is
        already a hard dependency (3D rendering) and already has this
        capability built in, so no separate B-Rep engine is needed here.

        Parameters
        ----------
        op : "union" | "difference" | "intersection"
            "difference" subtracts *geom_b* from *geom_a*.
        geom_a, geom_b : Geom
            Must be closed (watertight), manifold meshes — VTK's
            requirement for a boolean result to be well-defined. Checked
            up front; raises ``ValueError`` with a clear message instead
            of silently returning a garbage/degenerate mesh.
        name, surf_id : str
            Applied to the returned Geom.

        Returns
        -------
        Geom
            A new, independent mesh — *geom_a*/*geom_b* are left
            untouched.
        """
        if op not in ("union", "difference", "intersection"):
            raise ValueError(f"op must be 'union', 'difference', or 'intersection', got {op!r}")

        poly_a = _geom_to_polydata(geom_a)
        poly_b = _geom_to_polydata(geom_b)
        for label, poly, geom in (("first", poly_a, geom_a), ("second", poly_b, geom_b)):
            if poly.n_open_edges > 0:
                raise ValueError(
                    f"Geom '{geom.name}' ({label} selection) is not a closed mesh — "
                    "boolean operations need watertight geometry."
                )

        poly_a = poly_a.triangulate()
        poly_b = poly_b.triangulate()
        if op == "union":
            result = poly_a.boolean_union(poly_b)
        elif op == "difference":
            result = poly_a.boolean_difference(poly_b)
        else:
            result = poly_a.boolean_intersection(poly_b)
        result = result.triangulate()

        from pyfds.domain.model import Geom

        verts = [tuple(float(c) for c in p) for p in result.points]
        faces = [tuple(int(i) for i in f) for f in result.regular_faces]
        return Geom(name=name, surf_id=surf_id, verts=verts, faces=faces)


def _geom_to_polydata(geom: "Geom") -> "pv.PolyData":  # noqa: F821
    """Same triangle-array construction ``viewport_scene.py``'s
    ``build_scene`` already uses to render a Geom — kept as a private
    duplicate rather than a cross-import since ``domain/`` must not depend
    on ``gui/``."""
    import pyvista as pv

    if not geom.verts or not geom.faces:
        raise ValueError(f"Geom '{geom.name}' has no vertices/faces.")
    flat_faces: List[int] = []
    for face in geom.faces:
        flat_faces.append(len(face))
        flat_faces.extend(face)
    return pv.PolyData(geom.verts, flat_faces)
