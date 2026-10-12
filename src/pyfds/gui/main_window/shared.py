"""Constants and small helpers shared by the main-window modules (menu tables, bundled solver paths)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pyfds.core.events import EventType
from pyfds.core.viewport import CameraPreset, VisibilityFlags


def _import_figure_dialog():
    # matplotlib is an optional extra ("plot") — degrade gracefully rather
    # than making the whole GUI module fail to import without it.
    from pyfds.gui.figure_dialog import FigureDialog
    return FigureDialog

# (menu label, CameraPreset) for the View > Standard Views submenu.
_CAMERA_PRESETS = [
    ("&Front", CameraPreset.FRONT),
    ("&Back", CameraPreset.BACK),
    ("&Left", CameraPreset.LEFT),
    ("&Right", CameraPreset.RIGHT),
    ("&Top", CameraPreset.TOP),
    ("&Bottom", CameraPreset.BOTTOM),
    ("&Isometric", CameraPreset.ISOMETRIC),
]

# (menu label, VisibilityFlags) for the View > Show submenu.
_VISIBILITY_TOGGLES = [
    ("&Meshes", VisibilityFlags.MESHES),
    ("&Obstructions", VisibilityFlags.OBSTRUCTIONS),
    ("&Vents", VisibilityFlags.VENTS),
    ("&Devices", VisibilityFlags.DEVICES),
    ("&Init Regions", VisibilityFlags.INIT_REGIONS),
    ("&Profiles", VisibilityFlags.PROFILES),
    ("&Geometry", VisibilityFlags.GEOMETRY),
]

# Repo-bundled solvers (F:\firetwins\fds_smv\...) — checked as a fallback
# before ever prompting the user, and only as a runtime config override
# (never persisted to ~/.pyfds/config.json, which would leak into every
# other FdsConfig() in this process, tests included).
_REPO_ROOT = Path(__file__).resolve().parents[4]

_BUNDLED_FDS_BINARY = _REPO_ROOT / "fds_smv" / "FDS6" / "bin" / "fds.exe"

_BUNDLED_SMV_BINARY = _REPO_ROOT / "fds_smv" / "SMV6" / "smokeview.exe"

def _default_fds_binary() -> Optional[str]:
    return str(_BUNDLED_FDS_BINARY) if _BUNDLED_FDS_BINARY.exists() else None

def _default_smv_binary() -> Optional[str]:
    return str(_BUNDLED_SMV_BINARY) if _BUNDLED_SMV_BINARY.exists() else None

# Repo-bundled reference manuals — opened with the OS's default PDF viewer
# (QDesktopServices.openUrl), same "check it exists first" pattern as the
# solver binaries above.
_FDS_USER_GUIDE = _REPO_ROOT / "docs" / "manuals_and_tutorials" / "FDS" / "FDS_User_Guide.pdf"

_SMV_VERIFICATION_GUIDE = _REPO_ROOT / "docs" / "manuals_and_tutorials" / "SMV" / "SMV_Verification_Guide.pdf"

_PYROSIM_USER_MANUAL = _REPO_ROOT / "docs" / "manuals_and_tutorials" / "pyrosim" / "PyroSim_User_Manual_2025.pdf"

# (menu label, tool name) — tool_name resolves against agent.registry.TOOL_REGISTRY,
# so the GUI's "Add..." actions and the AI agent's tool calls share one field
# definition per entity type (see entity_dialogs.SchemaFormDialog).
_MODEL_ACTIONS = [
    ("Add &Mesh...", "add_mesh"),
    ("Add &Obstruction...", "add_obstruction"),
    ("Add &Vent...", "add_vent"),
    ("Add &Hole...", "add_hole"),
    ("Add &Burner Surface...", "add_burner"),
    ("Add Surface (&Library)...", "add_surface_from_library"),
    ("Add &Reaction...", "add_simple_reaction"),
    ("Add Fuel Reaction (&Library)...", "add_fuel_reaction"),
    ("Add Material (&Library)...", "add_material_from_library"),
    ("Add &Ramp...", "add_ramp"),
    ("Add &Init Region / Particle Cloud...", "add_init"),
    ("Add Particle &Class...", "add_particle_class"),
]

_DEVICE_ACTIONS = [
    ("Add &Thermocouple...", "add_thermocouple"),
    ("Add &Sprinkler...", "add_sprinkler"),
    ("Add Device (by &Quantity)...", "add_device"),
]

_OUTPUT_ACTIONS = [
    ("Add &Slice...", "add_slice"),
    ("Add &Boundary File...", "add_boundary_file"),
    ("Add &Isosurface...", "add_isosurface"),
    ("Add &Plot3D...", "add_plot3d"),
    ("Add &Profile...", "add_profile"),
]

# (menu label, tool name) for the &Draw menu's two-click box-footprint
# tool — same tool_name/dispatcher path as _MODEL_ACTIONS above, just
# driven by two viewport clicks instead of a form dialog.
_DRAW_ACTIONS = [
    ("Draw &Obstruction", "add_obstruction"),
    ("Draw &Vent", "add_vent"),
    ("Draw &Hole", "add_hole"),
]

_HVAC_ACTIONS = [
    ("Add HVAC &Node...", "add_hvac_node"),
    ("Add HVAC &Duct...", "add_hvac_duct"),
    ("Add &Fan...", "add_fan"),
    ("Add Da&mper...", "add_damper"),
    ("Add &Filter...", "add_hvac_filter"),
    ("Add &Leakage...", "add_hvac_leakage"),
]

_ENTITY_COLLECTIONS = [
    ("Meshes", "meshes"),
    ("Obstructions", "obstructions"),
    ("Vents", "vents"),
    ("Holes", "holes"),
    ("Surfaces", "surfaces"),
    ("Devices", "devices"),
    ("Reactions", "reactions"),
    ("Materials", "materials"),
    ("Ramps", "ramps"),
    ("Init Regions", "inits"),
    ("Particle Classes", "particles"),
    ("Slices", "slices"),
    ("Boundary Files", "bndfs"),
    ("Isosurfaces", "isofs"),
    ("Plot3D", "plot3ds"),
    ("Profiles", "profs"),
    ("HVAC Nodes", "hvac_nodes"),
    ("HVAC Ducts", "hvac_ducts"),
    ("Fans", "fans"),
    ("Dampers", "dampers"),
    ("HVAC Filters", "hvac_filters"),
    ("HVAC Leakages", "hvac_leakages"),
    ("HVAC Aircoils", "hvac_aircoils"),
    ("Scenarios", "scenarios"),
    ("Floors", "floors"),
    ("Groups", "groups"),
    ("Geoms", "geom"),
]

# Emitted by CommandPipeline for every mutation (add/remove/move/undo/redo)
# plus project lifecycle — a full refresh on any of these is always correct.
_REFRESH_EVENTS = (
    EventType.COMMAND_EXECUTED,
    EventType.UNDO_PERFORMED,
    EventType.REDO_PERFORMED,
    EventType.HISTORY_CLEARED,
    EventType.PROJECT_LOADED,
    EventType.PROJECT_CREATED,
)
