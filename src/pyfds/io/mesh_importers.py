"""CAD / mesh file importers: OBJ and DXF (3DFACE), behind one registry (IMP-02).

Every importer returns a :class:`~pyfds.domain.model.Geom` (triangles only, vertices welded), after
applying ``units`` (file units -> metres), ``up_axis`` (``"Y"`` rotates a Y-up file to FDS's Z-up) and an
optional translation, exactly like :class:`~pyfds.io.stl_importer.StlImporter`.

Supported: ``.stl`` (ASCII/binary), ``.obj`` (Wavefront), ``.dxf`` (ASCII, ``3DFACE`` entities).
Not yet: IFC, FBX, DWG, DAE, glTF - ``import_geometry`` says so rather than guessing.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .stl_importer import StlImporter

logger = logging.getLogger(__name__)

Vec = Tuple[float, float, float]

UNITS = {"m": 1.0, "mm": 0.001, "cm": 0.01, "dm": 0.1, "km": 1000.0, "in": 0.0254, "ft": 0.3048, "yd": 0.9144}
#: DXF $INSUNITS codes (AutoCAD) -> unit name
_DXF_UNITS = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m", 7: "km", 14: "dm"}


def unit_factor(units: str) -> float:
    try:
        return UNITS[units.lower()]
    except KeyError:
        raise ValueError(f"unknown units {units!r}; choose from {', '.join(UNITS)}") from None


def _finish(verts: List[Vec], faces: List[Tuple[int, int, int]], path: Path, *, surf_id: str,
            name: Optional[str], units: str, up_axis: str, translate: Optional[Sequence[float]],
            scale: float, weld: bool = True):
    from pyfds.domain.model import Geom
    if up_axis.upper() not in ("Y", "Z"):
        raise ValueError("up_axis must be 'Y' or 'Z'")
    if not faces:
        raise ValueError(f"{path.name}: no triangles found")
    k = unit_factor(units) * scale
    pts = [(x * k, y * k, z * k) for x, y, z in verts]
    if up_axis.upper() == "Y":                                  # (x, y, z) Y-up  ->  (x, -z, y) Z-up
        pts = [(x, -z, y) for x, y, z in pts]
    if translate:
        dx, dy, dz = translate
        pts = [(x + dx, y + dy, z + dz) for x, y, z in pts]
    if weld:
        pts, faces = StlImporter._weld(pts, faces)
    if not faces:
        raise ValueError(f"{path.name}: every triangle is degenerate")
    return Geom(name=name or path.stem, surf_id=surf_id, verts=pts, faces=faces)


# -- OBJ ---------------------------------------------------------------------------------------
class ObjImporter:
    @staticmethod
    def load(path: str, *, surf_id: str = "INERT", name: Optional[str] = None, units: str = "m",
             up_axis: str = "Z", translate: Optional[Sequence[float]] = None, scale: float = 1.0):
        """Wavefront OBJ: ``v`` and ``f`` lines (polygons are fanned into triangles; normals, texture
        coordinates, materials and groups are ignored)."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"OBJ file not found: {p}")
        verts: List[Vec] = []
        faces: List[Tuple[int, int, int]] = []
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            parts = line.split("#", 1)[0].split()
            if not parts:
                continue
            if parts[0] == "v":
                try:
                    verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except (ValueError, IndexError):
                    raise ValueError(f"{p.name} line {n}: bad vertex {line.strip()!r}") from None
            elif parts[0] == "f":
                idx = []
                for tok in parts[1:]:
                    try:
                        i = int(tok.split("/")[0])
                    except ValueError:
                        raise ValueError(f"{p.name} line {n}: bad face index {tok!r}") from None
                    i = i - 1 if i > 0 else len(verts) + i      # negative = relative to the end
                    if not 0 <= i < len(verts):
                        raise ValueError(f"{p.name} line {n}: face refers to missing vertex {tok}")
                    idx.append(i)
                if len(idx) < 3:
                    raise ValueError(f"{p.name} line {n}: a face needs at least 3 vertices")
                faces.extend((idx[0], idx[k], idx[k + 1]) for k in range(1, len(idx) - 1))
        return _finish(verts, faces, p, surf_id=surf_id, name=name, units=units, up_axis=up_axis,
                       translate=translate, scale=scale)


# -- DXF ---------------------------------------------------------------------------------------
class DxfImporter:
    @staticmethod
    def load(path: str, *, surf_id: str = "INERT", name: Optional[str] = None, units: Optional[str] = None,
             up_axis: str = "Z", translate: Optional[Sequence[float]] = None, scale: float = 1.0):
        """ASCII DXF ``3DFACE`` entities (triangles and quads). *units* defaults to the file's
        ``$INSUNITS`` when it has one, else metres."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"DXF file not found: {p}")
        raw = p.read_bytes()
        if raw.startswith(b"AutoCAD Binary DXF"):
            raise ValueError(f"{p.name}: binary DXF is not supported; save as ASCII DXF")
        lines = raw.decode("utf-8", errors="replace").splitlines()
        if len(lines) % 2:
            lines.append("")
        pairs = [(lines[i].strip(), lines[i + 1].strip()) for i in range(0, len(lines), 2)]
        file_units = None
        for i, (code, val) in enumerate(pairs):
            if code == "9" and val == "$INSUNITS" and i + 1 < len(pairs):
                try:
                    file_units = _DXF_UNITS.get(int(pairs[i + 1][1]))
                except ValueError:
                    pass
        verts: List[Vec] = []
        faces: List[Tuple[int, int, int]] = []
        i, other = 0, set()
        while i < len(pairs):
            code, val = pairs[i]
            if code == "0" and val == "3DFACE":
                i += 1
                c: Dict[str, float] = {}
                while i < len(pairs) and pairs[i][0] != "0":
                    try:
                        c[pairs[i][0]] = float(pairs[i][1])
                    except ValueError:
                        pass
                    i += 1
                try:
                    pts = [(c[str(10 + k)], c[str(20 + k)], c[str(30 + k)]) for k in range(4)]
                except KeyError:
                    raise ValueError(f"{p.name}: a 3DFACE is missing coordinates") from None
                base = len(verts)
                if pts[3] == pts[2]:
                    verts.extend(pts[:3])
                    faces.append((base, base + 1, base + 2))
                else:
                    verts.extend(pts)
                    faces.extend([(base, base + 1, base + 2), (base, base + 2, base + 3)])
                continue
            if code == "0":
                other.add(val)
            i += 1
        if not faces:
            kinds = sorted(other & {"MESH", "POLYLINE", "SOLID", "3DSOLID", "LWPOLYLINE", "LINE", "INSERT"})
            hint = f" (found {', '.join(kinds)} - export the model as 3DFACE, STL or OBJ)" if kinds else ""
            raise ValueError(f"{p.name}: no 3DFACE entities{hint}")
        return _finish(verts, faces, p, surf_id=surf_id, name=name, units=units or file_units or "m",
                       up_axis=up_axis, translate=translate, scale=scale)


def _load_stl(path, *, surf_id="INERT", name=None, units="m", up_axis="Z", translate=None, scale=1.0):
    from pyfds.domain.model import Geom
    g = StlImporter.load(path, surf_id=surf_id, name=name)
    return _finish(list(g.verts), [tuple(f) for f in g.faces], Path(path), surf_id=surf_id, name=g.name,
                   units=units, up_axis=up_axis, translate=translate, scale=scale, weld=False)


#: extension -> loader; extend with ``IMPORTERS[".ext"] = fn`` (Strategy registry)
IMPORTERS: Dict[str, Callable] = {".stl": _load_stl, ".obj": ObjImporter.load, ".dxf": DxfImporter.load}
_PLANNED = {".ifc", ".fbx", ".dwg", ".dae", ".gltf", ".glb"}


def supported_formats() -> List[str]:
    return sorted(IMPORTERS)


def import_geometry(path: str, **options):
    """Load a CAD/mesh file by its extension; returns a ``Geom``."""
    ext = Path(path).suffix.lower()
    if ext in IMPORTERS:
        return IMPORTERS[ext](path, **options)
    if ext in _PLANNED:
        raise ValueError(f"{ext} import is not available yet; export the model as "
                         f"{' / '.join(supported_formats())} and import that")
    raise ValueError(f"unknown file type {ext!r}; supported: {', '.join(supported_formats())}")
