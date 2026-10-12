"""Libraries of reusable definitions (LIB-01, MAT-05)."""
from __future__ import annotations

from typing import List

from .base import ToolSpec

_STR = {"type": "string"}
_CAT = {"type": "string", "enum": ["reactions", "heat_detectors", "materials", "particles", "smoke_detectors",
                                   "species", "spray_models", "sprinkler_links", "surfaces"]}


def _spec(name, description, props, required, handler, mutates=True):
    return ToolSpec(name=name, description=description,
                    input_schema={"type": "object", "properties": props, "required": required},
                    handler=handler, mutates=mutates)


TOOLS: List[ToolSpec] = [
    _spec("library_categories", "List the library categories with built-in and user entry counts.", {}, [],
          lambda api: api.library.categories(), mutates=False),
    _spec("library_entries", "List the entry names of a library category.",
          {"category": _CAT, "source": {"type": "string", "enum": ["all", "builtin", "user"]}}, ["category"],
          lambda api, category, source="all": api.library.names(category, source), mutates=False),
    _spec("library_entry", "Show one library entry (description and field values).",
          {"category": _CAT, "name": _STR}, ["category", "name"],
          lambda api, category, name: api.library.get(category, name), mutates=False),
    _spec("library_add_to_model", "Create an entity in the project from a library entry (surfaces bring their materials).",
          {"category": _CAT, "name": _STR, "new_name": _STR}, ["category", "name"],
          lambda api, category, name, new_name=None: api.library.add_to_model(category, name, new_name).name),
    _spec("library_add_to_library", "Save a project entity as a user library entry.",
          {"category": _CAT, "entity": _STR, "name": _STR, "overwrite": {"type": "boolean"}, "description": _STR},
          ["category", "entity"],
          lambda api, category, entity, **kw: api.library.add_to_library(category, entity, **kw), ),
    _spec("library_remove", "Remove a user library entry.", {"category": _CAT, "name": _STR}, ["category", "name"],
          lambda api, category, name: api.library.remove_from_library(category, name)),
    _spec("library_export", "Write the user library (optionally with built-ins) to a JSON file.",
          {"filepath": _STR, "categories": {"type": "array", "items": _CAT}, "include_builtin": {"type": "boolean"}},
          ["filepath"],
          lambda api, filepath, categories=None, include_builtin=False:
              api.library.export_library(filepath, categories, include_builtin), mutates=False),
    _spec("library_import", "Merge a library JSON file into the user library; bad entries are reported, not fatal.",
          {"filepath": _STR, "overwrite": {"type": "boolean"}}, ["filepath"],
          lambda api, filepath, overwrite=False: api.library.import_library(filepath, overwrite)),
]
