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
    _spec("library_import_fds", "Add the materials, surfaces, reactions, species, particles and props of an FDS file "
          "(a property library or a model) to the user library.",
          {"filepath": _STR, "categories": {"type": "array", "items": _CAT}, "overwrite": {"type": "boolean"}},
          ["filepath"],
          lambda api, filepath, categories=None, overwrite=False: api.library.import_fds(filepath, categories, overwrite)),
    _spec("library_export_fds", "Write library entries as FDS records.",
          {"filepath": _STR, "categories": {"type": "array", "items": _CAT}, "include_builtin": {"type": "boolean"},
           "names": {"type": "array", "items": _STR}}, ["filepath"],
          lambda api, filepath, categories=None, include_builtin=False, names=None:
              api.library.export_fds(filepath, categories, include_builtin, names), mutates=False),
    _spec("appearance_list", "List the appearance library (colour, transparency, texture).", {}, [],
          lambda api: {n: api.library.appearance(n) for n in api.library.appearance_names()}, mutates=False),
    _spec("appearance_add", "Define a user appearance; texture_width/height are the tile size in metres.",
          {"name": _STR, "color": _STR, "rgb": {"type": "array", "items": {"type": "integer"}},
           "transparency": {"type": "number"}, "texture_map": _STR, "texture_width": {"type": "number"},
           "texture_height": {"type": "number"}, "overwrite": {"type": "boolean"}}, ["name"],
          lambda api, name, **kw: api.library.add_appearance(name, **kw)),
    _spec("appearance_from_surface", "Save a surface's look as an appearance.",
          {"surface": _STR, "name": _STR, "overwrite": {"type": "boolean"}}, ["surface"],
          lambda api, surface, name=None, overwrite=False: api.library.appearance_from_surface(surface, name, overwrite)),
    _spec("appearance_apply", "Give surfaces an appearance from the library (one undo step).",
          {"appearance": _STR, "surfaces": {"type": "array", "items": _STR}}, ["appearance", "surfaces"],
          lambda api, appearance, surfaces: api.library.apply_appearance(appearance, surfaces)),
]
