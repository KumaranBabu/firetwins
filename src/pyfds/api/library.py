"""Libraries of reusable definitions: ``api.library`` (LIB-01, MAT-05).

Built-in entries come from the preset tables; user entries are held here and can be exported to
and imported from JSON. ``add_to_model`` / ``add_to_library`` move definitions between the project
and the library. Nothing is written to disk unless you call ``save`` / ``export_library``.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from pyfds.domain import libraries as lib

from .library_files import LibraryFiles


class LibraryManager(LibraryFiles):
    def __init__(self, api) -> None:
        self._api = api
        self._user: Dict[str, Dict[str, Dict[str, Any]]] = {k: {} for k in lib.CATEGORIES}
        self.path: Optional[str] = None            # set to make the user library persistent

    # -- reading ---------------------------------------------------------------------
    def _cat(self, category: str) -> lib.Category:
        try:
            return lib.CATEGORIES[category]
        except KeyError:
            raise KeyError(f"unknown library category {category!r}; choose from {', '.join(lib.CATEGORIES)}") from None

    def categories(self) -> List[Dict[str, Any]]:
        out = []
        for k, c in lib.CATEGORIES.items():
            out.append({"key": k, "label": c.label, "builtin": len(lib.builtin_entries(k)), "user": len(self._user[k])})
        return out

    def names(self, category: str, source: str = "all") -> List[str]:
        self._cat(category)
        if source not in ("all", "builtin", "user"):
            raise ValueError("source must be all, builtin or user")
        names = set()
        if source in ("all", "builtin"):
            names |= set(lib.builtin_entries(category))
        if source in ("all", "user"):
            names |= set(self._user[category])
        return sorted(names)

    def get(self, category: str, name: str) -> Dict[str, Any]:
        """The entry ``{"description", "fields", "source"}``; a user entry shadows a built-in of the same name."""
        self._cat(category)
        if name in self._user[category]:
            return {**self._user[category][name], "source": "user"}
        built = lib.builtin_entries(category)
        if name in built:
            return {**built[name], "source": "builtin"}
        raise KeyError(f"{category} library has no entry {name!r}")

    # -- library -> model ------------------------------------------------------------
    def _make(self, category: str, name: str, new_name: Optional[str] = None):
        from pyfds.domain import model
        c = self._cat(category)
        entry = self.get(category, name)
        cls = getattr(model, c.entity)
        return cls(name=new_name or name.upper().replace(" ", "_").replace("-", "_"), **entry["fields"])

    def add_to_model(self, category: str, name: str, new_name: Optional[str] = None) -> Any:
        """Create the entity in the project (one undo step). A surface also brings the library materials
        its layers use if the project lacks them. Refuses to duplicate an existing ID."""
        c = self._cat(category)
        entity = self._make(category, name, new_name)
        collection = getattr(self._api.project, c.collection)
        if any(e.name == entity.name for e in collection):
            raise ValueError(f"{c.entity} {entity.name!r} already exists in the project; pass new_name=")
        from pyfds.automation.commands import AddEntityCommand
        with self._api.history.transaction(f"add {entity.name} from library"):
            if category == "surfaces":
                have = {m.name for m in self._api.project.materials}
                for layer in entity.layers:
                    if layer.material_id in have:
                        continue
                    key = next((n for n in self.names("materials") if n.upper() == layer.material_id), None)                         or lib.MATERIAL_ALIASES.get(layer.material_id)
                    if key is not None:     # named as the layer calls it, so the reference resolves
                        self._api.history.execute(AddEntityCommand(
                            self._api.project, self._make("materials", key, layer.material_id)))
                        have.add(layer.material_id)
            self._api.history.execute(AddEntityCommand(self._api.project, entity))
        return entity

    # -- model -> library ------------------------------------------------------------
    def candidates(self, category: str) -> List[str]:
        """Names of the project's objects that can be saved into *category* (``add_to_library`` accepts them)."""
        c = self._cat(category)
        return [e.name for e in getattr(self._api.project, c.collection) if lib.matches(c, e)]

    def add_to_library(self, category: str, entity_or_name, name: Optional[str] = None,
                       overwrite: bool = False, description: str = "") -> str:
        """Save a project entity as a user library entry; returns the entry name."""
        c = self._cat(category)
        entity = entity_or_name
        if isinstance(entity_or_name, str):
            entity = next((e for e in getattr(self._api.project, c.collection) if e.name == entity_or_name), None)
            if entity is None:
                raise KeyError(f"{c.entity} {entity_or_name!r} not found in the project")
        if not lib.matches(c, entity):
            raise ValueError(f"{entity.name!r} is not a {c.label.lower().rstrip('s')}")
        key = name or entity.name
        if key in self._user[category] and not overwrite:
            raise ValueError(f"{category} library already has {key!r}; pass overwrite=True")
        fields = entity.model_dump(mode="json", exclude_defaults=True)
        for k in ("name", "enabled", "tags", "fds_extra"):
            fields.pop(k, None)
        self._user[category][key] = {"description": description, "fields": fields}
        self._autosave()
        return key

    def remove_from_library(self, category: str, name: str) -> None:
        self._cat(category)
        if name not in self._user[category]:
            raise KeyError(f"no user entry {name!r} in {category} (built-in entries cannot be removed)")
        del self._user[category][name]
        self._autosave()

    # -- files -----------------------------------------------------------------------
    def export_library(self, filepath: str, categories: Optional[List[str]] = None, include_builtin: bool = False) -> int:
        """Write user entries (and optionally built-ins) to a JSON file; returns the number of entries."""
        cats = categories or list(lib.CATEGORIES)
        out: Dict[str, Dict[str, Any]] = {}
        for k in cats:
            self._cat(k)
            entries = dict(lib.builtin_entries(k)) if include_builtin else {}
            entries.update(self._user[k])
            if entries:
                out[k] = entries
        with open(filepath, "w", encoding="utf-8") as fh:
            doc = lib.to_document(out)
            if self._appearance_store() and categories is None:
                doc["appearances"] = self._appearance_store()
            json.dump(doc, fh, indent=2)
        return sum(len(v) for v in out.values()) + (len(self._appearance_store()) if categories is None else 0)

    def import_library(self, filepath: str, overwrite: bool = False) -> Dict[str, List[Any]]:
        """Merge a library file into the user library. Returns ``{"added", "replaced", "skipped", "invalid"}``;
        a bad entry is reported, never fatal, and a bad file changes nothing."""
        with open(filepath, "r", encoding="utf-8") as fh:
            try:
                doc = json.load(fh)
            except json.JSONDecodeError as exc:
                raise ValueError(f"not valid JSON: {exc}") from None
        return self._merge(doc, overwrite)

    def _merge(self, doc: Dict[str, Any], overwrite: bool) -> Dict[str, List[Any]]:
        bad = lib.check_document(doc)
        if bad:
            raise ValueError("; ".join(bad))
        report: Dict[str, List[Any]] = {"added": [], "replaced": [], "skipped": [], "invalid": []}
        for name, look in (doc.get("appearances") or {}).items():
            store = self._appearance_store()
            if name in store and not overwrite:
                report["skipped"].append(f"appearances/{name}")
            elif isinstance(look, dict):
                report["replaced" if name in store else "added"].append(f"appearances/{name}")
                store[name] = {k: (tuple(v) if k == "rgb" else v) for k, v in look.items() if k in
                               ("color", "rgb", "transparency", "texture_map", "texture_width", "texture_height")}
            else:
                report["invalid"].append({"category": "appearances", "name": name, "reason": "entry must be an object"})
        for cat, entries in doc["categories"].items():
            if cat not in lib.CATEGORIES or not isinstance(entries, dict):
                report["invalid"].append({"category": cat, "reason": "unknown category"})
                continue
            for name, entry in entries.items():
                why, coerced = self._invalid(cat, name, entry)
                if why:
                    report["invalid"].append({"category": cat, "name": name, "reason": why})
                    continue
                entry = {**entry, "fields": coerced}
                exists = name in self._user[cat]
                if exists and not overwrite:
                    report["skipped"].append(f"{cat}/{name}")
                    continue
                self._user[cat][name] = {"description": entry.get("description", ""), "fields": dict(entry["fields"])}
                report["replaced" if exists else "added"].append(f"{cat}/{name}")
        self._autosave()
        return report

    def import_table(self, category: str, filepath: str, overwrite: bool = False) -> Dict[str, List[Any]]:
        """Import a table written by ``api.engineering.export_*`` (JSON ``{name: {field: value}}`` or CSV with a
        ``name`` column) as user entries of *category*. Blank CSV cells are left out."""
        import csv
        self._cat(category)
        if filepath.lower().endswith(".csv"):
            with open(filepath, newline="", encoding="utf-8") as fh:
                table = {r.pop("name"): {k: v for k, v in r.items() if v not in ("", None)}
                         for r in csv.DictReader(fh) if r.get("name")}
        else:
            with open(filepath, encoding="utf-8") as fh:
                table = json.load(fh)
        if not isinstance(table, dict):
            raise ValueError("expected a table of {name: {field: value}}")
        doc = lib.to_document({category: {
            n: {"description": (f or {}).pop("description", "") if isinstance(f, dict) else "", "fields": f}
            for n, f in table.items()}})
        return self._merge(doc, overwrite)

    def _invalid(self, category: str, name: str, entry: Any):
        """``(reason, coerced_fields)``: reason is None when the entry builds a valid entity; the coerced
        fields have the right types (a CSV cell ``'2280.0'`` becomes ``2280.0``)."""
        if not isinstance(entry, dict) or not isinstance(entry.get("fields"), dict):
            return "entry needs a 'fields' object", None
        try:
            ent = self._make_from(category, name, entry["fields"])
        except Exception as exc:                        # pydantic validation error
            return str(exc).splitlines()[0][:120], None
        dumped = ent.model_dump(mode="json")
        return None, {k: dumped[k] for k in entry["fields"] if k in dumped} |             {k: v for k, v in entry["fields"].items() if k not in dumped}

    def _make_from(self, category: str, name: str, fields: dict):
        from pyfds.domain import model
        return getattr(model, self._cat(category).entity)(name=name, **fields)

    # -- persistence -----------------------------------------------------------------
    def save(self, filepath: Optional[str] = None) -> str:
        """Write the user library; with no argument uses (and requires) ``self.path``."""
        target = filepath or self.path
        if not target:
            raise ValueError("no path set: pass filepath or set api.library.path")
        self.export_library(target)
        return target

    def load(self, filepath: Optional[str] = None) -> Dict[str, List[Any]]:
        target = filepath or self.path
        if not target:
            raise ValueError("no path set: pass filepath or set api.library.path")
        if not os.path.exists(target):
            return {"added": [], "replaced": [], "skipped": [], "invalid": []}
        return self.import_library(target, overwrite=True)

    @staticmethod
    def default_path() -> str:
        """Where the user library lives: ``$PYFDS_USER_DIR`` if set, else ``user_data/`` beside the application folder
        (never the user profile). The file is ``user_library.json``."""
        base = os.environ.get("PYFDS_USER_DIR")
        if not base:
            here = os.path.abspath(__file__)
            base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here)))), "user_data")
        return os.path.join(base, "user_library.json")

    def use_default_path(self) -> Optional[Dict[str, List[Any]]]:
        """Make the user library persistent at ``default_path()``: load what is there and save every later change.
        Returns the load report, or ``None`` (and stays in-memory) if the file cannot be read or the folder written."""
        target = self.default_path()
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            report = self.load(target)
        except (OSError, ValueError, KeyError):
            return None
        self.path = target
        return report

    def _autosave(self) -> None:
        if self.path:
            self.save()
