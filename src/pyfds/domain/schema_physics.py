"""Entity schemas: surface, material, reaction, ramp, control, wind profile."""
from __future__ import annotations

from .schema_types import (
    EntitySchema,
    FT,
    _p,
)


def _build_surface_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Surface",
        display_name="Surface",
        fds_namelist="SURF",
        category="Materials",
        description="Defines boundary condition / material properties for faces.",
        properties=[
            _p("name",             "ID",           FT.STRING, required=True, fds_param="ID"),
            _p("heat_release_rate","HRRPUA",        FT.FLOAT, "kW/m²", min_val=0.0, fds_param="HRRPUA",
               category="Fire", desc="Heat release rate per unit area. Set >0 for a burning surface."),
            _p("tau_q",            "Ramp-up time", FT.FLOAT, "s", min_val=0.0, fds_param="TAU_Q", category="Fire"),
            _p("ramp_q",           "HRR Ramp",     FT.ENTITY_REF, fds_param="RAMP_Q", ref_type="Ramp", category="Fire"),
            _p("tmp_front",        "Temp (front)", FT.FLOAT, "°C", fds_param="TMP_FRONT", category="Thermal"),
            _p("vel",              "Velocity",     FT.FLOAT, "m/s", fds_param="VEL", category="Flow"),
            _p("volume_flow",      "Volume Flow",  FT.FLOAT, "m³/s", fds_param="VOLUME_FLOW", category="Flow"),
            _p("mass_flux",        "Mass Flux",    FT.FLOAT, "kg/(m²·s)", fds_param="MASS_FLUX", category="Flow"),
            _p("backing",          "Backing",      FT.ENUM,  fds_param="BACKING", category="Thermal",
               enum_values=["VOID", "INSULATED", "EXPOSED"], default="VOID"),
            _p("burn_away",        "Burn Away",    FT.BOOL,  fds_param="BURN_AWAY", category="Fire"),
            _p("matl_id",          "Material ID",  FT.ENTITY_REF, fds_param="MATL_ID", ref_type="Material", category="Layers"),
            _p("color",            "Color",        FT.COLOR_NAME, fds_param="COLOR", category="Display"),
            _p("transparency",     "Transparency", FT.FLOAT, min_val=0.0, max_val=1.0, fds_param="TRANSPARENCY", category="Display"),
            _p("texture_map",      "Texture",      FT.FILE_PATH, fds_param="TEXTURE_MAP", category="Display", advanced=True),
        ],
    )


def _build_material_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Material",
        display_name="Material",
        fds_namelist="MATL",
        category="Materials",
        description="Solid material thermal and pyrolysis properties (MATL).",
        properties=[
            _p("name",            "ID",            FT.STRING, required=True, fds_param="ID"),
            _p("density",         "Density",       FT.FLOAT, "kg/m³", required=True, min_val=0.01, fds_param="DENSITY"),
            _p("conductivity",    "Conductivity",  FT.FLOAT, "W/(m·K)", required=True, min_val=0.0, fds_param="CONDUCTIVITY"),
            _p("specific_heat",   "Specific Heat", FT.FLOAT, "kJ/(kg·K)", required=True, min_val=0.0, fds_param="SPECIFIC_HEAT"),
            _p("emissivity",      "Emissivity",    FT.FLOAT, min_val=0.0, max_val=1.0, fds_param="EMISSIVITY"),
            _p("heat_of_reaction","Heat of Reaction",FT.FLOAT,"kJ/kg", min_val=0.0, fds_param="HEAT_OF_REACTION", category="Pyrolysis"),
            _p("reference_temperature","Ref. Temp",FT.FLOAT,"°C", fds_param="REFERENCE_TEMPERATURE", category="Pyrolysis"),
            _p("a",               "A (Arrhenius)", FT.FLOAT, "1/s", fds_param="A", category="Pyrolysis", advanced=True),
            _p("e",               "E (Activation)",FT.FLOAT, "J/mol", fds_param="E", category="Pyrolysis", advanced=True),
            _p("n_reactions",     "N Reactions",   FT.INT, min_val=1, fds_param="N_REACTIONS", category="Pyrolysis", advanced=True),
        ],
    )


def _build_reaction_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Reaction",
        display_name="Reaction",
        fds_namelist="REAC",
        category="Combustion",
        description="Gas-phase combustion reaction (REAC). Typically one per simulation.",
        properties=[
            _p("name",                  "ID",             FT.STRING, required=True, fds_param="ID"),
            _p("fuel",                  "Fuel Species",   FT.STRING, fds_param="FUEL"),
            _p("formula",               "Formula",        FT.STRING, fds_param="FORMULA", advanced=True),
            _p("heat_of_combustion",    "Heat of Comb.",  FT.FLOAT, "kJ/kg", min_val=0.0, fds_param="HEAT_OF_COMBUSTION"),
            _p("soot_yield",            "Soot Yield",     FT.FLOAT, "kg/kg", min_val=0.0, max_val=1.0, fds_param="SOOT_YIELD"),
            _p("co_yield",              "CO Yield",       FT.FLOAT, "kg/kg", min_val=0.0, max_val=1.0, fds_param="CO_YIELD"),
            _p("radiative_fraction",    "Rad. Fraction",  FT.FLOAT, min_val=0.0, max_val=1.0, fds_param="RADIATIVE_FRACTION"),
            _p("lower_oxygen_limit",    "LOL",            FT.FLOAT, "vol fraction", min_val=0.0, max_val=0.3, fds_param="LOWER_OXYGEN_LIMIT", advanced=True),
            _p("auto_ignition_temperature","Auto-ignition",FT.FLOAT,"°C", fds_param="AUTO_IGNITION_TEMPERATURE", advanced=True),
            _p("fuel_radcal_id",        "RADCAL Fuel",    FT.STRING, fds_param="FUEL_RADCAL_ID", advanced=True),
        ],
    )


def _build_ramp_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Ramp",
        display_name="Ramp",
        fds_namelist="RAMP",
        category="Controls",
        description="Time-varying scalar function (RAMP). Each T/F pair is one namelist line.",
        properties=[
            _p("name",   "ID",     FT.STRING, required=True, fds_param="ID"),
            _p("times",  "Times",  FT.LIST_FLOAT, "s", required=True, fds_param="T",
               desc="Strictly increasing time values."),
            _p("values", "Values", FT.LIST_FLOAT, required=True, fds_param="F",
               desc="Function values at corresponding time points."),
        ],
    )


def _build_control_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Control",
        display_name="Control Logic",
        fds_namelist="CTRL",
        category="Controls",
        description="Logic controller for activating/deactivating model components.",
        properties=[
            _p("name",             "ID",             FT.STRING, required=True, fds_param="ID"),
            _p("function_type",    "Function",       FT.ENUM, required=True, fds_param="FUNCTION_TYPE",
               enum_values=["CUSTOM", "ANY", "ALL", "ONLY", "AT_LEAST", "DEADBAND",
                            "TIME_DELAY", "PERCENTILE", "CYCLING"]),
            _p("input_id",         "Input ID",       FT.ENTITY_REF, fds_param="INPUT_ID"),
            _p("setpoint",         "Set Point",      FT.FLOAT, fds_param="SETPOINT"),
            _p("delay",            "Delay",          FT.FLOAT, "s", min_val=0.0, fds_param="DELAY"),
            _p("latch",            "Latch",          FT.BOOL, default=True, fds_param="LATCH"),
            _p("deadband",         "Dead Band",      FT.VECTOR2, fds_param="DEADBAND", advanced=True),
            _p("percentile_rank",  "Percentile Rank",FT.FLOAT, min_val=0.0, max_val=100.0,
               fds_param="PERCENTILE_RANK", advanced=True),
            _p("ramp_id",          "Ramp ID",        FT.ENTITY_REF, fds_param="RAMP_ID", ref_type="Ramp", advanced=True),
        ],
    )


def _build_wind_profile_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="WindProfile",
        display_name="Wind Profile",
        fds_namelist="WIND",
        category="Atmosphere",
        description="Atmospheric boundary layer wind profile for outdoor fire modelling.",
        properties=[
            _p("name",      "ID",        FT.STRING, required=True, fds_param="ID"),
            _p("speed",     "Speed",     FT.FLOAT, "m/s", min_val=0.0, fds_param="SPEED"),
            _p("direction", "Direction", FT.FLOAT, "°", min_val=0.0, max_val=360.0, fds_param="DIRECTION",
               desc="Wind direction in degrees from North (270 = westerly)."),
            _p("z_ref",     "Ref Height",FT.FLOAT, "m", min_val=0.001, fds_param="Z_REF"),
            _p("z0",        "Roughness Length", FT.FLOAT, "m", min_val=0.0, fds_param="Z0", advanced=True),
            _p("l",         "Obukhov Length",   FT.FLOAT, "m", fds_param="L", advanced=True),
            _p("ustar",     "Friction Velocity", FT.FLOAT, "m/s", min_val=0.0, fds_param="USTAR", advanced=True),
            _p("latitude",  "Latitude",  FT.FLOAT, "°", fds_param="LATITUDE", advanced=True),
            _p("l_inf",     "Mixing Height", FT.FLOAT, "m", min_val=0.0, fds_param="L_INF", advanced=True),
            _p("ramp_id",   "Speed Ramp",    FT.ENTITY_REF, fds_param="RAMP_ID", ref_type="Ramp"),
        ],
    )
