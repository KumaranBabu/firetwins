"""CAD/BIM import, repair and export on ``api.geom`` (B3: IMP-02, 03, 05, 07). A mixin for ``GeomManager``."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Union

from .species import _unique


class GeomImportOps:
    """Mixin for ``GeomManager`` (needs ``_api``, ``_project``, ``all()``, ``_geom()``)."""

    def import_file(self, path: str, **options) -> Any:
        """Import a CAD/mesh file as ``Geom`` shapes (one undo step).

        Formats: STL, OBJ, DXF (3DFACE), glTF/GLB, DAE (COLLADA), IFC. FBX and DWG are closed formats and
        refused with a message. Options: ``units`` (file units), ``up_axis`` (``"Y"`` for Y-up files;
        glTF defaults to Y), ``translate``, ``scale``, ``surf_id``, ``name``; IFC also ``types``
        (``["IfcWall", ...]``) and ``include_spaces``; ``merge=True`` joins an IFC into one ``Geom``.

        Returns one ``Geom``; an IFC with several elements returns a list (each has ``bim_type``).
        """
        from pathlib import Path
        from pyfds.automation.commands import AddEntityCommand
        from pyfds.io.mesh_importers import import_geometry_all, merge_geoms
        merge = options.pop("merge", False)
        isolated = options.pop("isolated", False)
        timeout = options.pop("timeout", 300.0)
        if isolated:
            # a parser crash or a hang on a damaged CAD file must not take the application down
            from pyfds.execution.isolated import run_isolated
            geoms = run_isolated("pyfds.io.mesh_importers:import_geometry_all", path, timeout=timeout, **options)
        else:
            geoms = import_geometry_all(path, **options)
        if merge and len(geoms) > 1:
            geoms = [merge_geoms(geoms, options.get("name") or Path(path).stem)]
        with self._api.history.transaction(f"import {Path(path).name}"):
            for g in geoms:
                g.name = _unique(self, g.name)
                self._api.history.execute(AddEntityCommand(self._project, g))
        return geoms[0] if len(geoms) == 1 else geoms

    # -- appearance (APP-03): the look an imported shape brings with it --------------------------------
    def look(self, geom_or_name) -> Optional[Dict[str, Any]]:
        """The shape's look (from a glTF material) as a dict, or ``None`` if it has none."""
        g = self._geom(geom_or_name)
        return g.look.model_dump() if g.look is not None else None

    def set_look(self, geom_or_name, **fields) -> Any:
        """Give a shape a look, or change fields of the one it has (``base_color``, ``opacity``, ``metallic``,
        ``roughness``, ``emissive``, ``double_sided``, ``name``). Validated; one undo step."""
        from pyfds.automation.commands import ModifyPropertyCommand
        from pyfds.domain.model import PbrLook
        g = self._geom(geom_or_name)
        merged = {**(g.look.model_dump() if g.look is not None else {}), **fields}
        new = PbrLook(**merged)                                  # pydantic refuses out-of-range values (ValueError)
        self._api.history.execute(ModifyPropertyCommand(g, "look", new))
        return new

    def clear_look(self, geom_or_name) -> None:
        """Remove a shape's look (it is then drawn in the plain default colour)."""
        from pyfds.automation.commands import ModifyPropertyCommand
        g = self._geom(geom_or_name)
        if g.look is None:
            raise ValueError(f"{g.name} has no look")
        self._api.history.execute(ModifyPropertyCommand(g, "look", None))

    # -- BIM (IMP-03) ----------------------------------------------------------------
    def bim_types(self) -> Dict[str, int]:
        """``{IFC class: number of shapes}`` for shapes that came from a BIM file."""
        out: Dict[str, int] = {}
        for g in self.all():
            if g.bim_type:
                out[g.bim_type] = out.get(g.bim_type, 0) + 1
        return dict(sorted(out.items()))

    def select_by_bim_type(self, *types: str, storey: Optional[str] = None) -> List[Any]:
        """The BIM shapes whose IFC class starts with one of *types* (``IfcWall`` also matches
        ``IfcWallStandardCase``; no types = all BIM shapes), optionally on one storey. Case-insensitive."""
        wanted = [t.lower() for t in types]
        return [g for g in self.all() if g.bim_type
                and (not wanted or any(g.bim_type.lower().startswith(w) for w in wanted))
                and (storey is None or g.bim_storey == storey)]

    def generate_from_bim(self, mesh=None, types: Sequence[str] = (), storey: Optional[str] = None,
                          surface_map: Optional[Dict[str, str]] = None, default_surf: str = "INERT",
                          mode: str = "solid", remove_geom: bool = True) -> List[Any]:
        """Turn imported BIM shapes into native obstructions on the mesh grid (one undo step).

        *types* / *storey* pick the shapes (default: all BIM shapes). *surface_map* gives a surface per
        IFC class (``{"IfcWall": "GYPSUM"}``); others use *default_surf*. With *remove_geom* the source
        shapes are deleted."""
        shapes = self.select_by_bim_type(*types, storey=storey)
        if not shapes:
            raise ValueError("no BIM shapes match; import an IFC first (or check the type / storey)")
        smap = {k.lower(): v for k, v in (surface_map or {}).items()}
        out: List[Any] = []
        with self._api.history.transaction("generate model from BIM"):
            for g in shapes:
                surf = next((v for k, v in smap.items() if g.bim_type.lower().startswith(k)), default_surf)
                out += self.convert_to_blocks(g, mesh, mode=mode, surf_id=surf, name_prefix=g.name,
                                              remove_geom=remove_geom)
        return out

    # -- repair (IMP-05) ---------------------------------------------------------------
    def check_geometry(self, geom_or_name) -> Dict[str, Any]:
        """Problems in a shape: degenerate/duplicate triangles, open and non-manifold edges, volume."""
        from pyfds.domain.geometry_repair import inspect
        g = self._geom(geom_or_name)
        return inspect(g.verts or [], g.faces or [])

    def repair(self, geom_or_name, weld_tol: float = 1e-6, orient: bool = True,
               outward: bool = True) -> Dict[str, Any]:
        """Weld vertices, drop degenerate/duplicate/unused pieces and fix the winding (one undo step).
        Returns a report with the numbers before and after."""
        from pyfds.automation.commands import GroupCommand, ModifyPropertyCommand
        from pyfds.domain.geometry_repair import repair
        g = self._geom(geom_or_name)
        verts, faces, report = repair(g.verts or [], g.faces or [], weld_tol=weld_tol, orient=orient,
                                      outward=outward)
        if not faces:
            raise ValueError(f"{g.name}: nothing is left after repair (all triangles were degenerate)")
        self._api.history.execute(GroupCommand(
            [ModifyPropertyCommand(g, "verts", verts), ModifyPropertyCommand(g, "faces", faces)],
            label=f"repair {g.name}"))
        return report

    def rescale(self, geom_or_name, factor: float, about: Optional[Sequence[float]] = None) -> Any:
        """Rescale an imported shape (fix a wrong-units import) about *about* (default: its minimum corner)."""
        from pyfds.automation.commands import ModifyPropertyCommand
        if factor <= 0:
            raise ValueError("factor must be positive")
        g = self._geom(geom_or_name)
        bb = g.bbox()
        ox, oy, oz = about if about is not None else (bb[0], bb[2], bb[4])
        verts = [(ox + (x - ox) * factor, oy + (y - oy) * factor, oz + (z - oz) * factor) for x, y, z in g.verts]
        self._api.history.execute(ModifyPropertyCommand(g, "verts", verts))
        return g

    # -- export (IMP-07) -----------------------------------------------------------------
    def export_geometry(self, path: str, geoms: Union[None, Sequence[Any]] = None,
                        include_obstructions: bool = False, units: str = "m", up_axis: str = "Z",
                        ascii_stl: bool = False) -> int:
        """Write shapes to ``.stl`` or ``.obj`` (by extension); returns the triangle count.

        *geoms* are ``Geom`` objects or names (default: all); with *include_obstructions* every ``&OBST``
        is written as a box too."""
        from pathlib import Path
        from pyfds.io import geometry_export as ge
        ext = Path(path).suffix.lower()
        if ext not in (".stl", ".obj"):
            raise ValueError("export format must be .stl or .obj")
        chosen = self.all() if geoms is None else [self._geom(g) for g in geoms]
        obsts = self._project.obstructions if include_obstructions else []
        shapes = ge.collect(chosen, obsts)
        if ext == ".stl":
            return ge.write_stl(path, shapes, units=units, up_axis=up_axis, ascii_format=ascii_stl)
        return ge.write_obj(path, shapes, units=units, up_axis=up_axis)
