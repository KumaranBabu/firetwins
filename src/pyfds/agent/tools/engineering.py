"""Engineering calculators (advisory, read-only)."""
from __future__ import annotations

from typing import List

from pyfds.api.catalog import list_fuels
from .base import ToolSpec


TOOLS: List[ToolSpec] = [

    # ── Engineering calculators (advisory — read-only) ──────────────────────
    ToolSpec(
        name="characterise_fire",
        description="Compute a t-squared fire growth characterisation for a peak HRR and growth rate.",
        input_schema={
            "type": "object",
            "properties": {
                "hrr_kw": {"type": "number"},
                "growth": {"type": "string", "enum": ["SLOW", "MEDIUM", "FAST", "ULTRAFAST"], "default": "MEDIUM"},
            },
            "required": ["hrr_kw"],
        },
        handler=lambda api, hrr_kw, growth="MEDIUM": api.engineering.characterise_fire(hrr_kw=hrr_kw, growth=growth),
        mutates=False,
    ),
    ToolSpec(
        name="recommend_cell_size",
        description="Recommend an FDS mesh cell size for a given HRR using the D*/dx criterion.",
        input_schema={"type": "object", "properties": {"hrr_kw": {"type": "number"}}, "required": ["hrr_kw"]},
        handler=lambda api, hrr_kw: api.engineering.recommend_cell_size(hrr_kw),
        mutates=False,
    ),
    ToolSpec(
        name="mesh_wizard",
        description="Auto-configure and add a single FDS mesh sized for a room fire (D*/dx-compliant).",
        input_schema={
            "type": "object",
            "properties": {
                "hrr_kw": {"type": "number"},
                "room_xb": {"type": "array", "items": {"type": "number"}, "minItems": 6, "maxItems": 6},
                "target_cells_millions": {"type": "number", "default": 2.0},
                "growth": {"type": "string", "enum": ["SLOW", "MEDIUM", "FAST", "ULTRAFAST"], "default": "MEDIUM"},
                "name": {"type": "string", "default": "AutoMesh"},
            },
            "required": ["hrr_kw", "room_xb"],
        },
        handler=lambda api, hrr_kw, room_xb, target_cells_millions=2.0, growth="MEDIUM", name="AutoMesh": (
            api.engineering.mesh_wizard(hrr_kw, tuple(room_xb), target_cells_millions, growth, name)
        ),
    ),
    ToolSpec(
        name="ceiling_jet",
        description="Alpert (1972) ceiling jet temperature and velocity at radius r below a ceiling of height H.",
        input_schema={
            "type": "object",
            "properties": {"hrr_kw": {"type": "number"}, "r": {"type": "number"}, "H": {"type": "number"}},
            "required": ["hrr_kw", "r", "H"],
        },
        handler=lambda api, hrr_kw, r, H: api.engineering.ceiling_jet(hrr_kw=hrr_kw, r=r, H=H),
        mutates=False,
    ),
    ToolSpec(
        name="heskestad_plume",
        description="Heskestad plume centerline temperature and velocity at height z above the fire.",
        input_schema={
            "type": "object",
            "properties": {"hrr_kw": {"type": "number"}, "z": {"type": "number"}},
            "required": ["hrr_kw", "z"],
        },
        handler=lambda api, hrr_kw, z: api.engineering.heskestad_plume(hrr_kw=hrr_kw, z=z),
        mutates=False,
    ),
    ToolSpec(
        name="critical_velocity",
        description="Kennedy (1996) tunnel critical ventilation velocity to prevent backlayering.",
        input_schema={
            "type": "object",
            "properties": {
                "hrr_kw": {"type": "number"},
                "tunnel_height_m": {"type": "number"},
                "tunnel_width_m": {"type": "number"},
            },
            "required": ["hrr_kw", "tunnel_height_m", "tunnel_width_m"],
        },
        handler=lambda api, hrr_kw, tunnel_height_m, tunnel_width_m: api.engineering.critical_velocity(
            hrr_kw=hrr_kw, tunnel_height_m=tunnel_height_m, tunnel_width_m=tunnel_width_m
        ),
        mutates=False,
    ),
    ToolSpec(
        name="smoke_filling_time",
        description="NFPA 92 time for the smoke layer to descend to a given interface height.",
        input_schema={
            "type": "object",
            "properties": {
                "hrr_kw": {"type": "number"},
                "floor_area_m2": {"type": "number"},
                "room_height_m": {"type": "number"},
                "z_interface_m": {"type": "number"},
            },
            "required": ["hrr_kw", "floor_area_m2", "room_height_m", "z_interface_m"],
        },
        handler=lambda api, hrr_kw, floor_area_m2, room_height_m, z_interface_m: api.engineering.smoke_filling_time(
            hrr_kw=hrr_kw, floor_area_m2=floor_area_m2, room_height_m=room_height_m, z_interface_m=z_interface_m
        ),
        mutates=False,
    ),
    ToolSpec(
        name="two_layer_zone_model",
        description="CFAST-style two-layer zone model quick-calc (upper/lower layer temperature and height).",
        input_schema={
            "type": "object",
            "properties": {
                "hrr_kw": {"type": "number"},
                "room_height_m": {"type": "number"},
                "floor_area_m2": {"type": "number"},
            },
            "required": ["hrr_kw", "room_height_m", "floor_area_m2"],
        },
        handler=lambda api, hrr_kw, room_height_m, floor_area_m2: api.engineering.two_layer_zone_model(
            hrr_kw=hrr_kw, room_height_m=room_height_m, floor_area_m2=floor_area_m2
        ),
        mutates=False,
    ),
    ToolSpec(
        name="detector_response_time",
        description="RTI-based heat detector / sprinkler activation time.",
        input_schema={
            "type": "object",
            "properties": {
                "hrr_kw": {"type": "number"},
                "ceiling_height_m": {"type": "number"},
                "detector_radial_distance_m": {"type": "number"},
            },
            "required": ["hrr_kw", "ceiling_height_m", "detector_radial_distance_m"],
        },
        handler=lambda api, hrr_kw, ceiling_height_m, detector_radial_distance_m: api.engineering.detector_response_time(
            hrr_kw=hrr_kw, ceiling_height_m=ceiling_height_m,
            detector_radial_distance_m=detector_radial_distance_m,
        ),
        mutates=False,
    ),
    ToolSpec(
        name="list_fuels",
        description="List all predefined fuel names available in the FDS6 fuel library.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.engineering.list_fuels(),
        mutates=False,
    ),
    ToolSpec(
        name="get_fuel",
        description="Look up the raw parameters of a predefined fuel from the library.",
        input_schema={"type": "object", "properties": {"fuel_name": {"type": "string"}}, "required": ["fuel_name"]},
        handler=lambda api, fuel_name: api.engineering.fuel(fuel_name),
        mutates=False,
    ),
    ToolSpec(
        name="add_fuel_reaction",
        description="Add a predefined library fuel as a REAC to the active project.",
        input_schema={
            "type": "object",
            "properties": {
                "fuel_name": {"type": "string", "enum": list_fuels()},
                "reaction_name": {"type": "string"},
            },
            "required": ["fuel_name"],
        },
        handler=lambda api, fuel_name, reaction_name=None: api.engineering.add_fuel_reaction(fuel_name, reaction_name),
    ),
]
