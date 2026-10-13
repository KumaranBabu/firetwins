"""IFC (BIM) importer: one ``Geom`` per building element, tagged with its IFC type and storey (IMP-02/03).

Needs the optional ``ifcopenshell`` package. Registered by ``mesh_importers`` for ``.ifc``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Sequence

from .mesh_importers import IMPORTERS, _finish

#: element types that are not physical shapes, skipped unless asked for
_SKIP = ("IfcOpeningElement", "IfcSpace", "IfcAnnotation", "IfcGrid", "IfcVirtualElement")


def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-]+", "_", text).strip("_") or "element"


class IfcImporter:
    @staticmethod
    def load(path: str, *, surf_id: str = "INERT", name: Optional[str] = None, units: str = "m",
             up_axis: str = "Z", translate: Optional[Sequence[float]] = None, scale: float = 1.0,
             types: Optional[Sequence[str]] = None, include_spaces: bool = False) -> List:
        """Every element with a body shape becomes a ``Geom`` named ``<Type>_<element name>`` with
        ``bim_type``, ``bim_name`` and ``bim_storey`` set. *types* limits the import to some IFC classes
        (``["IfcWall", "IfcSlab"]``); *include_spaces* also brings in ``IfcSpace`` volumes.
        The file's own length unit is applied, so *units* stays ``"m"`` (it only matters for an IFC with
        no unit information)."""
        try:
            import ifcopenshell
            import ifcopenshell.geom
            import ifcopenshell.util.element as ue
            import ifcopenshell.util.unit as uu
        except ImportError:
            raise ValueError("IFC import needs the 'ifcopenshell' package (pip install ifcopenshell)") from None
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"IFC file not found: {p}")
        model = ifcopenshell.open(str(p))
        file_scale = uu.calculate_unit_scale(model)          # the file's length unit in metres
        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", True)
        wanted = {t.lower() for t in types} if types else None
        skip = {s.lower() for s in _SKIP if not (include_spaces and s == "IfcSpace")}
        out, used = [], set()
        for el in model.by_type("IfcProduct"):
            cls = el.is_a()
            if cls.lower() in skip or getattr(el, "Representation", None) is None:
                continue
            if wanted and not any(el.is_a(t) for t in types):
                continue
            try:
                shape = ifcopenshell.geom.create_shape(settings, el)
            except Exception:
                continue                                   # unsupported representation: skip, don't abort
            v, f = shape.geometry.verts, shape.geometry.faces
            if not f:
                continue
            verts = [(v[i], v[i + 1], v[i + 2]) for i in range(0, len(v), 3)]
            faces = [(f[i], f[i + 1], f[i + 2]) for i in range(0, len(f), 3)]
            label = getattr(el, "Name", None) or el.GlobalId
            gname = base = _safe(f"{cls[3:]}_{label}")
            n = 1
            while gname in used:
                n += 1
                gname = f"{base}_{n}"
            used.add(gname)
            container = ue.get_container(el)
            storey = container.Name if container is not None and container.is_a("IfcBuildingStorey") else None
            g = _finish(verts, faces, p, surf_id=surf_id, name=gname, units=units, up_axis=up_axis,
                        translate=translate, scale=scale * file_scale)
            g.bim_type, g.bim_name, g.bim_storey, g.source_file = cls, label, storey, p.name
            out.append(g)
        if not out:
            raise ValueError(f"{p.name}: no building elements with geometry found")
        return out


IMPORTERS[".ifc"] = IfcImporter.load
