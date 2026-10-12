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

from typing import List, Sequence

from .geometry_tools_ops import (  # noqa: F401  (re-exported)
    GeometryToolsOpsMixin,
)
from .geometry_tools_primitives import (  # noqa: F401  (re-exported)
    GeometryToolsPrimitivesMixin,
)
from .geometry_tools_common import (  # noqa: F401  (re-exported)
    _Face,
    _Vertex,
    _geom_to_polydata,
)

from .geometry_tools_common import (  # noqa: F401  (re-exported)
    _geom_to_polydata,
)


class GeometryTools(GeometryToolsPrimitivesMixin, GeometryToolsOpsMixin):
    """Factory methods for parametric FDS &GEOM primitives."""

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
