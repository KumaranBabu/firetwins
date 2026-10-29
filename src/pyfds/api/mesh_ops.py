"""Mesh operations: refine, split, merge, move/scale/mirror/rotate, refinement zones,
open boundaries, stretching and statistics (plan step B1).

Mixed into :class:`pyfds.api.meshes.MeshManager`. Every public operation is ONE undo
step (it runs inside a history transaction), and validates before changing anything.
Meshes are axis-aligned boxes with a uniform cell size, so every operation keeps that
true; non-uniform spacing is expressed separately by ``MeshTransform`` control points.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .species import _unique

_AXES = {"X": 0, "Y": 1, "Z": 2}
_FACES = ("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX")
_EPS = 1e-9


def _axis(axis: str) -> int:
    try:
        return _AXES[axis.strip().upper()]
    except (KeyError, AttributeError):
        raise ValueError("axis must be X, Y or Z") from None


def _bounds(mesh) -> Tuple[List[float], List[float]]:
    return ([mesh.x_min, mesh.y_min, mesh.z_min], [mesh.x_max, mesh.y_max, mesh.z_max])


def _set_bounds_cmds(mesh, lo, hi, cells):
    from pyfds.automation.commands import ModifyPropertyCommand
    return [ModifyPropertyCommand(mesh, "x_min", lo[0]), ModifyPropertyCommand(mesh, "x_max", hi[0]),
            ModifyPropertyCommand(mesh, "y_min", lo[1]), ModifyPropertyCommand(mesh, "y_max", hi[1]),
            ModifyPropertyCommand(mesh, "z_min", lo[2]), ModifyPropertyCommand(mesh, "z_max", hi[2]),
            ModifyPropertyCommand(mesh, "cell_count", tuple(int(c) for c in cells))]


def subtract_rects(rect, cutters, eps=_EPS):
    """``rect`` minus the union of ``cutters`` — all ``(u0, u1, v0, v1)`` — as disjoint rectangles."""
    pieces = [tuple(rect)]
    for c in cutters:
        nxt = []
        for (a0, a1, b0, b1) in pieces:
            i0, i1, j0, j1 = max(a0, c[0]), min(a1, c[1]), max(b0, c[2]), min(b1, c[3])
            if i1 - i0 <= eps or j1 - j0 <= eps:
                nxt.append((a0, a1, b0, b1))
                continue
            if i0 - a0 > eps: nxt.append((a0, i0, b0, b1))          # left strip
            if a1 - i1 > eps: nxt.append((i1, a1, b0, b1))          # right strip
            if j0 - b0 > eps: nxt.append((i0, i1, b0, j0))          # below the hole
            if b1 - j1 > eps: nxt.append((i0, i1, j1, b1))          # above the hole
        pieces = nxt
    return [p for p in pieces if p[1] - p[0] > eps and p[3] - p[2] > eps]


class MeshOperations:
    """Mixin for ``MeshManager`` (needs ``all()``, ``get()``, ``add()``, ``remove()``, ``_api``, ``_project``)."""

    # -- helpers -------------------------------------------------------------------
    def _mesh(self, mesh_or_name):
        mesh = self.get(mesh_or_name) if isinstance(mesh_or_name, str) else mesh_or_name
        if mesh is None or mesh not in self.all():
            raise KeyError(f"mesh {mesh_or_name!r} not found")
        return mesh

    def _tx(self, label: str):
        return self._api.history.transaction(label)

    def _exec(self, cmds, label: str) -> None:
        from pyfds.automation.commands import GroupCommand
        res = self._pipe.execute(GroupCommand(list(cmds), label=label))
        if not res.success:
            raise ValueError(res.message)

    def _clone(self, mesh, name: Optional[str], lo, hi, cells):
        from pyfds.domain.model import Mesh
        return Mesh(name=name or _unique(self, f"{mesh.name}_copy"),
                    x_min=lo[0], x_max=hi[0], y_min=lo[1], y_max=hi[1], z_min=lo[2], z_max=hi[2],
                    cell_count=tuple(int(c) for c in cells), color=mesh.color,
                    cylindrical=mesh.cylindrical, description=mesh.description)

    def mesh_number(self, mesh_or_name) -> int:
        """1-based position in the written file (what ``&TRNX MESH_NUMBER`` refers to)."""
        mesh = self._mesh(mesh_or_name)
        ordered = sorted(self.all(), key=lambda m: (m.priority is None, m.priority or 0))
        return ordered.index(mesh) + 1

    # -- statistics (MSH-03) ---------------------------------------------------------------
    def stats(self, mesh_or_name) -> Dict[str, Any]:
        """Derived numbers the Properties tab shows: cell size, aspect ratio, cell count,
        and whether the spacing is stretched by ``MeshTransform`` points."""
        mesh = self._mesh(mesh_or_name)
        lo, hi = _bounds(mesh)
        size = [(hi[i] - lo[i]) / mesh.cell_count[i] for i in range(3)]
        n = self.mesh_number(mesh)
        stretched = sorted({t.direction for t in self._project.mesh_transforms if t.mesh_number == n})
        return {"cell_size": tuple(size), "cells": tuple(mesh.cell_count),
                "total_cells": mesh.cell_count[0] * mesh.cell_count[1] * mesh.cell_count[2],
                "aspect_ratio": max(size) / min(size), "non_uniform_axes": stretched,
                "uniform": not stretched}

    def project_stats(self) -> Dict[str, Any]:
        """Totals over all meshes (including any refinement already applied)."""
        per = {m.name: self.stats(m)["total_cells"] for m in self.all()}
        return {"meshes": len(per), "total_cells": sum(per.values()), "per_mesh": per}

    # -- refine / split / merge (MSH-06, MSH-08, MSH-10) ---------------------------------------------
    def refine(self, mesh_or_name, factor: int = 2) -> Any:
        """Divide every cell by *factor* in each direction (factor 2 = one cell becomes eight)."""
        mesh = self._mesh(mesh_or_name)
        if not isinstance(factor, int) or factor < 2:
            raise ValueError("factor must be an integer >= 2")
        lo, hi = _bounds(mesh)
        with self._tx(f"refine mesh {mesh.name} x{factor}"):
            self._exec(_set_bounds_cmds(mesh, lo, hi, [c * factor for c in mesh.cell_count]),
                       f"refine {mesh.name}")
        return mesh

    def split(self, mesh_or_name, axis: str, at: Optional[float] = None,
              new_name: Optional[str] = None) -> Any:
        """Cut a mesh in two on a plane perpendicular to *axis*; returns the new (upper) mesh.

        *at* is snapped to the nearest cell boundary (default: the middle). Cell size is
        unchanged. If the mesh has an MPI rank, the new mesh gets the next free rank.
        """
        mesh = self._mesh(mesh_or_name)
        a = _axis(axis)
        lo, hi = _bounds(mesh)
        n = mesh.cell_count[a]
        if n < 2:
            raise ValueError(f"{mesh.name} has only {n} cell along {axis.upper()}; cannot split")
        h = (hi[a] - lo[a]) / n
        k = n // 2 if at is None else int(round((at - lo[a]) / h))
        if not 1 <= k <= n - 1:
            raise ValueError(f"split position {at} is not inside mesh {mesh.name} "
                             f"({lo[a]}..{hi[a]}) on a cell boundary")
        plane = lo[a] + k * h
        lo2, hi2 = list(lo), list(hi)
        hi2_first = list(hi); hi2_first[a] = plane
        lo2[a] = plane
        cells1 = list(mesh.cell_count); cells1[a] = k
        cells2 = list(mesh.cell_count); cells2[a] = n - k
        from pyfds.automation.commands import AddEntityCommand
        new = self._clone(mesh, new_name or _unique(self, f"{mesh.name}_2"), lo2, hi, cells2)
        ranks = [m.mpi_processor for m in self.all() if m.mpi_processor is not None]
        if mesh.mpi_processor is not None:
            new.mpi_processor = max(ranks) + 1
        with self._tx(f"split mesh {mesh.name} at {axis.upper()}={plane:g}"):
            self._exec(_set_bounds_cmds(mesh, lo, hi2_first, cells1), f"shrink {mesh.name}")
            self._pipe.execute(AddEntityCommand(self._project, new))
        return new

    def partition(self, mesh_or_name, parts: int, axis: Optional[str] = None) -> List[Any]:
        """Cut a mesh into *parts* slabs of (nearly) equal cell count for MPI load balancing; returns
        ``[mesh, *new meshes]`` in order along *axis* (default: the axis with the most cells). One undo step."""
        mesh = self._mesh(mesh_or_name)
        if not isinstance(parts, int) or parts < 2:
            raise ValueError("parts must be an integer >= 2")
        a = _AXES[axis.strip().upper()] if axis else max(range(3), key=lambda i: mesh.cell_count[i])
        n = mesh.cell_count[a]
        if parts > n:
            raise ValueError(f"{mesh.name} has only {n} cells along {'XYZ'[a]}; cannot make {parts} parts")
        lo, hi = _bounds(mesh)
        h = (hi[a] - lo[a]) / n
        pieces = [mesh]
        with self._tx(f"partition mesh {mesh.name} into {parts}"):
            rest = mesh
            for i in range(1, parts):
                k = round(i * n / parts)
                rest = self.split(rest, "XYZ"[a], lo[a] + k * h)
                pieces.append(rest)
        return pieces

    def merge(self, names: Sequence[Any], new_name: Optional[str] = None) -> Any:
        """Join meshes that exactly tile one box and share a cell size into the first mesh."""
        meshes = [self._mesh(n) for n in names]
        if len(meshes) < 2 or len({id(m) for m in meshes}) != len(meshes):
            raise ValueError("give two or more different meshes")
        lo = [min(_bounds(m)[0][i] for m in meshes) for i in range(3)]
        hi = [max(_bounds(m)[1][i] for m in meshes) for i in range(3)]
        h0 = [(_bounds(meshes[0])[1][i] - _bounds(meshes[0])[0][i]) / meshes[0].cell_count[i] for i in range(3)]
        for m in meshes[1:]:
            h = [(_bounds(m)[1][i] - _bounds(m)[0][i]) / m.cell_count[i] for i in range(3)]
            if any(abs(h[i] - h0[i]) > 1e-6 * h0[i] for i in range(3)):
                raise ValueError(f"{m.name} has a different cell size than {meshes[0].name}")
        vol = lambda m: ((_bounds(m)[1][0] - _bounds(m)[0][0]) * (_bounds(m)[1][1] - _bounds(m)[0][1])
                         * (_bounds(m)[1][2] - _bounds(m)[0][2]))
        box = (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])
        if abs(sum(vol(m) for m in meshes) - box) > 1e-9 * max(box, 1.0):
            raise ValueError("the meshes do not exactly fill a box (gap or overlap)")
        for i, m1 in enumerate(meshes):
            for m2 in meshes[i + 1:]:
                inter = 1.0
                for k in range(3):
                    inter *= max(0.0, min(_bounds(m1)[1][k], _bounds(m2)[1][k])
                                 - max(_bounds(m1)[0][k], _bounds(m2)[0][k]))
                if inter > 1e-12:
                    raise ValueError(f"{m1.name} and {m2.name} overlap")
        cells = [(hi[i] - lo[i]) / h0[i] for i in range(3)]
        if any(abs(c - round(c)) > 1e-6 for c in cells):
            raise ValueError("merged extent is not a whole number of cells")
        from pyfds.automation.commands import ModifyPropertyCommand, RemoveEntityCommand
        keep = meshes[0]
        with self._tx(f"merge {len(meshes)} meshes into {keep.name}"):
            self._exec(_set_bounds_cmds(keep, lo, hi, [round(c) for c in cells]), f"merge into {keep.name}")
            if new_name and new_name != keep.name:
                if self.get(new_name) is not None:
                    raise ValueError(f"{new_name!r} already exists")
                self._pipe.execute(ModifyPropertyCommand(keep, "name", new_name))
            for m in meshes[1:]:
                self._pipe.execute(RemoveEntityCommand(self._project, m))
        return keep

    # -- move / scale / mirror / rotate (MSH-10) -----------------------------------------------------
    def move(self, mesh_or_name, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> Any:
        mesh = self._mesh(mesh_or_name)
        lo, hi = _bounds(mesh)
        d = (dx, dy, dz)
        with self._tx(f"move mesh {mesh.name}"):
            self._exec(_set_bounds_cmds(mesh, [lo[i] + d[i] for i in range(3)],
                                        [hi[i] + d[i] for i in range(3)], mesh.cell_count), f"move {mesh.name}")
        return mesh

    def scale(self, mesh_or_name, factor: float, origin: Sequence[float] = (0.0, 0.0, 0.0)) -> Any:
        """Uniform scale about *origin*; the cell count is kept, so cell size scales too."""
        mesh = self._mesh(mesh_or_name)
        if factor <= 0:
            raise ValueError("factor must be > 0")
        lo, hi = _bounds(mesh)
        f = lambda v, i: origin[i] + (v - origin[i]) * factor
        with self._tx(f"scale mesh {mesh.name} x{factor:g}"):
            self._exec(_set_bounds_cmds(mesh, [f(lo[i], i) for i in range(3)],
                                        [f(hi[i], i) for i in range(3)], mesh.cell_count), f"scale {mesh.name}")
        return mesh

    def mirror(self, mesh_or_name, axis: str, at: float, copy: bool = False,
               new_name: Optional[str] = None) -> Any:
        """Reflect across the plane ``axis = at``. ``copy=True`` adds the mirrored mesh instead of moving."""
        mesh = self._mesh(mesh_or_name)
        a = _axis(axis)
        lo, hi = _bounds(mesh)
        nlo, nhi = list(lo), list(hi)
        nlo[a], nhi[a] = 2 * at - hi[a], 2 * at - lo[a]
        return self._place(mesh, nlo, nhi, mesh.cell_count, copy, new_name, f"mirror mesh {mesh.name}")

    def rotate(self, mesh_or_name, angle: float, origin: Sequence[float] = (0.0, 0.0), copy: bool = False,
               new_name: Optional[str] = None) -> Any:
        """Rotate about the vertical axis through *origin* (x, y). Meshes stay axis-aligned, so
        only multiples of 90 degrees are accepted."""
        mesh = self._mesh(mesh_or_name)
        quarter = angle / 90.0
        if abs(quarter - round(quarter)) > 1e-9:
            raise ValueError("a mesh can only be rotated by multiples of 90 degrees")
        k = int(round(quarter)) % 4
        lo, hi = _bounds(mesh)
        pts = [(lo[0], lo[1]), (hi[0], hi[1])]
        for _ in range(k):                                    # (x, y) -> (-y, x) about origin
            pts = [(origin[0] - (y - origin[1]), origin[1] + (x - origin[0])) for x, y in pts]
        nlo = [min(pts[0][0], pts[1][0]), min(pts[0][1], pts[1][1]), lo[2]]
        nhi = [max(pts[0][0], pts[1][0]), max(pts[0][1], pts[1][1]), hi[2]]
        cells = list(mesh.cell_count)
        if k % 2:
            cells[0], cells[1] = cells[1], cells[0]
        return self._place(mesh, nlo, nhi, cells, copy, new_name, f"rotate mesh {mesh.name}")

    def _place(self, mesh, lo, hi, cells, copy, new_name, label):
        from pyfds.automation.commands import AddEntityCommand
        with self._tx(label):
            if copy:
                new = self._clone(mesh, new_name, lo, hi, cells)
                self._pipe.execute(AddEntityCommand(self._project, new))
                return new
            self._exec(_set_bounds_cmds(mesh, lo, hi, cells), label)
        return mesh

    # -- refinement zone (MSH-09) ----------------------------------------------------------------------
    def apply_refinement(self, mesh_or_name, xb: Sequence[float], factor: int = 2) -> List[Any]:
        """Refine only the box *xb* of a mesh: the mesh is cut so the box becomes its own mesh
        (edges snapped outward to cell boundaries, so the whole drawn box is refined), which is then refined by *factor*; the rest stays
        coarse as up to six neighbouring meshes. Returns ``[refined mesh, *remainder meshes]``.
        """
        mesh = self._mesh(mesh_or_name)
        if len(xb) != 6:
            raise ValueError("xb must be [x_min, x_max, y_min, y_max, z_min, z_max]")
        if not isinstance(factor, int) or factor < 2:
            raise ValueError("factor must be an integer >= 2")
        lo, hi = _bounds(mesh)
        h = [(hi[i] - lo[i]) / mesh.cell_count[i] for i in range(3)]
        zl, zh = [], []
        for i in range(3):
            a = max(lo[i], min(xb[2 * i], xb[2 * i + 1]))
            b = min(hi[i], max(xb[2 * i], xb[2 * i + 1]))
            if b - a < h[i] * 0.5:
                raise ValueError("the zone is outside the mesh or thinner than half a cell")
            # snap outward so the whole drawn zone ends up refined
            k0 = max(0, int(math.floor((a - lo[i]) / h[i] + 1e-6)))
            k1 = min(mesh.cell_count[i], int(math.ceil((b - lo[i]) / h[i] - 1e-6)))
            zl.append(lo[i] + k0 * h[i])
            zh.append(lo[i] + k1 * h[i])
        pieces: List[Any] = []
        with self._tx(f"refine zone in {mesh.name} x{factor}"):
            core = mesh
            for i, axis in enumerate("XYZ"):
                clo, chi = _bounds(core)
                if zl[i] - clo[i] > _EPS:                      # peel off the part below the zone
                    upper = self.split(core, axis, zl[i])
                    pieces.append(core)
                    core = upper
                clo, chi = _bounds(core)
                if chi[i] - zh[i] > _EPS:                      # peel off the part above the zone
                    pieces.append(self.split(core, axis, zh[i]))
            self.refine(core, factor)
        return [core] + pieces

    # -- stretching (MSH-03 non-uniform authoring) -----------------------------------------------------
    def set_stretching(self, mesh_or_name, axis: str, points: Sequence[Tuple[float, float]]) -> List[Any]:
        """Replace the stretching of one axis by control points ``[(cc, pc), ...]`` — ``cc`` the
        coordinate, ``pc`` the fraction (0..1) of the mesh's cells that should lie below it.
        Pass an empty list to return the axis to uniform spacing."""
        from pyfds.automation.commands import RemoveEntityCommand
        mesh = self._mesh(mesh_or_name)
        axis = axis.upper()
        _axis(axis)
        n = self.mesh_number(mesh)
        made: List[Any] = []
        with self._tx(f"stretch mesh {mesh.name} {axis}"):
            for t in [t for t in self._project.mesh_transforms
                      if t.mesh_number == n and t.direction == axis]:
                self._pipe.execute(RemoveEntityCommand(self._project, t))
            for cc, pc in points:
                made.append(self._api.mesh_transforms.add_transform(axis, cc, pc, mesh_number=n))
        return made

    # -- open boundaries (MSH-11) -----------------------------------------------------------------------
    def open_boundaries(self, surf_id: str = "OPEN", meshes: Optional[Sequence[Any]] = None,
                        floor: bool = False) -> List[Any]:
        """Add an ``OPEN`` vent on every mesh face that is not shared with another mesh.

        The bottom face (Z-min) is the ground and stays closed unless *floor* is True. Faces partly shared
        with a neighbour get vents only over the exposed part. Faces already carrying an identical vent are
        skipped, so running it twice adds nothing.
        """
        from pyfds.automation.commands import AddEntityCommand
        from pyfds.domain.model import Vent
        targets = [self._mesh(m) for m in meshes] if meshes else self.all()
        everyone = self.all()
        existing = [(v.x_min, v.x_max, v.y_min, v.y_max, v.z_min, v.z_max) for v in self._project.vents
                    if v.surface_id == surf_id]
        made: List[Vent] = []
        with self._tx("open mesh boundaries"):
            for m in targets:
                lo, hi = _bounds(m)
                for a, axname in enumerate("XYZ"):
                    u, v = [i for i in range(3) if i != a]
                    for side, plane in (("MIN", lo[a]), ("MAX", hi[a])):
                        if axname == "Z" and side == "MIN" and not floor:
                            continue
                        cutters = []
                        for o in everyone:
                            if o is m:
                                continue
                            olo, ohi = _bounds(o)
                            # neighbour whose opposite face lies on this plane
                            if abs((olo[a] if side == "MAX" else ohi[a]) - plane) > 1e-6:
                                continue
                            cutters.append((olo[u], ohi[u], olo[v], ohi[v]))
                        for (u0, u1, v0, v1) in subtract_rects((lo[u], hi[u], lo[v], hi[v]), cutters):
                            xb = [0.0] * 6
                            xb[2 * a] = xb[2 * a + 1] = plane
                            xb[2 * u], xb[2 * u + 1], xb[2 * v], xb[2 * v + 1] = u0, u1, v0, v1
                            if any(all(abs(x - y) < 1e-6 for x, y in zip(xb, e)) for e in existing):
                                continue
                            vent = Vent(name=_unique(self._api.vents, f"{m.name}_{axname}{side}_OPEN"),
                                        x_min=xb[0], x_max=xb[1], y_min=xb[2], y_max=xb[3],
                                        z_min=xb[4], z_max=xb[5], surface_id=surf_id)
                            self._pipe.execute(AddEntityCommand(self._project, vent))
                            existing.append(tuple(xb))
                            made.append(vent)
        return made
