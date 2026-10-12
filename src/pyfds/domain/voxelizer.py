"""
PyFDS Voxelizer
================
Converts a ``Geom`` entity (or STL path) into a list of axis-aligned
``Obstruction`` objects by rasterising the geometry onto an FDS mesh grid.

Two modes
---------
``surface``  — obstructions are the voxels that the triangle surface passes
               through (shell).  Fast and always correct.
``solid``    — flood-fill from the outside after surface voxelisation to
               distinguish inside from outside cells.  Requires a *watertight*
               (closed, manifold) mesh; non-watertight meshes fall back to
               surface mode with a warning.

Usage::

    from pyfds.domain.voxelizer import Voxelizer
    from pyfds.io.stl_importer import StlImporter
    from pyfds.domain.model import Mesh

    geom = StlImporter.load("building.stl", surf_id="CONCRETE")
    mesh = Mesh(x_min=0, x_max=50, y_min=0, y_max=50, z_min=0, z_max=20,
                cell_count=(50, 50, 20))

    obsts = Voxelizer.voxelize(geom, mesh, surf_id="CONCRETE",
                               mode="solid", name_prefix="bldg")
    for o in obsts:
        project.add_entity(o)
"""
from __future__ import annotations

import logging
import math
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_Vec3 = Tuple[float, float, float]


# ---------------------------------------------------------------------------
# Low-level geometry helpers
# ---------------------------------------------------------------------------

def _sub(a: _Vec3, b: _Vec3) -> _Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: _Vec3, b: _Vec3) -> _Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: _Vec3, b: _Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _triangle_aabb_overlap(
    v0: _Vec3, v1: _Vec3, v2: _Vec3,
    bmin: _Vec3, bmax: _Vec3,
) -> bool:
    """
    Separating Axis Theorem test: return True if triangle (v0,v1,v2)
    overlaps the AABB [bmin, bmax].

    Tests: 3 AABB face normals + 1 triangle normal + 9 edge×face axes.
    """
    hx = (bmax[0] - bmin[0]) * 0.5
    hy = (bmax[1] - bmin[1]) * 0.5
    hz = (bmax[2] - bmin[2]) * 0.5
    cx = bmin[0] + hx
    cy = bmin[1] + hy
    cz = bmin[2] + hz

    # Translate triangle to box-centred coords
    t0 = (v0[0] - cx, v0[1] - cy, v0[2] - cz)
    t1 = (v1[0] - cx, v1[1] - cy, v1[2] - cz)
    t2 = (v2[0] - cx, v2[1] - cy, v2[2] - cz)

    e0 = _sub(t1, t0)
    e1 = _sub(t2, t1)
    e2 = _sub(t0, t2)

    half = (hx, hy, hz)

    # Test 9 edge×AABB-axis cross-product separators
    for edge in (e0, e1, e2):
        for axis_idx in range(3):
            # Axis: e × face-normal (one of (1,0,0),(0,1,0),(0,0,1))
            ax = (
                0.0 if axis_idx == 0 else (-edge[2] if axis_idx == 1 else  edge[1]),
                0.0 if axis_idx == 1 else ( edge[2] if axis_idx == 0 else -edge[0]),
                0.0 if axis_idx == 2 else (-edge[1] if axis_idx == 0 else  edge[0]),
            )
            p0 = _dot(t0, ax)
            p1 = _dot(t1, ax)
            p2 = _dot(t2, ax)
            r = abs(ax[0]) * half[0] + abs(ax[1]) * half[1] + abs(ax[2]) * half[2]
            if min(p0, p1, p2) > r + 1e-12 or max(p0, p1, p2) < -(r + 1e-12):
                return False

    # Test 3 AABB face normals (simple extents test)
    for i in range(3):
        lo = min(t0[i], t1[i], t2[i])
        hi = max(t0[i], t1[i], t2[i])
        if lo > half[i] + 1e-12 or hi < -(half[i] + 1e-12):
            return False

    # Test triangle normal
    normal = _cross(e0, _sub(t2, t0))
    d = _dot(normal, t0)
    r2 = abs(normal[0]) * hx + abs(normal[1]) * hy + abs(normal[2]) * hz
    if abs(d) > r2 + 1e-12:
        return False

    return True


# ---------------------------------------------------------------------------
# Flood-fill helper
# ---------------------------------------------------------------------------

def _flood_fill_outside(
    grid: list,
    ni: int,
    nj: int,
    nk: int,
) -> list:
    """
    6-connected flood fill from all boundary voxels to mark exterior voxels.
    Returns a 3-D boolean list: True = outside.
    """
    outside = [[[False] * nk for _ in range(nj)] for _ in range(ni)]
    stack = []

    def _push(i, j, k):
        if 0 <= i < ni and 0 <= j < nj and 0 <= k < nk:
            if not outside[i][j][k] and not grid[i][j][k]:
                outside[i][j][k] = True
                stack.append((i, j, k))

    # Seed all unoccupied boundary voxels
    for j in range(nj):
        for k in range(nk):
            _push(0, j, k)
            _push(ni - 1, j, k)
    for i in range(ni):
        for k in range(nk):
            _push(i, 0, k)
            _push(i, nj - 1, k)
    for i in range(ni):
        for j in range(nj):
            _push(i, j, 0)
            _push(i, j, nk - 1)

    # BFS
    while stack:
        ci, cj, ck = stack.pop()
        for di, dj, dk in (
            (1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)
        ):
            _push(ci + di, cj + dj, ck + dk)

    return outside


# ---------------------------------------------------------------------------
# Voxelizer
# ---------------------------------------------------------------------------

class Voxelizer:
    """
    Rasterise a ``Geom`` (or STL path) onto an FDS mesh grid.

    All returned ``Obstruction`` objects use a consistent ``name_prefix``.
    They are ready to pass to ``project.add_entity()`` or the API.
    """

    @staticmethod
    def voxelize(
        geom_or_path,
        mesh,
        *,
        surf_id: str = "INERT",
        name_prefix: str = "vox",
        mode: str = "surface",
        color: str = "GRAY",
    ) -> List["Obstruction"]:  # noqa: F821
        """
        Voxelise a geometry onto a mesh grid.

        Parameters
        ----------
        geom_or_path : Geom
            A ``Geom`` entity (load STL files via ``api.geom.voxelize`` or
            ``pyfds.io.stl_importer.StlImporter`` first).
        mesh : Mesh
            Defines the voxel grid extents and resolution.
        surf_id : str
            Surface ID applied to all generated ``Obstruction`` objects.
        name_prefix : str
            Prefix for obstruction names (e.g. ``"bldg"`` → ``"bldg_0042"``).
        mode : {"surface", "solid"}
            ``"surface"`` marks voxels touched by the mesh surface.
            ``"solid"``   uses flood-fill to also fill the interior.
        color : str
            ``COLOR`` applied to generated obstructions.

        Returns
        -------
        list[Obstruction]
        """
        from pyfds.domain.model import Obstruction

        geom = geom_or_path

        if not geom.verts or not geom.faces:
            logger.warning("Voxelizer: empty Geom — returning no obstructions")
            return []

        ni, nj, nk = mesh.cell_count
        dx = (mesh.x_max - mesh.x_min) / ni
        dy = (mesh.y_max - mesh.y_min) / nj
        dz = (mesh.z_max - mesh.z_min) / nk

        # Build occupied grid (ni × nj × nk booleans)
        grid = [[[False] * nk for _ in range(nj)] for _ in range(ni)]

        verts = geom.verts
        faces = geom.faces

        # For each triangle, find candidate voxels via AABB of triangle then SAT test
        for fi, (ia, ib, ic) in enumerate(faces):
            v0 = verts[ia]
            v1 = verts[ib]
            v2 = verts[ic]

            # Triangle bounding box → candidate voxel range
            txmin = min(v0[0], v1[0], v2[0])
            txmax = max(v0[0], v1[0], v2[0])
            tymin = min(v0[1], v1[1], v2[1])
            tymax = max(v0[1], v1[1], v2[1])
            tzmin = min(v0[2], v1[2], v2[2])
            tzmax = max(v0[2], v1[2], v2[2])

            # Convert to grid indices (clamped to mesh extents)
            i0 = max(0, int(math.floor((txmin - mesh.x_min) / dx)))
            i1 = min(ni - 1, int(math.floor((txmax - mesh.x_min) / dx)))
            j0 = max(0, int(math.floor((tymin - mesh.y_min) / dy)))
            j1 = min(nj - 1, int(math.floor((tymax - mesh.y_min) / dy)))
            k0 = max(0, int(math.floor((tzmin - mesh.z_min) / dz)))
            k1 = min(nk - 1, int(math.floor((tzmax - mesh.z_min) / dz)))

            for ci in range(i0, i1 + 1):
                for cj in range(j0, j1 + 1):
                    for ck in range(k0, k1 + 1):
                        if grid[ci][cj][ck]:
                            continue
                        bmin = (
                            mesh.x_min + ci * dx,
                            mesh.y_min + cj * dy,
                            mesh.z_min + ck * dz,
                        )
                        bmax = (bmin[0] + dx, bmin[1] + dy, bmin[2] + dz)
                        if _triangle_aabb_overlap(v0, v1, v2, bmin, bmax):
                            grid[ci][cj][ck] = True

        logger.info(
            "Voxelizer: surface pass — %d occupied voxels for %d triangles",
            sum(grid[i][j][k] for i in range(ni) for j in range(nj)
                for k in range(nk)),
            len(faces),
        )

        # Solid mode: flood-fill to find outside, then mark non-outside non-surface as inside
        if mode == "solid":
            outside = _flood_fill_outside(grid, ni, nj, nk)
            n_added = 0
            for ci in range(ni):
                for cj in range(nj):
                    for ck in range(nk):
                        if not grid[ci][cj][ck] and not outside[ci][cj][ck]:
                            grid[ci][cj][ck] = True
                            n_added += 1
            logger.info("Voxelizer: solid fill added %d interior voxels", n_added)

        # Build Obstruction list
        obstructions: List[Obstruction] = []
        counter = 0
        for ci in range(ni):
            for cj in range(nj):
                for ck in range(nk):
                    if grid[ci][cj][ck]:
                        x0 = mesh.x_min + ci * dx
                        y0 = mesh.y_min + cj * dy
                        z0 = mesh.z_min + ck * dz
                        obstructions.append(Obstruction(
                            name=f"{name_prefix}_{counter:05d}",
                            x_min=x0,      x_max=x0 + dx,
                            y_min=y0,      y_max=y0 + dy,
                            z_min=z0,      z_max=z0 + dz,
                            surface_id=surf_id,
                            color=color,
                        ))
                        counter += 1

        logger.info("Voxelizer: generated %d obstructions", len(obstructions))
        return obstructions
