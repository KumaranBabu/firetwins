"""Mesh manager: add/query meshes plus order, alignment test and the operations in ``mesh_ops``."""
from __future__ import annotations

import logging
from typing import Any, Dict

from .base import _CollectionManager
from .mesh_ops import MeshOperations

logger = logging.getLogger(__name__)


class MeshManager(MeshOperations, _CollectionManager):
    """Manage FDS mesh regions."""
    def __init__(self, api):
        from pyfds.domain.model import Mesh
        super().__init__(api, Mesh)

    def add_mesh(self, ijk, xb, **kwargs) -> Any:
        from pyfds.domain.model import Mesh
        entity_id = kwargs.pop("id", None)
        name = kwargs.pop("name", entity_id or "mesh")
        mesh = Mesh(
            name=name,
            cell_count=tuple(int(v) for v in ijk),
            x_min=float(xb[0]), x_max=float(xb[1]),
            y_min=float(xb[2]), y_max=float(xb[3]),
            z_min=float(xb[4]), z_max=float(xb[5]),
            **kwargs,
        )
        self.add(mesh)
        return mesh

    def set_order(self, names: Any) -> None:
        """Set mesh priority from a list of mesh names (first = highest priority), one undo step.

        FDS gives an earlier mesh priority where meshes overlap; the writer emits meshes in
        this order. Meshes not named keep their relative order after the named ones.
        """
        from pyfds.automation.commands import GroupCommand, ModifyPropertyCommand
        names = list(names)
        meshes = self.all()
        unknown = [n for n in names if self.get(n) is None]
        if unknown or len(set(names)) != len(names):
            raise ValueError(f"names must be unique existing meshes (bad: {unknown or 'duplicates'})")
        rest = [m.name for m in meshes if m.name not in names]
        cmds = [ModifyPropertyCommand(self.get(n), "priority", i + 1)
                for i, n in enumerate(names + rest)]
        res = self._pipe.execute(GroupCommand(cmds, label="set mesh order"))
        if not res.success:
            raise ValueError(res.message)

    def alignment_test(self) -> Dict[str, str]:
        """PyroSim's *Mesh Alignment Test*: ``{mesh name: "Passed" | "Failed"}``."""
        from pyfds.validation import MeshAlignmentRule
        messages = [r.message for r in MeshAlignmentRule().check(self._project)]
        return {m.name: ("Failed" if any(f"'{m.name}'" in msg for msg in messages) else "Passed")
                for m in self.all()}

    def check_poisson(self) -> Dict[str, bool]:
        from pyfds.domain.geometry import GeometryHelper
        return {
            m.name: all(
                GeometryHelper.is_poisson_compliant(n) for n in m.cell_count
            )
            for m in self.all()
        }
