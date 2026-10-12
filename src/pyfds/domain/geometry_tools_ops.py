"""GeometryTools: extrude, merge, bounds, boolean."""
from __future__ import annotations

from typing import List, Sequence, Tuple

from .geometry_tools_common import (
    _Face,
    _Vertex,
    _geom_to_polydata,
)


class GeometryToolsOpsMixin:
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
