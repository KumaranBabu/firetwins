"""Project hygiene, preferences, examples and bulk rename (B8)."""
from __future__ import annotations

from typing import List

from .base import ToolSpec

_STR = {"type": "string"}


def _spec(name, description, props, required, handler, mutates=True):
    return ToolSpec(name=name, description=description,
                    input_schema={"type": "object", "properties": props, "required": required},
                    handler=handler, mutates=mutates)


def _resolve(api, names):
    out = []
    for n in names:
        found = [m.entity for m in api.find.find(n, fields=("name",), regex=False, case_sensitive=True, whole_word=True)
                 if m.value == n]
        if not found:
            raise KeyError(f"{n!r} not found")
        if len(found) > 1:
            raise ValueError(f"{n!r} is ambiguous ({len(found)} objects share that name)")
        out.append(found[0])
    return out


TOOLS: List[ToolSpec] = [
    _spec("bulk_rename", "Rename several named objects in the order given: template uses {n} (counter, e.g. {n:02d}) "
          "and {name} (old name). One undo step; nothing changes if any name would clash.",
          {"names": {"type": "array", "items": _STR}, "template": _STR, "start": {"type": "integer"},
           "step": {"type": "integer"}, "update_references": {"type": "boolean"}}, ["names", "template"],
          lambda api, names, template, **kw: api.find.bulk_rename(_resolve(api, names), template, **kw)),
    _spec("set_write_protection", "Turn write protection on or off: a protected project cannot be saved over the file "
          "it was opened from.", {"on": {"type": "boolean"}}, ["on"],
          lambda api, on: api.hygiene.set_write_protection(on)),
    _spec("remove_all_objects", "Delete all model objects (obstructions, vents, holes, geometry, devices, init regions, "
          "texts) or only the listed collections, as one undo step.",
          {"kinds": {"type": "array", "items": _STR}}, [],
          lambda api, kinds=None: api.hygiene.remove_all_objects(kinds)),
    _spec("check_recovery", "Is there an autosave newer than this project file (the last session ended unsaved)?",
          {"path": _STR}, ["path"], lambda api, path: api.hygiene.recovery_available(path), mutates=False),
    _spec("recover_project", "Load the autosave of a project file.", {"path": _STR}, ["path"],
          lambda api, path: api.hygiene.recover(path)),
    _spec("model_defaults", "What a new PyroSim model lists: reserved surfaces, default species, particle classes, view.",
          {}, [], lambda api: api.hygiene.model_defaults(), mutates=False),
    _spec("list_examples", "The curated example models.", {}, [], lambda api: api.examples.list(), mutates=False),
    _spec("load_example", "Replace the current project with a curated example model.", {"name": _STR}, ["name"],
          lambda api, name: api.examples.load(name)),
    _spec("get_preferences", "All preferences grouped for a dialog, with descriptions.", {}, [],
          lambda api: api.preferences.all(), mutates=False),
    _spec("set_preference", "Set one preference (validated).", {"key": _STR, "value": {}}, ["key", "value"],
          lambda api, key, value: api.preferences.set(key, value)),
]
