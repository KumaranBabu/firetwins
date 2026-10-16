"""Copy / paste of model objects as FDS text: ``api.clipboard`` (UX-03).

``copy`` puts the selected objects on an internal clipboard as FDS input text and returns it, so the
same text can be pasted into another model or into any text editor. ``paste_fds_text`` parses FDS
text (from this clipboard, a file or the web) and adds the objects as ONE undo step.

Name clashes: objects other things refer to by name (surfaces, materials, ramps, species ...) are
*reused* when the target already has one of that name; every other object is renamed ``NAME_2`` ...
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

#: Collections whose members are referred to by name from other objects: reuse on a clash.
_BY_REFERENCE = {
    "surfaces", "materials", "ramps", "species", "particles", "props", "controls", "devices", "zones",
    "mults", "moves", "reactions", "hvac_nodes", "hvac_ducts", "fans", "dampers", "hvac_filters",
    "hvac_leakages", "hvac_aircoils", "mesh_transforms",
}


def _shift(entity: Any, dx: float, dy: float, dz: float) -> None:
    for lo, hi, d in (("x_min", "x_max", dx), ("y_min", "y_max", dy), ("z_min", "z_max", dz)):
        if hasattr(entity, lo) and hasattr(entity, hi):
            setattr(entity, lo, getattr(entity, lo) + d)
            setattr(entity, hi, getattr(entity, hi) + d)
    for attr, d in (("x", dx), ("y", dy), ("z", dz)):
        if isinstance(getattr(entity, attr, None), (int, float)) and not isinstance(getattr(entity, attr), bool):
            setattr(entity, attr, getattr(entity, attr) + d)
    for attr in ("xyz", "xyz_center", "texture_origin"):
        v = getattr(entity, attr, None)
        if v and len(v) == 3:
            setattr(entity, attr, type(v)((v[0] + dx, v[1] + dy, v[2] + dz)))
    if getattr(entity, "verts", None):
        entity.verts = [(x + dx, y + dy, z + dz) for x, y, z in entity.verts]


class ClipboardManager:
    # -- merge a whole file ---------------------------------------------------------------------------------------
    def merge_file(self, path: str, categories: Optional[Sequence[str]] = None,
                   offset: Sequence[float] = (0.0, 0.0, 0.0)) -> Dict[str, Any]:
        """Add the objects of an ``.fds`` or ``.pyfds`` file to the open project (File > Import). One undo step;
        objects other things refer to by name are reused on a clash, the rest are renamed (see the module note).
        *categories* limits it (``["devices", "controls", "props"]``)."""
        from pathlib import Path
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"file not found: {path}")
        if p.suffix.lower() == ".pyfds":
            from pyfds.io.fds_writer import FdsWriter
            from pyfds.io.serializer import Serializer
            try:
                text = FdsWriter().to_string(Serializer().load(str(p)))
            except Exception as exc:
                raise ValueError(f"cannot read {p.name}: {exc}") from None
        else:
            text = p.read_text(encoding="utf-8", errors="replace")
        return self.paste_fds_text(text, offset, categories)

    def __init__(self, api) -> None:
        self._api = api
        self._text: str = ""

    # -- copy ------------------------------------------------------------------------
    @property
    def text(self) -> str:
        """What is on the clipboard (FDS input text)."""
        return self._text

    def to_fds_text(self, entities: Iterable[Any], include_dependencies: bool = False,
                    substitute: Optional[dict] = None) -> str:
        """FDS text for these objects. With *include_dependencies* the surfaces they use (and those
        surfaces' materials and ramps) are included, so the text pastes into an empty model.
        *substitute* maps ``id(object)`` to a stand-in written in its place (an editor's unsaved-edit preview)."""
        items = list(entities)
        if not items:
            raise ValueError("nothing to copy")
        p = self._api.project
        known = {e.uid for attr in set(p._TYPE_MAP.values()) for e in getattr(p, attr)}
        for e in items:
            if e.uid not in known:
                raise KeyError(f"{getattr(e, 'name', e)!r} is not in the project")
        if include_dependencies:
            items = self._with_dependencies(items)
        from pyfds.io.fds_writer import FdsWriter
        return "\n".join(FdsWriter().entity_records(p, items, substitute)) + "\n"

    def _with_dependencies(self, items: List[Any]) -> List[Any]:
        p = self._api.project
        out, seen = list(items), {id(e) for e in items}

        def add(e):
            if e is not None and id(e) not in seen:
                seen.add(id(e))
                out.append(e)

        by_name = lambda coll, n: next((x for x in getattr(p, coll) if x.name == n), None)
        for e in list(out):
            for sid in {getattr(e, "surface_id", None), *(getattr(e, "surface_ids", None) or [])} - {None}:
                s = by_name("surfaces", sid)
                if s is None:
                    continue
                add(s)
                for layer in s.layers:
                    add(by_name("materials", layer.material_id))
                for r in (s.ramp_q, s.ramp_t, s.ramp_v, s.ramp_mf):
                    add(by_name("ramps", r) if r else None)
        return out

    def copy(self, entities: Iterable[Any], include_dependencies: bool = False) -> str:
        """Copy to the clipboard; returns the FDS text."""
        self._text = self.to_fds_text(entities, include_dependencies)
        return self._text

    # -- paste -----------------------------------------------------------------------
    def paste(self, offset: Sequence[float] = (0.0, 0.0, 0.0)) -> Dict[str, Any]:
        """Paste the clipboard (see ``paste_fds_text``)."""
        if not self._text:
            raise ValueError("the clipboard is empty")
        return self.paste_fds_text(self._text, offset)

    def paste_fds_text(self, text: str, offset: Sequence[float] = (0.0, 0.0, 0.0),
                       categories: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        """Add the objects in FDS *text*, moved by *offset*. One undo step. *categories* limits what is taken to
        those collections (``["materials", "ramps"]``); everything else in the text is ignored.

        Returns ``{"added": [entities], "renamed": {old: new}, "skipped": [names reused], "warnings": [...]}``."""
        if len(offset) != 3:
            raise ValueError("offset needs three numbers (dx, dy, dz)")
        from pyfds.io.fds_parser import FdsParser
        parser = FdsParser()
        try:
            tmp = parser.parse_string(text)
        except Exception as exc:
            raise ValueError(f"cannot read the text as FDS input: {exc}") from None
        p = self._api.project
        report: Dict[str, Any] = {"added": [], "renamed": {}, "skipped": [], "warnings": list(parser.warnings)}
        from pyfds.automation.commands import AddEntityCommand
        plan = []
        wanted = set(categories) if categories is not None else None
        if wanted is not None:
            unknown = wanted - set(tmp._TYPE_MAP.values())
            if unknown:
                raise ValueError(f"unknown categories: {', '.join(sorted(unknown))}")
        for attr in sorted(set(tmp._TYPE_MAP.values())):
            if wanted is not None and attr not in wanted:
                continue
            existing = {e.name for e in getattr(p, attr)}
            for e in getattr(tmp, attr):
                name = getattr(e, "name", None)
                if name in existing and attr in _BY_REFERENCE:
                    report["skipped"].append(f"{attr}/{name}")
                    continue
                if name in existing:
                    new = name
                    i = 2
                    while new in existing:
                        new, i = f"{name}_{i}", i + 1
                    report["renamed"][name] = new
                    e.name = new
                existing.add(e.name)
                _shift(e, *[float(v) for v in offset])
                plan.append(e)
        if not plan and not report["skipped"]:
            what = f" of kind {', '.join(sorted(wanted))}" if wanted else ""
            raise ValueError(f"no FDS objects{what} found in the text")
        if plan:
            with self._api.history.transaction("paste"):
                for e in plan:
                    self._api.history.execute(AddEntityCommand(p, e))
        report["added"] = plan
        return report
