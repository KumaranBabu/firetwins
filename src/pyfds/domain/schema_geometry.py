"""Entity schemas: mesh, obstruction, vent, transforms, geom, move."""
from __future__ import annotations

from .schema_types import (
    EntitySchema,
    FT,
    _p,
)


def _build_mesh_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Mesh",
        display_name="Mesh Region",
        fds_namelist="MESH",
        category="Mesh",
        description="Defines one rectangular FDS computation mesh block.",
        properties=[
            _p("name",        "ID",          FT.STRING,    required=True,  fds_param="ID",
               desc="Unique name for this mesh block."),
            _p("x_min",       "X min",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("x_max",       "X max",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("y_min",       "Y min",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("y_max",       "Y max",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("z_min",       "Z min",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("z_max",       "Z max",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("cell_count",  "IJK",         FT.VECTOR_IJK, required=True, fds_param="IJK", category="Mesh",
               desc="Cell count (I, J, K). Each value must satisfy the Poisson rule: 2^a·3^b·5^c."),
            _p("mpi_processor", "MPI Rank",  FT.INT,   min_val=0, fds_param="MPI_PROCESS", category="Mesh",
               desc="MPI process index (0-based). Leave blank for auto-assignment."),
            _p("cylindrical", "Cylindrical", FT.BOOL,  fds_param="CYLINDRICAL", category="Mesh",
               desc="Enable cylindrical coordinates for axisymmetric simulations.", advanced=True),
            _p("color",       "Color",       FT.COLOR_NAME, fds_param="COLOR", category="Display"),
        ],
    )


def _build_obstruction_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Obstruction",
        display_name="Obstruction",
        fds_namelist="OBST",
        category="Geometry",
        description="Solid rectangular block (OBST). The fundamental geometry primitive.",
        properties=[
            _p("name",       "ID",        FT.STRING,   required=True,  fds_param="ID"),
            _p("x_min",      "X min",     FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("x_max",      "X max",     FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("y_min",      "Y min",     FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("y_max",      "Y max",     FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("z_min",      "Z min",     FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("z_max",      "Z max",     FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("surface_id", "Surface",   FT.ENTITY_REF, required=True, fds_param="SURF_ID",
               ref_type="Surface", category="Material"),
            _p("color",      "Color",     FT.COLOR_NAME, fds_param="COLOR", category="Display"),
            _p("transparency","Transparency", FT.FLOAT, min_val=0.0, max_val=1.0, fds_param="TRANSPARENCY", category="Display"),
            _p("thicken",    "Thicken",   FT.BOOL,  fds_param="THICKEN", category="Options",
               desc="Force the obstruction to be one cell thick even if it appears thinner.", advanced=True),
            _p("allow_vent", "Allow Vent",FT.BOOL,  fds_param="ALLOW_VENT", category="Options", advanced=True),
            _p("ctrl_id",    "Control",   FT.ENTITY_REF, fds_param="CTRL_ID", ref_type="Control", category="Control"),
            _p("mult_id",    "Multiplier",FT.ENTITY_REF, fds_param="MULT_ID", ref_type="Mult", category="Options", advanced=True),
        ],
    )


def _build_vent_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Vent",
        display_name="Vent",
        fds_namelist="VENT",
        category="Geometry",
        description="Planar boundary condition patch (VENT). Used for openings, inlets, and fire.",
        properties=[
            _p("name",            "ID",          FT.STRING,   required=True, fds_param="ID"),
            _p("x_min",           "X min",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("x_max",           "X max",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("y_min",           "Y min",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("y_max",           "Y max",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("z_min",           "Z min",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("z_max",           "Z max",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("surface_id",      "Surface",     FT.ENTITY_REF, required=True, fds_param="SURF_ID",
               ref_type="Surface", default="OPEN"),
            _p("ctrl_id",         "Control",     FT.ENTITY_REF, fds_param="CTRL_ID", ref_type="Control", category="Control"),
            _p("dynamic_pressure","Dyn. Pressure",FT.FLOAT, "Pa", fds_param="DYNAMIC_PRESSURE", category="Flow"),
            _p("color",           "Color",       FT.COLOR_NAME, fds_param="COLOR", category="Display"),
        ],
    )


def _build_mesh_transform_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="MeshTransform",
        display_name="Mesh Transform (TRN)",
        fds_namelist="TRNX/TRNY/TRNZ",
        category="Mesh",
        description="Non-uniform mesh cell stretching control point.",
        properties=[
            _p("name",        "ID",          FT.STRING, required=True, fds_param="ID"),
            _p("direction",   "Direction",   FT.ENUM, required=True, fds_param="",
               enum_values=["X", "Y", "Z"]),
            _p("mesh_number", "Mesh Number", FT.INT, min_val=1, fds_param="MESH_NUMBER"),
            _p("ideriv",      "IDERIV",      FT.INT, min_val=0, max_val=1, fds_param="IDERIV",
               enum_values=["0", "1"], desc="0=piecewise uniform, 1=stretching."),
            _p("cc",          "CC",          FT.FLOAT, "m", fds_param="CC",
               desc="Physical coordinate of the control point."),
            _p("pc",          "PC",          FT.FLOAT, min_val=0.0, max_val=1.0, fds_param="PC",
               desc="Fractional position within the mesh (0..1)."),
        ],
    )


def _build_geom_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Geom",
        display_name="Geometry (GEOM)",
        fds_namelist="GEOM",
        category="Geometry",
        description="Complex geometry defined by a triangulated surface mesh or file.",
        properties=[
            _p("name",         "ID",          FT.STRING, required=True, fds_param="ID"),
            _p("surf_id",      "Surface",     FT.ENTITY_REF, required=True, fds_param="SURF_ID", ref_type="Surface"),
            _p("binary_file",  "Binary File", FT.FILE_PATH, fds_param="BINARY_FILE",
               desc="Path to a binary geometry file (.bingeom)."),
            _p("is_terrain",   "Is Terrain",  FT.BOOL, fds_param="IS_TERRAIN"),
            _p("component_only","Component Only", FT.BOOL, fds_param="COMPONENT_ONLY", advanced=True),
            _p("move_id",      "Move ID",     FT.STRING, fds_param="MOVE_ID", advanced=True),
        ],
    )


def _build_move_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Move",
        display_name="Rigid Body Motion",
        fds_namelist="MOVE",
        category="Geometry",
        description="Applies rigid-body translation or rotation to a GEOM or OBST entity.",
        properties=[
            _p("name",           "ID",            FT.STRING, required=True, fds_param="ID"),
            _p("omega",          "Angular Velocity", FT.FLOAT, "rad/s", fds_param="OMEGA"),
            _p("rotation_angle", "Rotation Angle",   FT.FLOAT, "°", fds_param="ROTATION_ANGLE"),
            _p("dx",  "ΔX", FT.FLOAT, "m", fds_param="DX"),
            _p("dy",  "ΔY", FT.FLOAT, "m", fds_param="DY"),
            _p("dz",  "ΔZ", FT.FLOAT, "m", fds_param="DZ"),
            _p("scale", "Scale", FT.FLOAT, min_val=0.001, fds_param="SCALE"),
            _p("x0", "Origin X", FT.FLOAT, "m", fds_param="X0", advanced=True),
            _p("y0", "Origin Y", FT.FLOAT, "m", fds_param="Y0", advanced=True),
            _p("z0", "Origin Z", FT.FLOAT, "m", fds_param="Z0", advanced=True),
        ],
    )
