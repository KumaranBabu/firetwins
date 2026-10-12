"""Species, zones, device properties, multipliers, moves, mesh stretching and text blocks (G3)."""
from __future__ import annotations

from typing import List

from .base import ToolSpec, _remove_from

_NAME = {"type": "string"}
_NUM3 = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}
_RANGE = {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2,
          "description": "[lower, upper] index range."}


def _list_tool(name: str, what: str, attr: str) -> ToolSpec:
    return ToolSpec(
        name=name, description=f"List all {what} in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: getattr(api, attr).all(), mutates=False)


def _remove_tool(name: str, what: str, attr: str) -> ToolSpec:
    return ToolSpec(
        name=name, description=f"Remove a {what} by name.",
        input_schema={"type": "object", "properties": {"name": _NAME}, "required": ["name"]},
        handler=lambda api, name: _remove_from(getattr(api, attr), name))


def _edit_tool(name: str, what: str, attr: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"Change fields of an existing {what} (one undoable step). "
                    "Unknown field names are rejected.",
        input_schema={"type": "object", "properties": {
            "name": _NAME, "fields": {"type": "object", "description": "{field: new value}."}},
            "required": ["name", "fields"]},
        handler=lambda api, name, fields: getattr(api, attr).update(name, **fields))


TOOLS: List[ToolSpec] = [
    # ── Species ──────────────────────────────────────────────────────────────
    ToolSpec(
        name="add_species",
        description="Add a gas species (&SPEC). Reactions, lumped species and devices refer to it by name.",
        input_schema={"type": "object", "properties": {
            "name": _NAME, "mw": {"type": "number", "description": "Molecular weight, g/mol."},
            "formula": {"type": "string"},
            "background": {"type": "boolean", "description": "Make this the background species."}},
            "required": ["name"]},
        handler=lambda api, name, mw=None, formula=None, background=False: _add_species(
            api, name, mw, formula, background),
    ),
    ToolSpec(
        name="add_lumped_species",
        description="Add a lumped (mixture) species from existing component species; give volume OR mass fractions.",
        input_schema={"type": "object", "properties": {
            "name": _NAME, "components": {"type": "array", "items": _NAME},
            "volume_fractions": {"type": "array", "items": {"type": "number"}},
            "mass_fractions": {"type": "array", "items": {"type": "number"}}},
            "required": ["name", "components"]},
        handler=lambda api, name, components, volume_fractions=None, mass_fractions=None:
            api.species.add_lumped(name, components, volume_fractions, mass_fractions),
    ),
    ToolSpec(
        name="set_background_species",
        description="Make a species the background (diluent) species; clears the flag on the others.",
        input_schema={"type": "object", "properties": {"name": _NAME}, "required": ["name"]},
        handler=lambda api, name: api.species.set_background(name),
    ),
    _edit_tool("edit_species", "species", "species"),
    _list_tool("list_species", "species", "species"),
    ToolSpec(
        name="remove_species",
        description="Remove a species by name; refused while a reaction or lumped species still uses it.",
        input_schema={"type": "object", "properties": {"name": _NAME}, "required": ["name"]},
        handler=lambda api, name: api.species.remove_checked(name),
    ),

    # ── Pressure zones ───────────────────────────────────────────────────────
    ToolSpec(
        name="add_zone",
        description="Add a pressure zone (&ZONE) identified by one interior point.",
        input_schema={"type": "object", "properties": {"xyz": _NUM3, "name": _NAME}, "required": ["xyz"]},
        handler=lambda api, xyz, name=None: api.zones.add_zone(xyz, name=name),
    ),
    _edit_tool("edit_zone", "pressure zone", "zones"),
    _list_tool("list_zones", "pressure zones", "zones"),
    _remove_tool("remove_zone", "pressure zone", "zones"),

    # ── Device properties ────────────────────────────────────────────────────
    ToolSpec(
        name="add_sprinkler_prop",
        description="Add a sprinkler property set (&PROP) with RTI and C-factor; reference it from a device's prop_id.",
        input_schema={"type": "object", "properties": {
            "name": _NAME, "rti": {"type": "number", "default": 50.0},
            "c_factor": {"type": "number", "default": 0.7}}},
        handler=lambda api, name=None, rti=50.0, c_factor=0.7:
            api.props.add_sprinkler(name, rti=rti, c_factor=c_factor),
    ),
    ToolSpec(
        name="add_smoke_detector_prop",
        description="Add a smoke-detector property set (&PROP) with an activation obscuration (%/m).",
        input_schema={"type": "object", "properties": {
            "name": _NAME, "activation_obscuration": {"type": "number", "default": 3.28}}},
        handler=lambda api, name=None, activation_obscuration=3.28:
            api.props.add_smoke_detector(name, activation_obscuration=activation_obscuration),
    ),
    _edit_tool("edit_prop", "device property set", "props"),
    _list_tool("list_props", "device property sets", "props"),
    _remove_tool("remove_prop", "device property set", "props"),

    # ── Multipliers ──────────────────────────────────────────────────────────
    ToolSpec(
        name="add_mult",
        description="Add an array multiplier (&MULT): copies of an obstruction at dx/dy/dz spacing over i/j/k index ranges.",
        input_schema={"type": "object", "properties": {
            "name": _NAME, "dx": {"type": "number"}, "dy": {"type": "number"}, "dz": {"type": "number"},
            "i": _RANGE, "j": _RANGE, "k": _RANGE}},
        handler=lambda api, name=None, dx=0.0, dy=0.0, dz=0.0, i=(0, 0), j=(0, 0), k=(0, 0):
            api.mults.add_mult(name, dx=dx, dy=dy, dz=dz, i=i, j=j, k=k),
    ),
    _edit_tool("edit_mult", "multiplier", "mults"),
    _list_tool("list_mults", "multipliers", "mults"),
    _remove_tool("remove_mult", "multiplier", "mults"),

    # ── Moves ────────────────────────────────────────────────────────────────
    ToolSpec(
        name="add_translation",
        description="Add a translation (&MOVE) that offsets a geometry/obstruction by dx, dy, dz.",
        input_schema={"type": "object", "properties": {
            "name": _NAME, "dx": {"type": "number"}, "dy": {"type": "number"}, "dz": {"type": "number"}}},
        handler=lambda api, name=None, dx=0.0, dy=0.0, dz=0.0: api.moves.add_translation(dx, dy, dz, name=name),
    ),
    ToolSpec(
        name="add_rotation",
        description="Add a rotation (&MOVE) by an angle in degrees about an axis through an origin.",
        input_schema={"type": "object", "properties": {
            "angle": {"type": "number"}, "axis": _NUM3, "origin": _NUM3, "name": _NAME},
            "required": ["angle"]},
        handler=lambda api, angle, axis=(0, 0, 1), origin=(0, 0, 0), name=None:
            api.moves.add_rotation(angle, axis=axis, origin=origin, name=name),
    ),
    _edit_tool("edit_move", "move", "moves"),
    _list_tool("list_moves", "moves", "moves"),
    _remove_tool("remove_move", "move", "moves"),

    # ── Mesh stretching ──────────────────────────────────────────────────────
    ToolSpec(
        name="add_mesh_transform",
        description="Add a non-uniform mesh stretching control point (&TRNX/&TRNY/&TRNZ).",
        input_schema={"type": "object", "properties": {
            "direction": {"type": "string", "enum": ["X", "Y", "Z"]},
            "cc": {"type": "number", "description": "Physical coordinate."},
            "pc": {"type": "number", "description": "Fractional position 0..1.", "default": 0.5},
            "mesh_number": {"type": "integer", "default": 1}, "name": _NAME},
            "required": ["direction", "cc"]},
        handler=lambda api, direction, cc, pc=0.5, mesh_number=1, name=None:
            api.mesh_transforms.add_transform(direction, cc, pc, mesh_number, name=name),
    ),
    _edit_tool("edit_mesh_transform", "mesh transform", "mesh_transforms"),
    _list_tool("list_mesh_transforms", "mesh transforms", "mesh_transforms"),
    _remove_tool("remove_mesh_transform", "mesh transform", "mesh_transforms"),

    # ── Raw text blocks ──────────────────────────────────────────────────────
    ToolSpec(
        name="add_text_block",
        description="Add a verbatim text block written unchanged into the FDS file (for features without a typed editor).",
        input_schema={"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]},
        handler=lambda api, content: api.texts.add_text(content),
    ),
    _list_tool("list_text_blocks", "text blocks", "texts"),
    ToolSpec(
        name="remove_text_block",
        description="Remove a text block by its index in list_text_blocks.",
        input_schema={"type": "object", "properties": {"index": {"type": "integer"}}, "required": ["index"]},
        handler=lambda api, index: _remove_text(api, index),
    ),
]


def _add_species(api, name, mw, formula, background):
    fields = {"formula": formula} if formula else {}
    spec = api.species.add_species(name, mw, **fields)
    if background:
        api.species.set_background(name)
    return spec


def _remove_text(api, index):
    text = api.texts.get(index)
    if text is None:
        raise KeyError(f"no text block at index {index}")
    api.texts.remove(text)
