"""Meshes as FDS sees them: a mesh with ``MULT_ID`` stands for one mesh per copy of its &MULT.

``&MESH ... MULT_ID='m'`` with ``&MULT ID='m', DX=2.5, I_UPPER=1`` is two meshes side by side. The project keeps the single
entry the user typed; this module expands it for everything that needs the real set (validation, the 3D view, the MPI
process count). The copies are throw-away objects: changing one does not change the project.
"""
from __future__ import annotations

from typing import Any, List


def mesh_copies(project: Any, mesh: Any) -> List[Any]:
    """The meshes *mesh* stands for: itself when it has no multiplier, else one shifted copy per index (I fastest)."""
    mult_id = getattr(mesh, "mult_id", None)
    mult = next((m for m in getattr(project, "mults", []) if m.name == mult_id), None) if mult_id else None
    if mult is None:
        return [mesh]
    out = []
    for k in range(mult.k_lower, mult.k_upper + 1):
        for j in range(mult.j_lower, mult.j_upper + 1):
            for i in range(mult.i_lower, mult.i_upper + 1):
                dx, dy, dz = mult.dx0 + i * mult.dx, mult.dy0 + j * mult.dy, mult.dz0 + k * mult.dz
                copy = mesh.model_copy(update={
                    "name": f"{mesh.name}" if (i, j, k) == (mult.i_lower, mult.j_lower, mult.k_lower) else f"{mesh.name}_{i}_{j}_{k}",
                    "x_min": mesh.x_min + dx, "x_max": mesh.x_max + dx, "y_min": mesh.y_min + dy, "y_max": mesh.y_max + dy,
                    "z_min": mesh.z_min + dz, "z_max": mesh.z_max + dz, "mult_id": None})
                out.append(copy)
    return out


def expanded_meshes(project: Any) -> List[Any]:
    """Every mesh FDS will run, multipliers expanded, in file order."""
    return [c for m in project.meshes for c in mesh_copies(project, m)]


def mesh_count(project: Any) -> int:
    return len(expanded_meshes(project))
