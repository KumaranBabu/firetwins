"""Library files in FDS syntax and the appearance library (B5: SPC-04, FIO-05, RXN-06, SRF-10, APP-01, LIB-02).

``import_fds`` reads any FDS input file (a ``property_library.fds`` or a whole model) and offers its
materials, surfaces, reactions, species, particles and PROP records as user library entries.
``export_fds`` writes library entries as plain FDS records, so the file can be pasted into a model or
read by another tool. Appearances (colour, transparency, texture and its tiling) are a small library
of their own that can be applied to surfaces.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pyfds.domain import libraries as lib

_DROP = ("name", "enabled", "tags", "fds_extra")

#: Appearance fields, all of them fields of a surface.
APPEARANCE_FIELDS = ("color", "rgb", "transparency", "texture_map", "texture_width", "texture_height")

#: FDS colour names with their RGB, offered as ready appearances (subset of the FDS colour table).
_BUILTIN_APPEARANCES: Dict[str, Dict[str, Any]] = {
    "gray": {"color": "GRAY", "rgb": (128, 128, 128)},
    "white": {"color": "WHITE", "rgb": (255, 255, 255)},
    "black": {"color": "BLACK", "rgb": (0, 0, 0)},
    "red": {"color": "RED", "rgb": (255, 0, 0)},
    "blue": {"color": "BLUE", "rgb": (0, 0, 255)},
    "green": {"color": "GREEN", "rgb": (0, 255, 0)},
    "yellow": {"color": "YELLOW", "rgb": (255, 255, 0)},
    "brick": {"color": "BRICK", "rgb": (156, 102, 31)},
    "glass": {"color": "LIGHT BLUE", "rgb": (173, 216, 230), "transparency": 0.7},
    "concrete": {"color": "GRAY", "rgb": (169, 169, 169)},
    "wood": {"color": "BROWN", "rgb": (160, 110, 60)},
}


class LibraryFiles:
    """Mixin for :class:`LibraryManager`."""

    # -- FDS files -------------------------------------------------------------------
    def import_fds(self, filepath: str, categories: Optional[List[str]] = None,
                   overwrite: bool = False, text: Optional[str] = None) -> Dict[str, Any]:
        """Add the definitions of an FDS input file to the user library.

        *categories* limits what is taken (default: all nine). Returns the usual
        ``{"added", "replaced", "skipped", "invalid"}`` report plus ``"missing_ramps"``: RAMP IDs the
        imported entries refer to but the library cannot hold (ramps are not library items)."""
        from pyfds.io.fds_parser import FdsParser
        parser = FdsParser()
        project = parser.parse_string(text) if text is not None else parser.parse(filepath)
        cats = categories or list(lib.CATEGORIES)
        doc: Dict[str, Dict[str, Any]] = {}
        ramps = set()
        for key in cats:
            c = self._cat(key)
            entries = {}
            for e in getattr(project, c.collection):
                if not lib.matches(c, e):
                    continue
                fields = e.model_dump(mode="json", exclude_defaults=True)
                for k in _DROP:
                    fields.pop(k, None)
                entries[e.name] = {"description": "", "fields": fields}
                ramps |= {v for k, v in fields.items() if k.startswith("ramp") and isinstance(v, str)}
            if entries:
                doc[key] = entries
        report = self._merge(lib.to_document(doc), overwrite)
        known = {r.name for r in getattr(project, "ramps", [])}
        report["missing_ramps"] = sorted(ramps)
        report["ramps_in_file"] = sorted(ramps & known)
        report["warnings"] = list(parser.warnings)
        return report

    def export_fds(self, filepath: str, categories: Optional[List[str]] = None, include_builtin: bool = False,
                   names: Optional[List[str]] = None) -> int:
        """Write library entries as FDS records (``&MATL``, ``&SURF``, ``&REAC``, ``&SPEC``, ``&PART``, ``&PROP``).
        *names* restricts the entries. Returns the number written. User entries shadow built-ins."""
        from pyfds.domain.model import FdsProject
        from pyfds.io.fds_writer import FdsWriter
        proj = FdsProject()
        for key in categories or list(lib.CATEGORIES):
            c = self._cat(key)
            pool = dict(lib.builtin_entries(key)) if include_builtin else {}
            pool.update(self._user[key])
            for n, entry in sorted(pool.items()):
                if names is not None and n not in names:
                    continue
                ent = self._make(key, n, n)
                getattr(proj, c.collection).append(ent)
        w = FdsWriter()
        lines: List[str] = []
        count = 0
        for tag, coll, fn in w._entity_table(proj):
            if tag in ("MATL", "REAC", "SPEC", "SURF", "PART", "PROP"):
                for e in coll:
                    lines.append(fn(e))
                    count += 1
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write("! PyFDS property library\n" + "\n".join(lines) + "\n")
        return count

    # -- appearances -----------------------------------------------------------------
    def _appearance_store(self) -> Dict[str, Dict[str, Any]]:
        if not hasattr(self, "_appearances"):
            self._appearances: Dict[str, Dict[str, Any]] = {}
        return self._appearances

    def appearance_names(self, source: str = "all") -> List[str]:
        names = set()
        if source in ("all", "builtin"):
            names |= set(_BUILTIN_APPEARANCES)
        if source in ("all", "user"):
            names |= set(self._appearance_store())
        return sorted(names)

    def appearance(self, name: str) -> Dict[str, Any]:
        store = self._appearance_store()
        if name in store:
            return {**store[name], "source": "user"}
        if name in _BUILTIN_APPEARANCES:
            return {**_BUILTIN_APPEARANCES[name], "source": "builtin"}
        raise KeyError(f"no appearance {name!r}; choose from {', '.join(self.appearance_names())}")

    def add_appearance(self, name: str, color: str = "GRAY", rgb=None, transparency: float = 0.0,
                       texture_map: Optional[str] = None, texture_width: Optional[float] = None,
                       texture_height: Optional[float] = None, overwrite: bool = False) -> str:
        """Define a user appearance. ``texture_width/height`` are the size one tile of the texture covers (m)."""
        if not 0.0 <= transparency <= 1.0:
            raise ValueError("transparency is between 0 (opaque) and 1 (invisible)")
        if rgb is not None and (len(rgb) != 3 or any(not 0 <= int(v) <= 255 for v in rgb)):
            raise ValueError("rgb is three values from 0 to 255")
        for v in (texture_width, texture_height):
            if v is not None and v <= 0:
                raise ValueError("texture tile size must be positive")
        store = self._appearance_store()
        if name in store and not overwrite:
            raise ValueError(f"appearance {name!r} exists; pass overwrite=True")
        entry: Dict[str, Any] = {"color": color, "transparency": float(transparency)}
        for k, v in (("rgb", tuple(int(x) for x in rgb) if rgb is not None else None), ("texture_map", texture_map),
                     ("texture_width", texture_width), ("texture_height", texture_height)):
            if v is not None:
                entry[k] = v
        store[name] = entry
        self._autosave()
        return name

    def remove_appearance(self, name: str) -> None:
        store = self._appearance_store()
        if name not in store:
            raise KeyError(f"no user appearance {name!r} (built-in ones cannot be removed)")
        del store[name]
        self._autosave()

    def appearance_from_surface(self, surface: str, name: Optional[str] = None, overwrite: bool = False) -> str:
        """Save a surface's look as an appearance (Add to Library)."""
        s = self._api.surfaces.get(surface)
        if s is None:
            raise KeyError(f"surface {surface!r} not found")
        return self.add_appearance(name or surface, s.color, s.rgb, s.transparency, s.texture_map,
                                   s.texture_width, s.texture_height, overwrite)

    def apply_appearance(self, appearance: str, surfaces: List[str]) -> List[str]:
        """Give the named surfaces this look: one undo step. Fields the appearance does not set are reset."""
        look = self.appearance(appearance)
        values = {k: look.get(k) for k in APPEARANCE_FIELDS}
        values["transparency"] = look.get("transparency", 0.0)
        values["color"] = look.get("color", "GRAY")
        self._api.surfaces.update_many(surfaces, **values)
        return list(surfaces)
