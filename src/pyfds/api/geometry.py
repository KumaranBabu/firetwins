"""Obstructions, holes, vents and free-form geometry.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, List, TYPE_CHECKING

from .base import _CollectionManager
from .generators import BuildingGenerators

if TYPE_CHECKING:
    from .facade import FdsApi

logger = logging.getLogger(__name__)


class ObstManager(_CollectionManager):
    """Manage FDS obstructions."""
    def __init__(self, api):
        from pyfds.domain.model import Obstruction
        super().__init__(api, Obstruction)

    def add_obstruction(self, xb: List[float], surf_id: str = "INERT", **kwargs) -> Any:
        from pyfds.domain.model import Obstruction
        # NB: Obstruction has no xb/surf_id fields (it's x_min..z_max /
        # surface_id) — passing xb=/surf_id= straight through silently lands
        # in pydantic's extra="allow" bucket and the obstruction ends up a
        # default unit cube with surface "INERT" no matter what was asked for.
        obst = Obstruction(
            x_min=float(xb[0]), x_max=float(xb[1]),
            y_min=float(xb[2]), y_max=float(xb[3]),
            z_min=float(xb[4]), z_max=float(xb[5]),
            surface_id=surf_id,
            **kwargs,
        )
        self.add(obst)
        return obst

    def move(self, entity_id: str, dx: float = 0, dy: float = 0, dz: float = 0) -> None:
        from pyfds.automation.commands import MoveObstCommand
        obst = self.get(entity_id)
        if obst is None:
            raise KeyError(f"Obstruction {entity_id!r} not found")
        self._pipe.execute(MoveObstCommand(obst, dx, dy, dz))


class VentManager(_CollectionManager):
    """Manage FDS vents (supply/exhaust/open/mirror boundary patches)."""
    def __init__(self, api):
        from pyfds.domain.model import Vent
        super().__init__(api, Vent)

    def add_vent(self, xb: List[float], surf_id: str = "OPEN", **kwargs) -> Any:
        from pyfds.domain.model import Vent
        vent = Vent(
            x_min=float(xb[0]), x_max=float(xb[1]),
            y_min=float(xb[2]), y_max=float(xb[3]),
            z_min=float(xb[4]), z_max=float(xb[5]),
            surface_id=surf_id,
            **kwargs,
        )
        self.add(vent)
        return vent


class HoleManager(_CollectionManager):
    """Manage FDS holes (rectangular cutouts through obstructions)."""
    def __init__(self, api):
        from pyfds.domain.model import Hole
        super().__init__(api, Hole)

    def add_hole(self, xb: List[float], **kwargs) -> Any:
        from pyfds.domain.model import Hole
        hole = Hole(
            x_min=float(xb[0]), x_max=float(xb[1]),
            y_min=float(xb[2]), y_max=float(xb[3]),
            z_min=float(xb[4]), z_max=float(xb[5]),
            **kwargs,
        )
        self.add(hole)
        return hole


class GeomManager(BuildingGenerators):
    """
    High-level geometry manager: STL import, parametric primitives, voxelization.

    Accessible via ``api.geom``.
    """

    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    @property
    def _project(self):
        return self._api.project

    def all(self) -> List[Any]:
        """All &GEOM entities in the active project — matches the `.all()`
        contract every other manager exposes (ProjectExplorer/build_scene
        rely on it)."""
        return self._project.geoms

    def get(self, name: str) -> Any:
        """The ``&GEOM`` called *name*, or ``None``."""
        return next((g for g in self.all() if g.name == name), None)

    def remove(self, entity: Any) -> None:
        """Matches the `.remove(entity)` contract _on_delete_selected() calls
        generically via getattr(self.api, attr).remove(entity) for every
        entity collection — without this, deleting a Geom row in the
        Project Explorer would raise AttributeError."""
        from pyfds.automation.commands import RemoveEntityCommand
        self._api.history.execute(RemoveEntityCommand(self._project, entity))

    def load_stl(self, path: str, **kwargs) -> Any:
        """
        Load an STL file as a ``Geom`` entity and add it to the project.

        Returns the ``Geom``.
        """
        from pyfds.io.stl_importer import StlImporter
        from pyfds.automation.commands import AddEntityCommand
        geom = StlImporter.load(path, **kwargs)
        self._api.history.execute(AddEntityCommand(self._project, geom))
        return geom

    def import_file(self, path: str, **options) -> Any:
        """Import a CAD/mesh file (STL, OBJ, DXF 3DFACE) as a ``Geom`` (one undo step).

        Options: ``units`` (file units: m, mm, cm, in, ft ...), ``up_axis`` (``"Y"`` for Y-up files),
        ``translate``, ``scale``, ``surf_id``, ``name``."""
        from pyfds.io.mesh_importers import import_geometry
        from pyfds.automation.commands import AddEntityCommand
        geom = import_geometry(path, **options)
        self._api.history.execute(AddEntityCommand(self._project, geom))
        return geom

    def sphere(self, center, radius, **kwargs) -> Any:
        """Create a sphere ``Geom`` and add it to the project."""
        from pyfds.domain.geometry_tools import GeometryTools
        from pyfds.automation.commands import AddEntityCommand
        g = GeometryTools.sphere(center, radius, **kwargs)
        self._api.history.execute(AddEntityCommand(self._project, g))
        return g

    def cylinder(self, center_base, radius, height, **kwargs) -> Any:
        """Create a cylinder ``Geom`` and add it to the project."""
        from pyfds.domain.geometry_tools import GeometryTools
        from pyfds.automation.commands import AddEntityCommand
        g = GeometryTools.cylinder(center_base, radius, height, **kwargs)
        self._api.history.execute(AddEntityCommand(self._project, g))
        return g

    def cone(self, center_base, radius, height, **kwargs) -> Any:
        """Create a cone ``Geom`` and add it to the project."""
        from pyfds.domain.geometry_tools import GeometryTools
        from pyfds.automation.commands import AddEntityCommand
        g = GeometryTools.cone(center_base, radius, height, **kwargs)
        self._api.history.execute(AddEntityCommand(self._project, g))
        return g

    def box(self, xb, **kwargs) -> Any:
        """Create a triangulated box ``Geom`` and add it to the project."""
        from pyfds.domain.geometry_tools import GeometryTools
        from pyfds.automation.commands import AddEntityCommand
        g = GeometryTools.box_geom(xb, **kwargs)
        self._api.history.execute(AddEntityCommand(self._project, g))
        return g

    def extrude_polygon(self, polygon_xy, z_bottom, z_top, **kwargs) -> Any:
        """Extrude a 2-D polygon as a ``Geom`` and add it to the project."""
        from pyfds.domain.geometry_tools import GeometryTools
        from pyfds.automation.commands import AddEntityCommand
        g = GeometryTools.extrude_polygon(polygon_xy, z_bottom, z_top, **kwargs)
        self._api.history.execute(AddEntityCommand(self._project, g))
        return g

    def voxelize(
        self,
        geom_or_path,
        mesh=None,
        *,
        surf_id: str = "INERT",
        name_prefix: str = "vox",
        mode: str = "surface",
        add_to_project: bool = True,
    ) -> List[Any]:
        """
        Voxelise a ``Geom`` (or STL path) onto the first mesh in the project.

        Parameters
        ----------
        geom_or_path : Geom | str
        mesh : Mesh, optional
            Which mesh to use as grid.  Defaults to the first project mesh.
        surf_id, name_prefix, mode
            Forwarded to :func:`~pyfds.domain.voxelizer.Voxelizer.voxelize`.
        add_to_project : bool
            If True, add all generated ``Obstruction`` objects to the project.

        Returns
        -------
        list[Obstruction]
        """
        from pyfds.domain.voxelizer import Voxelizer
        if isinstance(geom_or_path, str):
            from pyfds.io.stl_importer import StlImporter
            geom_or_path = StlImporter.load(geom_or_path, surf_id=surf_id)
        if mesh is None:
            meshes = self._project.meshes
            if not meshes:
                raise RuntimeError("No meshes in project — add a mesh first.")
            mesh = meshes[0]
        obstructions = Voxelizer.voxelize(
            geom_or_path, mesh,
            surf_id=surf_id,
            name_prefix=name_prefix,
            mode=mode,
        )
        if add_to_project:
            from pyfds.automation.commands import AddEntityCommand
            for o in obstructions:
                self._api.history.execute(AddEntityCommand(self._project, o))
        return obstructions
