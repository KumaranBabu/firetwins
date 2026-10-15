"""The 'Edit <Things>...' entries at the top of the Model menu (PyroSim's Edit dialogs)."""
from __future__ import annotations

from .spec import SEPARATOR, ActionSpec

A = ActionSpec

# (menu label, collection attribute on the api, dialog title)
EDITORS = [
    ("Edit &Meshes...", "meshes", "Edit Meshes"),
    ("Edit &Zones...", "zones", "Edit Zones"),
    ("Edit S&pecies...", "species", "Edit Species"),
    ("Edit &Reactions...", "reactions", "Edit Reactions"),
    ("Edit Mate&rials...", "materials", "Edit Materials"),
    ("Edit &Surfaces...", "surfaces", "Edit Surfaces"),
    ("Edit Pa&rticles...", "particles", "Edit Particles"),
    ("Edit R&amps...", "ramps", "Edit Ramps"),
    ("Edit &Controls...", "controls", "Edit Controls"),
]
EDITABLE = {attr for _l, attr, _t in EDITORS} | {"obstructions", "vents", "holes", "devices", "inits"}

EDITOR_MENU = [A(f"model.edit.{attr}", label, ("_on_edit_collection", attr, title))
               for label, attr, title in EDITORS] + [SEPARATOR]
