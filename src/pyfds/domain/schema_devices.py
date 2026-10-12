"""Entity schemas: device, slice, HVAC node, duct, filter, leakage."""
from __future__ import annotations

from .schema_types import (
    EntitySchema,
    FT,
    _p,
)


def _build_device_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Device",
        display_name="Device / Sensor",
        fds_namelist="DEVC",
        category="Devices",
        description="Measurement device, sprinkler, or detector (DEVC).",
        properties=[
            _p("name",             "ID",          FT.STRING,   required=True, fds_param="ID"),
            _p("quantity",         "Quantity",    FT.STRING,   required=True, fds_param="QUANTITY",
               desc="FDS output quantity, e.g. TEMPERATURE, HEAT FLUX, VELOCITY."),
            _p("quantity2",        "Quantity 2",  FT.STRING,   fds_param="QUANTITY2", category="Output",
               desc="Optional second output quantity.", advanced=True),
            _p("x",                "X",           FT.FLOAT, "m", fds_param="XYZ", category="Location"),
            _p("y",                "Y",           FT.FLOAT, "m", fds_param="XYZ", category="Location"),
            _p("z",                "Z",           FT.FLOAT, "m", fds_param="XYZ", category="Location"),
            _p("orientation",      "Orientation", FT.VECTOR3,  fds_param="ORIENTATION", category="Location"),
            _p("prop_id",          "Property Set",FT.ENTITY_REF, fds_param="PROP_ID", ref_type="Prop", category="Sprinkler"),
            _p("ctrl_id",          "Control",     FT.ENTITY_REF, fds_param="CTRL_ID", ref_type="Control", category="Control"),
            _p("setpoint",         "Set Point",   FT.FLOAT,    fds_param="SETPOINT", category="Control"),
            _p("statistics",       "Statistics",  FT.ENUM,     fds_param="STATISTICS",
               enum_values=["", "MAX", "MIN", "MEAN", "RMS", "COV"], category="Output"),
            _p("latch",            "Latch",       FT.BOOL,     fds_param="LATCH", default=True, category="Control"),
            _p("time_averaged",    "Time-avg",    FT.BOOL,     fds_param="TIME_AVERAGED", category="Output", advanced=True),
            _p("duct_id",          "Duct ID",     FT.ENTITY_REF, fds_param="DUCT_ID", ref_type="HvacDuct", category="HVAC", advanced=True),
        ],
    )


def _build_hvac_node_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="HvacNode",
        display_name="HVAC Node",
        fds_namelist="NODE",
        category="HVAC",
        description="Connection point in the HVAC duct network.",
        properties=[
            _p("name",    "ID",      FT.STRING, required=True, fds_param="ID"),
            _p("x",       "X",       FT.FLOAT, "m", fds_param="XYZ", category="Location"),
            _p("y",       "Y",       FT.FLOAT, "m", fds_param="XYZ", category="Location"),
            _p("z",       "Z",       FT.FLOAT, "m", fds_param="XYZ", category="Location"),
            _p("ambient", "Ambient", FT.BOOL, fds_param="AMBIENT",
               desc="If True this node connects the network to the ambient environment."),
            _p("vent_id", "Vent ID", FT.ENTITY_REF, fds_param="VENT_ID", ref_type="Vent"),
        ],
    )


def _build_hvac_duct_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="HvacDuct",
        display_name="HVAC Duct",
        fds_namelist="DUCT",
        category="HVAC",
        description="Duct segment connecting two HVAC nodes.",
        properties=[
            _p("name",      "ID",          FT.STRING, required=True, fds_param="ID"),
            _p("node_id_1", "Node 1",      FT.ENTITY_REF, required=True, fds_param="NODE_ID", ref_type="HvacNode"),
            _p("node_id_2", "Node 2",      FT.ENTITY_REF, required=True, fds_param="NODE_ID", ref_type="HvacNode"),
            _p("diameter",  "Diameter",    FT.FLOAT, "m", min_val=0.001, fds_param="DIAMETER"),
            _p("length",    "Length",      FT.FLOAT, "m", min_val=0.0, fds_param="LENGTH"),
            _p("roughness", "Roughness",   FT.FLOAT, "m", min_val=0.0, fds_param="ROUGHNESS"),
        ],
    )


def _build_slice_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Slice",
        display_name="Slice File",
        fds_namelist="SLCF",
        category="Output",
        description="Planar output file recording a field quantity at each time step.",
        properties=[
            _p("name",         "ID",          FT.STRING, required=True, fds_param="ID"),
            _p("quantity",     "Quantity",    FT.STRING, required=True, fds_param="QUANTITY"),
            _p("plane",        "Plane",       FT.ENUM, required=True, fds_param="PBX/PBY/PBZ",
               enum_values=["X", "Y", "Z"]),
            _p("position",     "Position",    FT.FLOAT, "m", required=True, fds_param="PBX"),
            _p("quantity2",    "Quantity 2",  FT.STRING, fds_param="QUANTITY2", advanced=True),
            _p("vector",       "Vector",      FT.BOOL, fds_param="VECTOR"),
            _p("cell_centered","Cell-centred",FT.BOOL, fds_param="CELL_CENTERED", advanced=True),
        ],
    )


def _build_hvac_filter_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="HvacFilter",
        display_name="HVAC Filter",
        fds_namelist="FILTER",
        category="HVAC",
        description="Particulate filter in an HVAC duct network.",
        properties=[
            _p("name",       "ID",         FT.STRING, required=True, fds_param="ID"),
            _p("duct_id",    "Duct",       FT.ENTITY_REF, required=True, fds_param="DUCT_ID", ref_type="HvacDuct"),
            _p("efficiency", "Efficiency", FT.FLOAT, min_val=0.0, max_val=1.0, fds_param="EFFICIENCY"),
            _p("loss",       "Loss",       FT.FLOAT, min_val=0.0, fds_param="LOSS"),
            _p("clean_loss", "Clean Loss", FT.FLOAT, min_val=0.0, fds_param="CLEAN_LOSS", advanced=True),
            _p("ctrl_id",    "Control",    FT.ENTITY_REF, fds_param="CTRL_ID", ref_type="Control"),
        ],
    )


def _build_hvac_leakage_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="HvacLeakage",
        display_name="Duct Leakage",
        fds_namelist="LEAK",
        category="HVAC",
        description="Leakage path between two pressure zones.",
        properties=[
            _p("name",      "ID",          FT.STRING, required=True, fds_param="ID"),
            _p("zone_id_1", "Zone 1",      FT.ENTITY_REF, required=True, fds_param="ZONE_ID(1)", ref_type="Zone"),
            _p("zone_id_2", "Zone 2",      FT.ENTITY_REF, required=True, fds_param="ZONE_ID(2)", ref_type="Zone"),
            _p("area",      "Leakage Area",FT.FLOAT, "m²", min_val=0.0, fds_param="AREA"),
            _p("crack_id",  "Crack ID",    FT.STRING, fds_param="CRACK_ID", advanced=True),
            _p("ctrl_id",   "Control",     FT.ENTITY_REF, fds_param="CTRL_ID", ref_type="Control"),
        ],
    )
