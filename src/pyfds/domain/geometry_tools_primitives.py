"""GeometryTools: sphere, cylinder, cone."""
from __future__ import annotations

import math
from typing import List, Tuple

from .geometry_tools_common import _Face, _Vertex


class GeometryToolsPrimitivesMixin:
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
