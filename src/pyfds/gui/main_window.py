"""
Minimal application shell.

Wires the traditional Qt GUI and the optional AI assistant panel over one
shared ``FdsApi`` instance. Every widget here either (a) calls an
``FdsApi``/manager method in response to user action, or (b) subscribes to
the global ``EventBus`` and re-renders — it never reaches into
``api.project`` and mutates it directly. This is the same rule the agent
tool layer follows (see ``pyfds.agent``); a human clicking File > New and
the AI calling the ``apply_template`` tool are indistinguishable at the
model layer.

Run directly::

    python -m pyfds.gui.main_window
"""
from __future__ import annotations

import ast
import copy
import math
import operator
import shutil
import uuid
from pathlib import Path
from typing import Any, List, Optional, Tuple

from PySide6.QtCore import Qt, QItemSelectionModel, QSettings, QTimer, QUrl, Signal
from PySide6.QtGui import QActionGroup, QColor, QCursor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDockWidget, QFileDialog,
    QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox, QTreeWidget,
    QTreeWidgetItem,
)

from pyfds.agent import AgentToolDispatcher
from pyfds.agent.registry import get_tool
from pyfds.api import FdsApi
from pyfds.automation.commands import (
    AddEntityCommand, GroupCommand, MirrorCommand, MirrorGeomCommand,
    MoveObstCommand, RotateCommand, RotateGeomCommand, ScaleCommand,
    ScaleGeomCommand, TranslateGeomCommand, TranslatePointCommand,
)
from pyfds.core.events import EventType
from pyfds.core.viewport import CameraPreset, VisibilityFlags
from pyfds.domain.geometry_tools import GeometryTools
from pyfds.gui.entity_dialogs import SchemaFormDialog
from pyfds.gui.icons import icon_for_entity
from pyfds.gui.property_schema import apply_edits, build_edit_schema
from pyfds.gui.report_dialog import TextReportDialog

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
_REPO_ROOT = Path(__file__).resolve().parents[3]
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


# ── Move/Rotate/Scale/Mirror Selected — entity-shape dispatch helpers ──────
#
# Three "shapes" of transformable entity exist in this app: XB-box
# (Obstruction/Mesh/Vent/Hole — x_min/x_max/... bounds), Geom (mesh —
# verts/faces), and point (Device/HvacNode — x/y/z or an xyz tuple).
# These are plain module functions (not FdsApi/GUI methods) since they
# only inspect an entity's shape, not any application state.

def _point_xyz(entity: Any) -> Optional[Tuple[float, float, float]]:
    """Current (x, y, z) of a point entity, or None if it isn't one.
    Prefers ``xyz`` when present (what Device.add_device() populates and
    what FdsEntity.bbox()'s point-entity branch already reads) over plain
    x/y/z (what HvacNode uses instead)."""
    xyz = getattr(entity, "xyz", None)
    if xyz is not None:
        return (float(xyz[0]), float(xyz[1]), float(xyz[2]))
    if hasattr(entity, "x") and hasattr(entity, "y") and hasattr(entity, "z"):
        return (float(entity.x), float(entity.y), float(entity.z))
    return None


def _transform_kind(entity: Any) -> Optional[str]:
    """"geom" | "xb" | "point" | None (not transformable — Surface,
    Material, Ramp, ...)."""
    if hasattr(entity, "verts"):
        return "geom"
    if all(hasattr(entity, a) for a in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")):
        return "xb"
    if _point_xyz(entity) is not None:
        return "point"
    return None


def _selection_bbox(entities: List[Any]) -> Tuple[float, float, float, float, float, float]:
    """Combined bounding box across a whole multi-entity selection — the
    key correctness point for a *group* transform: rotating/scaling/
    mirroring must pivot the whole selection around ONE shared point, not
    each entity's own centroid independently (which would spin/scale every
    object in place instead of moving as one rigid group)."""
    boxes = []
    for entity in entities:
        box = entity.bbox() if hasattr(entity, "bbox") else None
        if box is None:
            xyz = _point_xyz(entity)
            if xyz is not None:
                x, y, z = xyz
                box = (x, x, y, y, z, z)
        if box is not None:
            boxes.append(box)
    if not boxes:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return (
        min(b[0] for b in boxes), max(b[1] for b in boxes),
        min(b[2] for b in boxes), max(b[3] for b in boxes),
        min(b[4] for b in boxes), max(b[5] for b in boxes),
    )


def _next_group_name(existing: set) -> str:
    n = 1
    while f"Group {n}" in existing:
        n += 1
    return f"Group {n}"


class ProjectExplorer(QTreeWidget):
    """Tree over the active project's entity collections. Never mutates
    directly — right-click emits a signal for MainWindow to act on, same
    as every other GUI-driven mutation in this app going through FdsApi."""

    entity_context_menu_requested = Signal()

    def __init__(self, api: FdsApi, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Project"])
        self._api = api
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._sub_ids = [api.subscribe(t, self._on_event) for t in _REFRESH_EVENTS]
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu_requested)
        self.refresh()

    def _on_event(self, event) -> None:
        self.refresh()

    def _on_context_menu_requested(self, pos) -> None:
        item = self.itemAt(pos)
        if item is None or item.data(0, Qt.UserRole) is None:
            return  # empty space or a category row — nothing to act on
        self.setCurrentItem(item)
        self.entity_context_menu_requested.emit()

    def refresh(self) -> None:
        self.clear()
        for label, attr in _ENTITY_COLLECTIONS:
            entities = getattr(self._api, attr).all()
            top = QTreeWidgetItem([f"{label} ({len(entities)})"])
            top.setIcon(0, icon_for_entity(attr))
            for entity in entities:
                text = getattr(entity, "name", repr(entity))
                child = QTreeWidgetItem([text])
                child.setData(0, Qt.UserRole, (attr, entity))
                child.setIcon(0, icon_for_entity(attr, entity, disabled=not getattr(entity, "enabled", True)))
                if not getattr(entity, "enabled", True):
                    child.setText(0, f"{text} (disabled)")
                    child.setForeground(0, QColor("gray"))
                top.addChild(child)
            self.addTopLevelItem(top)
        self.expandAll()

    def selected(self) -> Optional[Tuple[str, Any]]:
        """(manager_attr, entity) for the first selected entity row, or None
        (nothing / a category row selected). Single-entity operations
        (Copy/Cut/Duplicate/Delete/Edit Properties/rename/context-menu) all
        use this and are unaffected by multi-select being enabled — they
        just act on whichever row is "current" among the selection, same as
        before ExtendedSelection existed."""
        items = self.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.UserRole)

    def selected_entities(self) -> List[Tuple[str, Any]]:
        """(manager_attr, entity) for every selected entity row — category
        rows carry no UserRole data and are skipped. Used by multi-entity
        operations (Move/Rotate/Scale/Mirror/Group Selected)."""
        result = []
        for item in self.selectedItems():
            data = item.data(0, Qt.UserRole)
            if data is not None:
                result.append(data)
        return result

    def select_entity(self, attr: str, entity: Any) -> None:
        """Select the tree row for (attr, entity) — e.g. driven by a 3D
        viewport pick. Identity comparison (not ==): it's the exact same
        object reference the row was built from."""
        self.select_entities([(attr, entity)])

    def select_entities(self, pairs: List[Tuple[str, Any]]) -> None:
        """Select every tree row matching one of *pairs* — e.g. driven by a
        3D viewport multi-pick, or "Select Members" on a Group row. Replaces
        any prior selection, same as a fresh click — but only once at least
        one row actually matches; a pick that resolves to nothing (e.g. a
        stray entity no longer in the tree) leaves the existing selection
        untouched instead of blanking it, matching the pre-multi-select
        behavior of ``select_entity``."""
        wanted = [(attr, id(entity)) for attr, entity in pairs]
        matched: List[QTreeWidgetItem] = []
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                data = child.data(0, Qt.UserRole)
                if data is not None and (data[0], id(data[1])) in wanted:
                    matched.append(child)
        if not matched:
            return
        self.clearSelection()
        for item in matched:
            item.setSelected(True)
        # setCurrentItem(item) alone (no selection-model flags) resets the
        # selection to just *that* item — confirmed empirically it silently
        # undid the multi-select loop above. NoUpdate keeps "current" (for
        # keyboard nav) in sync without touching which rows are selected.
        self.setCurrentItem(matched[0], 0, QItemSelectionModel.NoUpdate)

    def find_entity_by_name(self, substring: str) -> Optional[QTreeWidgetItem]:
        """First entity row whose name contains *substring* (case-insensitive),
        or None. Category rows are never matched."""
        needle = substring.strip().lower()
        if not needle:
            return None
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                data = child.data(0, Qt.UserRole)
                if data is None:
                    continue
                _attr, entity = data
                if needle in getattr(entity, "name", "").lower():
                    return child
        return None

    def shutdown(self) -> None:
        for sub_id in self._sub_ids:
            self._api.unsubscribe(sub_id)


class MainWindow(QMainWindow):
    """Primary application window. The AI panel is one optional dock among many."""

    def __init__(self, api: Optional[FdsApi] = None) -> None:
        super().__init__()
        self.api = api or FdsApi()
        self.setWindowTitle("PyFDS")
        self.resize(1200, 750)
        self._current_project_path: Optional[str] = None
        self._clipboard_entity: Any = None
        self._view_bookmarks: dict = {}
        self._hvac_editor = None  # lazily-built singleton, see _on_hvac_network_editor

        self.dispatcher = AgentToolDispatcher(self.api)

        self.explorer = ProjectExplorer(self.api, self)
        self.explorer.itemDoubleClicked.connect(lambda item, col: self._on_edit_properties())
        self.explorer.entity_context_menu_requested.connect(self._on_explorer_context_menu)
        self.explorer_dock = QDockWidget("Project Explorer", self)
        self.explorer_dock.setObjectName("ProjectExplorerDock")
        self.explorer_dock.setWidget(self.explorer)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.explorer_dock)

        self.viewport_widget = self._build_viewport_widget()
        self.setCentralWidget(self.viewport_widget)
        if hasattr(self.viewport_widget, "entity_picked"):
            self.viewport_widget.entity_picked.connect(self.explorer.select_entity)
        if hasattr(self.viewport_widget, "selection_changed"):
            self.viewport_widget.selection_changed.connect(self.explorer.select_entities)
        if hasattr(self.viewport_widget, "box_footprint_picked"):
            self.viewport_widget.box_footprint_picked.connect(self._on_box_footprint_picked)

        self.agent_dock = self._build_agent_dock()
        self.addDockWidget(Qt.RightDockWidgetArea, self.agent_dock)

        self._build_menu()
        from .extras import install_extras
        install_extras(self)      # room/library/run-monitor/results-viewer entries (see extras.py)
        self._build_toolbar()
        from .icons import install_icons
        install_icons(self, "pyfds")      # task-coloured icons on every menu entry and toolbar button
        self._default_window_state = self.saveState()
        self._status_sub_ids = [self.api.subscribe(t, self._on_status_event) for t in _REFRESH_EVENTS]
        self._refresh_status()

    # ── Menu / actions ───────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        """Build the complete menu bar with all 149 items across 13 menus.

        PHASE 1 Implementation: All items are wired with handlers; backend
        integration is tracked via placeholder docstrings and TODO markers.
        """
        # Actions stashed on self.* are reused in the toolbar — checkable state
        # (e.g. Wireframe) stays in sync between menu and toolbar automatically.

        # ════════════════════════════════════════════════════════════════════════
        # FILE MENU (17 items)
        # ════════════════════════════════════════════════════════════════════════
        file_menu = self.menuBar().addMenu("&File")

        # Project lifecycle
        self._new_action = file_menu.addAction("&New", self._on_new)
        file_menu.addAction("New From &Template...", self._on_new_from_template)

        # Open / Recent
        self._open_action = file_menu.addAction("&Open...", self._on_open)
        self._recent_submenu = file_menu.addMenu("&Recent")
        self._rebuild_recent_menu()

        file_menu.addSeparator()

        # Save operations
        self._save_action = file_menu.addAction("&Save", self._on_save)
        self._save_as_action = file_menu.addAction("&Save As...", self._on_save_as)

        # Print (new)
        file_menu.addAction("&Print...", self._on_placeholder_print)

        file_menu.addSeparator()

        # Preferences (new)
        file_menu.addAction("&Preferences...", self._on_preferences)

        # Import submenu (new) - 6 items
        import_submenu = file_menu.addMenu("&Import")
        import_submenu.addAction("Import FDS File...", self._on_placeholder_import_fds)
        import_submenu.addAction("Import Geometry (STL)...", self._on_import_stl)
        import_submenu.addAction("Import Materials...", self._on_placeholder_import_materials)
        import_submenu.addAction("Import Scenarios...", self._on_placeholder_import_scenarios)
        import_submenu.addAction("Import Devices...", self._on_placeholder_import_devices)
        import_submenu.addAction("Import from Library...", self._on_placeholder_import_library)

        # Export submenu (new)
        export_submenu = file_menu.addMenu("&Export")
        export_submenu.addAction("Export as FDS...", self._on_export_as_fds)
        export_submenu.addAction("Export Geometry (STL)...", self._on_placeholder_export_stl)
        export_submenu.addAction("Export Configuration...", self._on_placeholder_export_config)

        file_menu.addSeparator()

        # Project Settings (new)
        file_menu.addAction("Pro&ject Settings...", self._on_project_settings)

        file_menu.addSeparator()

        # Export Database (existing, kept)
        export_db_menu = file_menu.addMenu("E&xport Database")
        export_db_menu.addAction("&Materials...", lambda: self._on_export_db("materials"))
        export_db_menu.addAction("&Surfaces...", lambda: self._on_export_db("surfaces"))
        export_db_menu.addAction("&Fuels...", lambda: self._on_export_db("fuels"))
        export_db_menu.addAction("&All (folder)...", self._on_export_db_all)

        file_menu.addSeparator()

        # Exit
        file_menu.addAction("E&xit", self.close)

        # ════════════════════════════════════════════════════════════════════════
        # EDIT MENU (18 items)
        # ════════════════════════════════════════════════════════════════════════
        edit_menu = self.menuBar().addMenu("&Edit")

        # Undo/Redo
        self._undo_action = edit_menu.addAction("&Undo", self.api.history.undo)
        self._redo_action = edit_menu.addAction("&Redo", self.api.history.redo)

        edit_menu.addSeparator()

        # Clipboard operations (new)
        self._cut_action = edit_menu.addAction("Cu&t", self._on_cut)
        self._cut_action.setShortcut(QKeySequence.Cut)
        self._copy_action = edit_menu.addAction("&Copy", self._on_copy)
        self._copy_action.setShortcut(QKeySequence.Copy)
        self._paste_action = edit_menu.addAction("&Paste", self._on_paste)
        self._paste_action.setShortcut(QKeySequence.Paste)
        self._paste_action.setEnabled(False)

        edit_menu.addSeparator()

        # Delete / Duplicate
        self._delete_action = edit_menu.addAction("&Delete Selected", self._on_delete_selected)
        self._delete_action.setShortcut(QKeySequence.Delete)
        self._duplicate_action = edit_menu.addAction("Dup&licate", self._on_duplicate)

        edit_menu.addSeparator()

        # Properties
        edit_menu.addAction("Edit &Properties...", self._on_edit_properties)

        edit_menu.addSeparator()

        # Find / Replace
        find_action = edit_menu.addAction("&Find...", self._on_find)
        find_action.setShortcut(QKeySequence.Find)
        replace_action = edit_menu.addAction("&Replace...", self._on_placeholder_replace)
        replace_action.setShortcut(QKeySequence.Replace)

        edit_menu.addSeparator()

        # Selection / Organization (new)
        edit_menu.addAction("Select &All", self._on_placeholder_select_all)
        edit_menu.addAction("&Filter...", self._on_placeholder_filter)
        edit_menu.addAction("&Group Objects", self._on_group_selected)
        edit_menu.addAction("&Ungroup Objects", self._on_ungroup_selected)

        edit_menu.addSeparator()

        # Transform operations (new) — placeholder until 3D viewport supports
        edit_menu.addAction("&Move Selected...", self._on_move_selected)
        edit_menu.addAction("&Rotate Selected...", self._on_rotate_selected)
        edit_menu.addAction("Sc&ale Selected...", self._on_scale_selected)
        edit_menu.addAction("&Mirror Selected", self._on_mirror_selected)
        edit_menu.addAction("&Snap Settings...", self._on_snap_settings)

        # ════════════════════════════════════════════════════════════════════════
        # VIEW MENU (16 items)
        # ════════════════════════════════════════════════════════════════════════
        view_menu = self.menuBar().addMenu("&View")

        # View navigation
        self._reset_view_action = view_menu.addAction("&Reset View", self._on_reset_view)

        # Standard camera presets (existing, 7 items)
        views_submenu = view_menu.addMenu("&Standard Views")
        self._camera_preset_actions = {}
        for label, preset in _CAMERA_PRESETS:
            action = views_submenu.addAction(label, lambda checked=False, p=preset: self._on_camera_preset(p))
            self._camera_preset_actions[preset] = action

        view_menu.addSeparator()

        # Render modes (new and existing)
        self._wireframe_action = view_menu.addAction("&Wireframe Mode")
        self._wireframe_action.setCheckable(True)
        self._wireframe_action.triggered.connect(self._on_toggle_wireframe)

        shaded_action = view_menu.addAction("&Shaded Mode")
        shaded_action.setCheckable(True)
        shaded_action.triggered.connect(self._on_placeholder_toggle_shaded)

        realistic_action = view_menu.addAction("&Realistic Mode")
        realistic_action.setCheckable(True)
        realistic_action.triggered.connect(self._on_placeholder_toggle_realistic)

        view_menu.addSeparator()

        # Display toggles
        show_submenu = view_menu.addMenu("&Show/Hide")
        for label, flag in _VISIBILITY_TOGGLES:
            action = show_submenu.addAction(label)
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(lambda checked, f=flag: self._on_toggle_visibility(f, checked))

        # Additional show/hide items (new)
        show_submenu.addSeparator()
        show_submenu.addAction("&Grid", self._on_placeholder_toggle_grid)
        show_submenu.addAction("&Axes", self._on_placeholder_toggle_axes)

        view_menu.addSeparator()

        # Section view (new)
        view_menu.addAction("&Section View", self._on_placeholder_section_view)

        # Split view (new)
        split_submenu = view_menu.addMenu("&Split")
        split_submenu.addAction("Horizontal", self._on_placeholder_split_horizontal)
        split_submenu.addAction("Vertical", self._on_placeholder_split_vertical)
        split_submenu.addAction("Four-Way", self._on_placeholder_split_four_way)

        # Fullscreen (new)
        view_menu.addAction("&Fullscreen", self._on_toggle_fullscreen)

        view_menu.addSeparator()

        # Bookmarks (new) — in-memory (session-only) named camera states
        view_menu.addAction("Save &Bookmark...", self._on_save_bookmark)
        view_menu.addAction("Load &Bookmark...", self._on_load_bookmark)

        view_menu.addSeparator()

        # Theme (new)
        theme_submenu = view_menu.addMenu("&Theme")
        theme_submenu.addAction("&Light", self._on_placeholder_theme_light)
        theme_submenu.addAction("&Dark", self._on_placeholder_theme_dark)

        # Units (new)
        units_submenu = view_menu.addMenu("&Units")
        units_submenu.addAction("&Metric (m, kg, s)", self._on_placeholder_units_metric)
        units_submenu.addAction("&Imperial (ft, lbm, s)", self._on_placeholder_units_imperial)

        # ════════════════════════════════════════════════════════════════════════
        # DRAW MENU (14 items) — Expanded from 4 to include primitive shapes
        # ════════════════════════════════════════════════════════════════════════
        draw_menu = self.menuBar().addMenu("&Draw")

        # Primitive shapes draw mode
        draw_group = QActionGroup(self)
        draw_group.setExclusive(True)
        self._draw_actions = {}

        # Basic drawing tools (existing)
        for label, tool_name in _DRAW_ACTIONS:
            action = draw_menu.addAction(label)
            action.setCheckable(True)
            draw_group.addAction(action)
            action.triggered.connect(lambda checked=False, t=tool_name: self._on_set_draw_mode(t))
            self._draw_actions[tool_name] = action

        draw_menu.addSeparator()

        # Additional primitive shapes (new) — dialog-driven, via api.geom
        # (NOT the box-footprint draw-mode pipeline: these have no natural
        # two-click XB footprint, and there is no "add_cylinder"/"add_sphere"/
        # "add_cone" agent tool for _on_box_footprint_picked to dispatch to).
        draw_menu.addAction("Draw &Cylinder...", self._on_draw_cylinder)
        draw_menu.addAction("Draw &Sphere...", self._on_draw_sphere)
        draw_menu.addAction("Draw C&one...", self._on_draw_cone)
        draw_menu.addAction("Draw &Pipe...", lambda: self._on_placeholder_geometry_primitive("Pipe"))
        draw_menu.addAction("Draw &Beam...", lambda: self._on_placeholder_geometry_primitive("Beam"))

        draw_menu.addSeparator()

        # Architectural elements (new) — no backend primitive yet
        for elem in ["Wall", "Floor", "Ceiling", "Stair", "Door", "Window", "Ramp"]:
            draw_menu.addAction(f"Draw {elem}...", lambda checked=False, e=elem: self._on_placeholder_geometry_primitive(e))

        draw_menu.addSeparator()

        # Boolean operations (new)
        bool_submenu = draw_menu.addMenu("&Boolean Operations")
        bool_submenu.addAction("&Union", self._on_boolean_union)
        bool_submenu.addAction("&Difference", self._on_boolean_difference)
        bool_submenu.addAction("&Intersection", self._on_boolean_intersection)

        draw_menu.addSeparator()

        # Cancel draw mode
        draw_menu.addAction("&Cancel Draw Mode", self._on_cancel_draw_mode)

        # ════════════════════════════════════════════════════════════════════════
        # MODEL MENU (20 items)
        # ════════════════════════════════════════════════════════════════════════
        model_menu = self.menuBar().addMenu("&Model")

        # Existing entity add actions
        for label, tool_name in _MODEL_ACTIONS:
            model_menu.addAction(label, lambda checked=False, t=tool_name: self._on_add_entity(t))

        model_menu.addSeparator()

        # Additional model items (new)
        model_menu.addAction("Add &Control Element...", self._on_placeholder_add_control)
        model_menu.addAction("Add &Property / Prop...", self._on_placeholder_add_prop)
        model_menu.addAction("Add S&pecies...", self._on_placeholder_add_species)

        model_menu.addSeparator()

        # Simulation configuration
        model_menu.addAction("&Simulation Parameters...", self._on_simulation_parameters)

        model_menu.addSeparator()

        # Validation and repair
        self._validate_action = model_menu.addAction("&Validate Project", self._on_validate)
        model_menu.addAction("Auto-&Fix", self._on_auto_fix)
        model_menu.addAction("Geometry &Repair...", self._on_placeholder_geometry_repair)

        model_menu.addSeparator()

        # Geometry operations
        model_menu.addAction("Convert to &Blocks (Voxelize STL)...", self._on_convert_to_blocks)

        # ════════════════════════════════════════════════════════════════════════
        # DEVICES MENU (12 items) — Expanded from 3
        # ════════════════════════════════════════════════════════════════════════
        devices_menu = self.menuBar().addMenu("&Devices")

        # Existing device types
        for label, tool_name in _DEVICE_ACTIONS:
            devices_menu.addAction(label, lambda checked=False, t=tool_name: self._on_add_entity(t))

        devices_menu.addSeparator()

        # Additional device types (new)
        devices_menu.addAction("Add &Heat Flux Sensor...", self._on_add_heat_flux)
        devices_menu.addAction("Add &Smoke Detector...", self._on_add_smoke_detector)
        devices_menu.addAction("Add &Beam Detector...", self._on_add_beam_detector)
        devices_menu.addAction("Add &Gas Sensor...", self._on_add_gas_sensor)
        devices_menu.addAction("Add &Anemometer...", self._on_add_anemometer)
        devices_menu.addAction("Add &Nozzle...", self._on_add_nozzle)
        devices_menu.addAction("Add &Velocity Probe...", self._on_add_velocity_probe)
        devices_menu.addAction("Add &Pressure Probe...", self._on_add_pressure_probe)

        devices_menu.addSeparator()

        # Device management
        devices_menu.addAction("Device &Labels", self._on_placeholder_device_labels)

        # ════════════════════════════════════════════════════════════════════════
        # OUTPUT MENU (5 items) — Complete
        # ════════════════════════════════════════════════════════════════════════
        output_menu = self.menuBar().addMenu("&Output")

        for label, tool_name in _OUTPUT_ACTIONS:
            output_menu.addAction(label, lambda checked=False, t=tool_name: self._on_add_entity(t))

        output_menu.addSeparator()

        # Output Frequency (new)
        output_menu.addAction("Output &Frequency...", self._on_output_frequency)

        # ════════════════════════════════════════════════════════════════════════
        # HVAC MENU (9 items) — Expanded from 6
        # ════════════════════════════════════════════════════════════════════════
        hvac_menu = self.menuBar().addMenu("HVA&C")

        # Existing HVAC components
        for label, tool_name in _HVAC_ACTIONS:
            hvac_menu.addAction(label, lambda checked=False, t=tool_name: self._on_add_entity(t))

        hvac_menu.addSeparator()

        # Additional HVAC tools (new)
        hvac_menu.addAction("&Network Editor", self._on_hvac_network_editor)
        hvac_menu.addAction("&Solver Setup...", self._on_hvac_solver_setup)
        hvac_menu.addAction("&Diagnostics", self._on_hvac_diagnostics)

        # ════════════════════════════════════════════════════════════════════════
        # SCENARIOS MENU (7 items) — Complete
        # ════════════════════════════════════════════════════════════════════════
        scenarios_menu = self.menuBar().addMenu("Sc&enarios")

        scenarios_menu.addAction("&New Scenario...", self._on_new_scenario)
        scenarios_menu.addAction("&Clone Scenario...", self._on_clone_scenario)

        scenarios_menu.addSeparator()

        scenarios_menu.addAction("&Apply Scenario...", self._on_apply_scenario_dialog)
        scenarios_menu.addAction("&Reset Active Scenario", self._on_reset_scenario)

        scenarios_menu.addSeparator()

        scenarios_menu.addAction("&Export All Scenarios (folder)...", self._on_export_scenarios)
        scenarios_menu.addAction("&Import Scenarios...", self._on_placeholder_import_scenarios_dialog)

        # ════════════════════════════════════════════════════════════════════════
        # FLOORS MENU (5 items) — Complete
        # ════════════════════════════════════════════════════════════════════════
        floors_menu = self.menuBar().addMenu("&Floors")

        floors_menu.addAction("&Define Floor...", self._on_define_floor)
        floors_menu.addAction("Auto-&Assign All", self._on_auto_assign_floors)
        floors_menu.addAction("A&ssign Selected Entity...", self._on_assign_to_floor)

        floors_menu.addSeparator()

        floors_menu.addAction("&Export Floors...", self._on_export_floors)
        floors_menu.addAction("&Import Floors...", self._on_import_floors)

        # ════════════════════════════════════════════════════════════════════════
        # RUN MENU (12 items) — Expanded from 4
        # ════════════════════════════════════════════════════════════════════════
        run_menu = self.menuBar().addMenu("&Run")

        # Simulation execution
        self._run_action = run_menu.addAction("&Run Simulation...", self._on_run_simulation)
        run_menu.addAction("&Resume Simulation...", self._on_resume_simulation)

        # Smokeview integration (new)
        self._open_smokeview_action = run_menu.addAction("Open &Smokeview After Run")
        self._open_smokeview_action.setCheckable(True)
        self._open_smokeview_action.setChecked(True)

        run_menu.addSeparator()

        # Parallel computing options (new)
        run_menu.addAction("&OpenMP Environment...", self._on_openmp_environment)
        run_menu.addAction("Run &Parallel (MPI)...", self._on_placeholder_run_parallel_mpi)
        run_menu.addAction("&MPI Preview", self._on_placeholder_mpi_preview)

        run_menu.addSeparator()

        # Simulation control (new)
        run_menu.addAction("&Pause Simulation", self._on_placeholder_pause_simulation)
        run_menu.addAction("Sto&p Simulation", self._on_placeholder_stop_simulation)

        run_menu.addSeparator()

        # GPU and monitoring (new)
        run_menu.addAction("&GPU Settings...", self._on_placeholder_gpu_settings)
        run_menu.addAction("&Monitor Simulation...", self._on_placeholder_monitor_simulation)

        # ════════════════════════════════════════════════════════════════════════
        # RESULTS MENU (14 items) — Expanded from 5
        # ════════════════════════════════════════════════════════════════════════
        results_menu = self.menuBar().addMenu("&Results")

        # Smokeview and file access
        results_menu.addAction("&Open Smokeview...", self._on_open_smokeview_results)
        results_menu.addAction("Open Results &Folder...", self._on_open_results_folder)

        results_menu.addSeparator()

        # Data browsing (new and existing)
        results_menu.addAction("View &Time History...", self._on_view_time_history)
        results_menu.addAction("&Slice Browser...", self._on_slice_browser)
        results_menu.addAction("&Boundary Browser...", self._on_boundary_browser)
        results_menu.addAction("&Plot Manager...", self._on_plot_manager)
        results_menu.addAction("&Isosurface Settings...", self._on_isosurface_settings)

        results_menu.addSeparator()

        # Archive and export
        results_menu.addAction("&Archive Results...", self._on_archive_results)
        results_menu.addAction("&Restore Results...", self._on_restore_results)

        results_menu.addSeparator()

        # Data export and reporting (new)
        results_menu.addAction("&Export CSV...", self._on_export_csv)
        results_menu.addAction("&Generate Report...", self._on_generate_report)
        results_menu.addAction("&Export Animation...", self._on_export_animation)
        results_menu.addAction("&Batch Export...", self._on_batch_export)

        # ════════════════════════════════════════════════════════════════════════
        # TOOLS MENU (11 items) — NEW MENU
        # ════════════════════════════════════════════════════════════════════════
        tools_menu = self.menuBar().addMenu("&Tools")

        # Validation and diagnostics
        tools_menu.addAction("&Validation...", self._on_tools_validation)
        tools_menu.addAction("&Find Errors...", self._on_find_errors)
        tools_menu.addAction("&Mesh Diagnostics...", self._on_mesh_diagnostics)
        tools_menu.addAction("&Geometry Repair...", self._on_placeholder_tools_geometry_repair)
        tools_menu.addAction("&Mesh Checker...", self._on_mesh_checker)

        tools_menu.addSeparator()

        # Utilities
        tools_menu.addAction("&Plugin Manager...", self._on_plugin_manager)
        tools_menu.addAction("&Preferences...", self._on_preferences)
        tools_menu.addAction("&Units Conversion...", self._on_units_conversion)
        tools_menu.addAction("&Calculator", self._on_calculator)

        tools_menu.addSeparator()

        # Development/preview
        tools_menu.addAction("&FDS Preview (EXPERIMENTAL)...", self._on_fds_preview)
        tools_menu.addAction("&Script Console...", self._on_placeholder_script_console)

        # ════════════════════════════════════════════════════════════════════════
        # WINDOW MENU (4 items) — NEW MENU
        # ════════════════════════════════════════════════════════════════════════
        window_menu = self.menuBar().addMenu("&Window")

        panels_menu = window_menu.addMenu("Show &Panels")
        panels_menu.addAction(self.explorer_dock.toggleViewAction())
        panels_menu.addAction(self.agent_dock.toggleViewAction())
        window_menu.addAction("&Layouts...", self._on_layouts)
        window_menu.addAction("&Workspace...", self._on_workspace)
        window_menu.addSeparator()
        window_menu.addAction("&Reset Window Layout", self._on_reset_window_layout)

        # ════════════════════════════════════════════════════════════════════════
        # HELP MENU (8 items) — Expanded from 4
        # ════════════════════════════════════════════════════════════════════════
        help_menu = self.menuBar().addMenu("&Help")

        help_menu.addAction("&FDS User Guide", lambda: self._on_open_doc(_FDS_USER_GUIDE))
        help_menu.addAction("&Smokeview Verification Guide", lambda: self._on_open_doc(_SMV_VERIFICATION_GUIDE))
        help_menu.addAction("Pyro&Sim User Manual (reference)", lambda: self._on_open_doc(_PYROSIM_USER_MANUAL))

        help_menu.addSeparator()

        # Learning resources (new)
        help_menu.addAction("&Examples...", self._on_placeholder_examples)
        help_menu.addAction("&Tutorials...", self._on_placeholder_tutorials)
        help_menu.addAction("&Keyboard Shortcuts...", self._on_keyboard_shortcuts)

        help_menu.addSeparator()

        # About and updates (new)
        help_menu.addAction("&Check for Updates...", self._on_placeholder_check_updates)
        help_menu.addAction("&About PyFDS", self._on_about)


    # ═════════════════════════════════════════════════════════════════════════════


    def _build_toolbar(self) -> None:
        """Quick-access icon-free toolbar — reuses the exact QAction objects
        from the menu bar (see _build_menu), so this is pure UX convenience,
        not a second code path."""
        bar = self.addToolBar("Quick Access")
        bar.setObjectName("QuickAccessToolBar")
        bar.setMovable(False)
        bar.addAction(self._new_action)
        bar.addAction(self._open_action)
        bar.addAction(self._save_as_action)
        bar.addSeparator()
        bar.addAction(self._undo_action)
        bar.addAction(self._redo_action)
        bar.addAction(self._delete_action)
        bar.addSeparator()
        bar.addAction(self._reset_view_action)
        bar.addAction(self._camera_preset_actions[CameraPreset.ISOMETRIC])
        bar.addAction(self._wireframe_action)
        bar.addSeparator()
        bar.addAction(self._validate_action)
        bar.addAction(self._run_action)

    # ── File Menu Placeholders ──────────────────────────────────────────────────

    def _on_save(self) -> None:
        """Save to the last-used path; falls back to Save As if the project
        has never been saved/opened in this session."""
        if self._current_project_path is None:
            self._on_save_as()
            return
        try:
            self.api.save(self._current_project_path)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))


    def _on_placeholder_print(self) -> None:
        """Print project or view.

        TODO: Implement Print
        Backend Status: NEEDS BACKEND
        Phase: Phase 3
        """
        QMessageBox.information(
            self,
            "Coming Soon",
            "Print functionality will be available in Phase 3.\n\n"
            "This is a placeholder."
        )


    def _on_preferences(self) -> None:
        """Shared by File > Preferences and Tools > Preferences — one real
        dialog, not two separate placeholders, since they're the same thing."""
        cfg = self.api.config
        schema = {
            "type": "object",
            "properties": {
                "fds_binary": {"type": "string", "default": cfg.get("fds_binary", "fds")},
                "smv_binary": {"type": "string", "default": cfg.get("smv_binary", "smokeview")},
                "mpiexec_binary": {"type": "string", "default": cfg.get("mpiexec_binary", "mpiexec")},
                "default_mpi_processes": {"type": "integer", "default": cfg.get("default_mpi_processes", 1)},
                "max_job_workers": {"type": "integer", "default": cfg.get("max_job_workers", 4)},
                "auto_validate": {"type": "boolean", "default": cfg.get("auto_validate", True)},
                "log_level": {"type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR"],
                              "default": cfg.get("log_level", "INFO")},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Preferences", "Session overrides — not written to disk.", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        cfg.set_many(dialog.values())


    def _recent_paths(self) -> list:
        settings = QSettings("PyFDS", "PyFDS")
        paths = settings.value("recent_projects", [])
        if isinstance(paths, str):
            paths = [paths]
        return list(paths or [])

    def _add_recent_path(self, path: str) -> None:
        resolved = str(Path(path).resolve())
        paths = [p for p in self._recent_paths() if p != resolved]
        paths.insert(0, resolved)
        QSettings("PyFDS", "PyFDS").setValue("recent_projects", paths[:5])
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        self._recent_submenu.clear()
        paths = self._recent_paths()
        if not paths:
            action = self._recent_submenu.addAction("(No Recent Projects)")
            action.setEnabled(False)
            return
        for path in paths:
            label = Path(path).name or path
            self._recent_submenu.addAction(label, lambda checked=False, p=path: self._on_open_recent(p))

    def _on_open_recent(self, path: str) -> None:
        if not Path(path).exists():
            QMessageBox.warning(self, "File not found", f"{path}\n\nThis file no longer exists.")
            paths = [p for p in self._recent_paths() if p != path]
            QSettings("PyFDS", "PyFDS").setValue("recent_projects", paths)
            self._rebuild_recent_menu()
            return
        try:
            self.api.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self._current_project_path = path
        self._add_recent_path(path)


    def _on_placeholder_import_fds(self) -> None:
        """Import FDS file into current project."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "FDS file import will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_import_stl(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import STL Geometry", "", "STL Files (*.stl)")
        if not path:
            return
        surf_id, ok = QInputDialog.getText(self, "Import STL", "Surface ID (material/boundary condition):", text="INERT")
        if not ok:
            return
        try:
            self.api.geom.load_stl(path, surf_id=surf_id or "INERT")
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
        else:
            self.explorer.refresh()


    def _on_placeholder_import_materials(self) -> None:
        """Import materials from external source."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Materials import will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_import_scenarios(self) -> None:
        """Import scenario definitions."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Scenario import will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_import_devices(self) -> None:
        """Import device definitions."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Device import will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_import_library(self) -> None:
        """Import from engineering libraries."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Library import will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_export_as_fds(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export as FDS", "", "FDS Files (*.fds)")
        if not path:
            return
        if not path.lower().endswith(".fds"):
            path += ".fds"
        try:
            self.api.save(path)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))


    def _on_placeholder_export_stl(self) -> None:
        """Export geometry as STL."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "STL export will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_export_config(self) -> None:
        """Export project configuration."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Configuration export will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_project_settings(self) -> None:
        project = self.api.project
        schema = {
            "type": "object",
            "properties": {
                "chid": {"type": "string", "default": project.chid,
                          "description": "FDS CHID — base name for all output files."},
                "title": {"type": "string", "default": project.title},
            },
            "required": ["chid"],
        }
        dialog = SchemaFormDialog("Project Settings", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self.api.set_property(project, "chid", values["chid"])
            self.api.set_property(project, "title", values.get("title", ""))
        except Exception as exc:
            QMessageBox.critical(self, "Could not update project settings", str(exc))


    # ── Edit Menu Placeholders ──────────────────────────────────────────────────

    def _on_cut(self) -> None:
        selected = self.explorer.selected()
        if selected is None:
            return
        self._on_copy()
        if self._clipboard_entity is not None:
            self._on_delete_selected()

    def _on_copy(self) -> None:
        selected = self.explorer.selected()
        if selected is None:
            return
        attr, entity = selected
        if attr in ("scenarios", "floors"):
            QMessageBox.information(self, "Not supported", f"{attr.title()} cannot be copied.")
            return
        self._clipboard_entity = entity.model_copy(deep=True)
        self._paste_action.setEnabled(True)

    def _on_paste(self) -> None:
        if self._clipboard_entity is None:
            return
        new_entity = self._clipboard_entity.model_copy(deep=True)
        new_entity._uid = str(uuid.uuid4())
        if hasattr(new_entity, "name"):
            new_entity.name = f"{new_entity.name}_copy"
        try:
            self.api.history.execute(AddEntityCommand(self.api.project, new_entity))
        except Exception as exc:
            QMessageBox.critical(self, "Could not paste", str(exc))
        else:
            self.explorer.refresh()

    def _on_duplicate(self) -> None:
        selected = self.explorer.selected()
        if selected is None:
            return
        attr, entity = selected
        if attr in ("scenarios", "floors"):
            QMessageBox.information(self, "Not supported", f"{attr.title()} cannot be duplicated.")
            return
        self._clipboard_entity = entity.model_copy(deep=True)
        self._paste_action.setEnabled(True)
        self._on_paste()


    def _on_placeholder_replace(self) -> None:
        """Find and replace objects/properties."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Find & Replace will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_select_all(self) -> None:
        """Select all objects in scene."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Select All will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_filter(self) -> None:
        """Filter displayed objects by type/property."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Filter will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    # ── Group / Ungroup ──────────────────────────────────────────────────────

    def _attr_for_entity(self, entity: Any) -> Optional[str]:
        """Which api.<attr> collection *entity* lives in — needed to feed
        entities resolved outside the tree (e.g. GroupManager.members())
        back into explorer.select_entities(), which matches by (attr, id)
        pairs the same way the tree itself stores them."""
        for _, attr in _ENTITY_COLLECTIONS:
            try:
                collection = getattr(self.api, attr).all()
            except Exception:
                continue
            if any(e is entity for e in collection):
                return attr
        return None

    def _on_group_selected(self) -> None:
        pairs = self.explorer.selected_entities()
        if not pairs:
            QMessageBox.information(self, "Group Objects", "Nothing selected.")
            return
        existing = {g.name for g in self.api.groups.all()}
        name, ok = QInputDialog.getText(
            self, "Group Objects", "Group name:", text=_next_group_name(existing)
        )
        if not ok or not name:
            return
        if self.api.groups.get(name) is None:
            self.api.groups.create(name)
        for _, entity in pairs:
            self.api.groups.assign(entity, name)
        # Membership is a plain dict mutation, not a Command (same as
        # FloorManager.assign()) — it fires no COMMAND_EXECUTED event, so
        # the tree needs an explicit refresh.
        self.explorer.refresh()
        self.statusBar().showMessage(f"Grouped {len(pairs)} object(s) as {name!r}.")

    def _on_ungroup_selected(self) -> None:
        pairs = self.explorer.selected_entities()
        if not pairs:
            QMessageBox.information(self, "Ungroup Objects", "Nothing selected.")
            return
        count = 0
        for attr, entity in pairs:
            if attr == "groups":
                # A Group row itself was selected — ungroup (and remove)
                # the whole group rather than treating the Group object
                # itself as something to unassign.
                for member in self.api.groups.members(entity.name):
                    self.api.groups.unassign(member)
                    count += 1
                self.api.groups.delete_group(entity.name)
            elif self.api.groups.group_of(entity) is not None:
                self.api.groups.unassign(entity)
                count += 1
        self.explorer.refresh()
        self.statusBar().showMessage(f"Ungrouped {count} object(s).")

    def _on_select_group_members(self, group_name: str) -> None:
        pairs = []
        for member in self.api.groups.members(group_name):
            attr = self._attr_for_entity(member)
            if attr is not None:
                pairs.append((attr, member))
        if not pairs:
            QMessageBox.information(self, "Empty group", f"Group {group_name!r} has no members.")
            return
        self.explorer.select_entities(pairs)

    # ── Move / Rotate / Scale / Mirror Selected ─────────────────────────────

    def _resolve_transform_targets(self) -> List[Any]:
        """Selected entities, expanded so selecting one grouped entity pulls
        in its whole group as one rigid transform target — this is what
        makes Group/Ungroup useful for Move/Rotate/Scale/Mirror, not just
        an Explorer-tree decoration."""
        resolved: List[Any] = []
        seen = set()
        for _, entity in self.explorer.selected_entities():
            group_name = self.api.groups.group_of(entity)
            members = self.api.groups.members(group_name) if group_name else [entity]
            for member in members:
                key = id(member)
                if key not in seen:
                    seen.add(key)
                    resolved.append(member)
        return resolved

    def _apply_transform(self, entities: List[Any], title: str, build_command_for) -> None:
        """Shared plumbing for Move/Rotate/Scale/Mirror Selected:
        build_command_for(kind, entity, bbox) returns a Command (or None to
        skip that entity) — one command per transformable entity, executed
        as a single GroupCommand so the whole multi-entity operation is one
        undo step. An entity whose command constructor rejects the given
        parameters (e.g. RotateCommand's XB entities only accept multiples
        of 90°) is skipped rather than aborting the whole batch."""
        bbox = _selection_bbox(entities)
        commands = []
        skipped = 0
        for entity in entities:
            kind = _transform_kind(entity)
            if kind is None:
                skipped += 1
                continue
            try:
                cmd = build_command_for(kind, entity, bbox)
            except Exception:
                cmd = None
            if cmd is not None:
                commands.append(cmd)
            else:
                skipped += 1
        if not commands:
            QMessageBox.information(self, title, "Nothing in the selection can be transformed.")
            return
        try:
            self.api.history.execute(GroupCommand(commands, label=title))
        except Exception as exc:
            QMessageBox.critical(self, f"Could not {title.lower()}", str(exc))
            return
        suffix = f" ({skipped} skipped)" if skipped else ""
        self.statusBar().showMessage(f"{title}: {len(commands)} object(s) transformed{suffix}.")

    def _on_move_selected(self) -> None:
        entities = self._resolve_transform_targets()
        if not entities:
            QMessageBox.information(self, "Move Selected", "Nothing selected.")
            return
        schema = {
            "type": "object",
            "properties": {
                "dx": {"type": "number", "default": 0.0},
                "dy": {"type": "number", "default": 0.0},
                "dz": {"type": "number", "default": 0.0},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Move Selected", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        dx, dy, dz = values.get("dx", 0.0), values.get("dy", 0.0), values.get("dz", 0.0)

        def build(kind, entity, bbox):
            if kind == "xb":
                return MoveObstCommand(entity, dx=dx, dy=dy, dz=dz)
            if kind == "geom":
                return TranslateGeomCommand(entity, dx=dx, dy=dy, dz=dz)
            if kind == "point":
                return TranslatePointCommand(entity, dx=dx, dy=dy, dz=dz)
            return None

        self._apply_transform(entities, "Move Selected", build)

    def _on_rotate_selected(self) -> None:
        entities = self._resolve_transform_targets()
        if not entities:
            QMessageBox.information(self, "Rotate Selected", "Nothing selected.")
            return
        schema = {
            "type": "object",
            "properties": {
                "degrees": {"type": "number", "default": 90.0,
                            "description": "About Z, shared pivot. XB entities "
                                           "(Obstruction/Mesh/Vent/Hole) only "
                                           "accept multiples of 90."},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Rotate Selected", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        degrees = dialog.values().get("degrees", 90.0)

        def build(kind, entity, bbox):
            ox, oy = (bbox[0] + bbox[1]) / 2, (bbox[2] + bbox[3]) / 2
            if kind == "xb":
                return RotateCommand(entity, degrees=degrees, origin=(ox, oy))
            if kind == "geom":
                return RotateGeomCommand(entity, degrees=degrees, origin=(ox, oy))
            if kind == "point":
                x, y, z = _point_xyz(entity)
                rad = math.radians(degrees)
                dxr, dyr = x - ox, y - oy
                nx = ox + dxr * math.cos(rad) - dyr * math.sin(rad)
                ny = oy + dxr * math.sin(rad) + dyr * math.cos(rad)
                return TranslatePointCommand(entity, dx=nx - x, dy=ny - y, dz=0.0)
            return None

        self._apply_transform(entities, "Rotate Selected", build)

    def _on_scale_selected(self) -> None:
        entities = self._resolve_transform_targets()
        if not entities:
            QMessageBox.information(self, "Scale Selected", "Nothing selected.")
            return
        schema = {
            "type": "object",
            "properties": {
                "factor": {"type": "number", "default": 1.0,
                           "description": "Uniform scale about the selection's shared centroid."},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Scale Selected", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        factor = dialog.values().get("factor", 1.0)

        def build(kind, entity, bbox):
            origin = ((bbox[0] + bbox[1]) / 2, (bbox[2] + bbox[3]) / 2, (bbox[4] + bbox[5]) / 2)
            if kind == "xb":
                return ScaleCommand(entity, factor=factor, origin=origin)
            if kind == "geom":
                return ScaleGeomCommand(entity, factor=factor, origin=origin)
            if kind == "point":
                x, y, z = _point_xyz(entity)
                ox, oy, oz = origin
                nx, ny, nz = ox + (x - ox) * factor, oy + (y - oy) * factor, oz + (z - oz) * factor
                return TranslatePointCommand(entity, dx=nx - x, dy=ny - y, dz=nz - z)
            return None

        self._apply_transform(entities, "Scale Selected", build)

    def _on_mirror_selected(self) -> None:
        entities = self._resolve_transform_targets()
        if not entities:
            QMessageBox.information(self, "Mirror Selected", "Nothing selected.")
            return
        schema = {
            "type": "object",
            "properties": {
                "axis": {"type": "string", "enum": ["X", "Y", "Z"], "default": "X"},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Mirror Selected", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        axis_idx = {"X": 0, "Y": 1, "Z": 2}[dialog.values().get("axis", "X")]

        def build(kind, entity, bbox):
            lo, hi = bbox[axis_idx * 2], bbox[axis_idx * 2 + 1]
            position = (lo + hi) / 2
            if kind == "xb":
                return MirrorCommand(entity, axis=axis_idx, position=position)
            if kind == "geom":
                return MirrorGeomCommand(entity, axis=axis_idx, position=position)
            if kind == "point":
                coords = list(_point_xyz(entity))
                old = coords[axis_idx]
                coords[axis_idx] = 2 * position - old
                nx, ny, nz = coords
                x, y, z = _point_xyz(entity)
                return TranslatePointCommand(entity, dx=nx - x, dy=ny - y, dz=nz - z)
            return None

        self._apply_transform(entities, "Mirror Selected", build)


    def _on_snap_settings(self) -> None:
        snap = self.api.viewport.state.snap
        schema = {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": snap.enabled},
                "grid_size": {"type": "number", "default": snap.grid_size, "description": "Metres per grid division."},
                "angle_step_deg": {"type": "number", "default": snap.angle_step_deg},
                "snap_to_grid": {"type": "boolean", "default": snap.snap_to_grid},
                "snap_to_vertex": {"type": "boolean", "default": snap.snap_to_vertex},
                "snap_to_edge": {"type": "boolean", "default": snap.snap_to_edge},
                "snap_to_face": {"type": "boolean", "default": snap.snap_to_face},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Snap Settings", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.api.viewport.set_snap(**dialog.values())


    # ── View Menu Placeholders ──────────────────────────────────────────────────

    def _on_placeholder_toggle_shaded(self, checked: bool) -> None:
        """Toggle shaded rendering mode."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Shaded mode will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_toggle_realistic(self, checked: bool) -> None:
        """Toggle realistic rendering mode."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Realistic mode will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_toggle_grid(self) -> None:
        """Toggle grid display."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Grid toggle will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_toggle_axes(self) -> None:
        """Toggle coordinate axes display."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Axes toggle will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_section_view(self) -> None:
        """Show section/slice through model."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Section view will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_split_horizontal(self) -> None:
        """Split viewport horizontally."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "View splitting will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_split_vertical(self) -> None:
        """Split viewport vertically."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "View splitting will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_split_four_way(self) -> None:
        """Split viewport into four views."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "View splitting will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _on_save_bookmark(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Bookmark", "Bookmark name:")
        if not ok or not name:
            return
        self._view_bookmarks[name] = self.api.viewport.state.camera
        self.statusBar().showMessage(f"View saved as bookmark {name!r}.")

    def _on_load_bookmark(self) -> None:
        if not self._view_bookmarks:
            QMessageBox.information(self, "No bookmarks", "No saved views yet — use Save Bookmark first.")
            return
        name, ok = QInputDialog.getItem(
            self, "Load Bookmark", "View:", list(self._view_bookmarks.keys()), 0, False
        )
        if not ok or not name:
            return
        self.api.viewport.set_camera(self._view_bookmarks[name])


    def _on_placeholder_theme_light(self) -> None:
        """Switch to light theme."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Theme switching will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_theme_dark(self) -> None:
        """Switch to dark theme."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Theme switching will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_units_metric(self) -> None:
        """Use metric units."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Unit system switching will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_units_imperial(self) -> None:
        """Use imperial units."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Unit system switching will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    # ── Draw Menu Placeholders ──────────────────────────────────────────────────

    def _on_placeholder_geometry_primitive(self, shape_name: str) -> None:
        QMessageBox.information(
            self,
            "Coming Soon",
            f"Draw {shape_name} has no geometry backend yet — this is a placeholder."
        )

    def _on_draw_sphere(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "Sphere"},
                "center": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                           "default": [0.0, 0.0, 1.0], "description": "Center [x, y, z] (m)"},
                "radius": {"type": "number", "default": 0.5},
                "surf_id": {"type": "string", "default": "INERT"},
            },
            "required": ["center", "radius"],
        }
        dialog = SchemaFormDialog("Draw Sphere", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self.api.geom.sphere(
                values["center"], values["radius"],
                surf_id=values.get("surf_id") or "INERT",
                name=values.get("name") or "Sphere",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not create sphere", str(exc))
        else:
            self.explorer.refresh()

    def _on_draw_cylinder(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "Cylinder"},
                "center_base": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                                 "default": [0.0, 0.0, 0.0], "description": "Base center [x, y, z] (m)"},
                "radius": {"type": "number", "default": 0.5},
                "height": {"type": "number", "default": 2.0},
                "surf_id": {"type": "string", "default": "INERT"},
            },
            "required": ["center_base", "radius", "height"],
        }
        dialog = SchemaFormDialog("Draw Cylinder", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self.api.geom.cylinder(
                values["center_base"], values["radius"], values["height"],
                surf_id=values.get("surf_id") or "INERT",
                name=values.get("name") or "Cylinder",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not create cylinder", str(exc))
        else:
            self.explorer.refresh()

    def _on_draw_cone(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "Cone"},
                "center_base": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                                 "default": [0.0, 0.0, 0.0], "description": "Base center [x, y, z] (m)"},
                "radius": {"type": "number", "default": 0.5},
                "height": {"type": "number", "default": 2.0},
                "surf_id": {"type": "string", "default": "INERT"},
            },
            "required": ["center_base", "radius", "height"],
        }
        dialog = SchemaFormDialog("Draw Cone", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self.api.geom.cone(
                values["center_base"], values["radius"], values["height"],
                surf_id=values.get("surf_id") or "INERT",
                name=values.get("name") or "Cone",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not create cone", str(exc))
        else:
            self.explorer.refresh()

    def _on_boolean_union(self) -> None:
        self._on_boolean_op("union")

    def _on_boolean_difference(self) -> None:
        self._on_boolean_op("difference")

    def _on_boolean_intersection(self) -> None:
        self._on_boolean_op("intersection")

    def _on_boolean_op(self, op: str) -> None:
        """Shared handler for Union/Difference/Intersection — needs exactly
        2 selected Geom entities. Source Geoms are left untouched; the
        result is added as a new, independent Geom (user's choice: keep
        both, don't replace)."""
        geoms = [e for a, e in self.explorer.selected_entities() if a == "geom"]
        if len(geoms) != 2:
            QMessageBox.information(
                self, f"Boolean {op.capitalize()}",
                "Select exactly 2 Geom entities first."
            )
            return
        geom_a, geom_b = geoms
        try:
            result = GeometryTools.boolean(
                op, geom_a, geom_b, name=f"{op.capitalize()}_{geom_a.name}_{geom_b.name}"
            )
        except ValueError as exc:
            QMessageBox.critical(self, f"Could not compute {op}", str(exc))
            return
        self.api.history.execute(AddEntityCommand(self.api.project, result))


    # ── Model Menu Placeholders ─────────────────────────────────────────────────

    def _on_placeholder_add_control(self) -> None:
        """Add control element."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Control elements will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_add_prop(self) -> None:
        """Add property/PROP specification."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Property elements will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_add_species(self) -> None:
        """Add chemical species."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Species configuration will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_geometry_repair(self) -> None:
        """Repair geometry issues."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Geometry repair will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    # ── Devices Menu Placeholders ───────────────────────────────────────────────

    def _on_add_device_by_quantity(self, quantity: str, dialog_title: str) -> None:
        """Shared path for every 'named sensor' menu item — each is really
        just the generic add_device tool with its QUANTITY default
        pre-filled; the dropdown still lets the user pick any DEVC quantity."""
        tool = get_tool("add_device")
        schema = copy.deepcopy(tool.input_schema)
        schema["properties"]["quantity"]["default"] = quantity
        dialog = SchemaFormDialog(dialog_title, tool.description, schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.dispatcher.call(tool.name, dialog.values())
        except Exception as exc:
            QMessageBox.critical(self, "Could not add device", str(exc))

    def _on_add_heat_flux(self) -> None:
        self._on_add_device_by_quantity("HEAT FLUX", "Add Heat Flux Sensor")

    def _on_add_smoke_detector(self) -> None:
        self._on_add_device_by_quantity("OPTICAL DENSITY", "Add Smoke Detector")

    def _on_add_beam_detector(self) -> None:
        self._on_add_device_by_quantity("EXTINCTION COEFFICIENT", "Add Beam Detector")

    def _on_add_gas_sensor(self) -> None:
        self._on_add_device_by_quantity("CARBON MONOXIDE", "Add Gas Sensor")

    def _on_add_anemometer(self) -> None:
        self._on_add_device_by_quantity("VELOCITY", "Add Anemometer")

    def _on_add_nozzle(self) -> None:
        # Mechanically identical to a sprinkler in FDS (a PROP-referenced
        # spray device at a point) — reuses add_sprinkler rather than
        # inventing a separate, redundant "add_nozzle" tool.
        self._on_add_entity("add_sprinkler")

    def _on_add_velocity_probe(self) -> None:
        self._on_add_device_by_quantity("VELOCITY", "Add Velocity Probe")

    def _on_add_pressure_probe(self) -> None:
        self._on_add_device_by_quantity("PRESSURE", "Add Pressure Probe")


    def _on_placeholder_device_labels(self) -> None:
        """Toggle device labels in viewport."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Device labels will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    # ── Output Menu Placeholders ────────────────────────────────────────────────

    def _on_output_frequency(self) -> None:
        dump = self.api.project.dump
        schema = {
            "type": "object",
            "properties": {
                "dt_slcf": {"type": "number", "default": dump.dt_slcf, "description": "Slice file output interval, s."},
                "dt_bndf": {"type": "number", "default": dump.dt_bndf, "description": "Boundary file output interval, s."},
                "dt_isof": {"type": "number", "default": dump.dt_isof, "description": "Isosurface output interval, s."},
                "dt_pl3d": {"type": "number", "default": dump.dt_pl3d, "description": "Plot3D output interval, s."},
                "dt_devc": {"type": "number", "default": dump.dt_devc, "description": "Device output interval, s."},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Output Frequency", "Maps to the &DUMP namelist.", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            for field_name, value in dialog.values().items():
                self.api.set_property(dump, field_name, value)
        except Exception as exc:
            QMessageBox.critical(self, "Could not update output frequency", str(exc))


    # ── HVAC Menu ────────────────────────────────────────────────────────────

    def _on_hvac_network_editor(self) -> None:
        """Open the HVAC Network Editor (2D schematic node/duct diagram),
        reusing the same instance on repeat opens rather than stacking
        windows."""
        if self._hvac_editor is None:
            from pyfds.gui.hvac_network_editor import HvacNetworkEditorDialog
            self._hvac_editor = HvacNetworkEditorDialog(self.api, self)
        self._hvac_editor.show()
        self._hvac_editor.raise_()
        self._hvac_editor.activateWindow()


    def _on_hvac_solver_setup(self) -> None:
        """Configure HVAC solver parameters and run the network solver."""
        schema = {
            "type": "object",
            "properties": {
                "rho": {"type": "number", "default": 1.2,
                        "description": "Air density (kg/m³)."},
                "max_iter": {"type": "integer", "default": 200,
                             "description": "Maximum Hardy-Cross iterations."},
                "tol": {"type": "number", "default": 1e-5,
                        "description": "Convergence tolerance (m³/s)."},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("HVAC Solver Setup", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            result = self.api.hvac.solve_network(
                rho=values.get("rho", 1.2),
                max_iter=values.get("max_iter", 200),
                tol=values.get("tol", 1e-5),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not solve HVAC network", str(exc))
            return
        TextReportDialog("HVAC Solver Result", result.summary(), self).exec()


    def _on_hvac_diagnostics(self) -> None:
        """Run the HVAC network solver with default parameters."""
        try:
            result = self.api.hvac.solve_network()
        except Exception as exc:
            QMessageBox.critical(self, "Could not run HVAC diagnostics", str(exc))
            return
        TextReportDialog("HVAC Diagnostics", result.summary(), self).exec()


    # ── Scenarios Menu Placeholders ─────────────────────────────────────────────

    def _on_placeholder_import_scenarios_dialog(self) -> None:
        """Import scenario definitions from file."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Scenario import will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    # ── Run Menu Placeholders ───────────────────────────────────────────────────

    def _on_placeholder_run_parallel_mpi(self) -> None:
        """Configure and run simulation with MPI."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "MPI configuration will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_mpi_preview(self) -> None:
        """Preview MPI setup."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "MPI preview will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_pause_simulation(self) -> None:
        """Pause running simulation."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Simulation pause will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_stop_simulation(self) -> None:
        """Stop running simulation."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Simulation stop will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_gpu_settings(self) -> None:
        """Configure GPU acceleration settings."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "GPU settings will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_monitor_simulation(self) -> None:
        """Monitor running simulation."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Simulation monitoring will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    # ── Results Menu Placeholders ───────────────────────────────────────────────

    def _on_slice_browser(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return
        try:
            idx = self.api.results.build_index(output_dir)
            entries = idx.find_slices()
        except Exception as exc:
            QMessageBox.critical(self, "Could not load slices", str(exc))
            return
        if not entries:
            QMessageBox.information(self, "No slice data", "No slice files found in this directory.")
            return
        lines = [
            f"{e.quantity} ({e.units})  mesh={e.mesh_id}  {Path(e.filepath).name}"
            for e in entries
        ]
        TextReportDialog("Slice Browser", "\n".join(lines), self).exec()


    def _on_boundary_browser(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return
        try:
            idx = self.api.results.build_index(output_dir)
            entries = idx.find_boundaries()
        except Exception as exc:
            QMessageBox.critical(self, "Could not load boundary files", str(exc))
            return
        if not entries:
            QMessageBox.information(self, "No boundary data", "No boundary files found in this directory.")
            return
        lines = [
            f"{e.quantity} ({e.units})  mesh={e.mesh_id}  {Path(e.filepath).name}"
            for e in entries
        ]
        TextReportDialog("Boundary Browser", "\n".join(lines), self).exec()


    def _on_plot_manager(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return
        try:
            FigureDialog = _import_figure_dialog()
        except ImportError:
            QMessageBox.critical(
                self, "Plotting unavailable",
                "Install with:\n  pip install pyfds[plot]",
            )
            return
        try:
            idx = self.api.results.build_index(output_dir)
            device_names = idx.all_device_names()
            if not device_names:
                QMessageBox.information(self, "No device data", "No device time-series data found.")
                return
        except Exception as exc:
            QMessageBox.critical(self, "Could not load results", str(exc))
            return
        name, ok = QInputDialog.getItem(self, "Plot Manager", "Device:", device_names, 0, False)
        if not ok:
            return
        try:
            from pyfds.results.reader import DeviceReader
            from pyfds.results.plotters import plot_device_timeseries
            filepath = idx.find_device_file(name)
            results = DeviceReader.read(filepath)
            fig = plot_device_timeseries(results)
        except Exception as exc:
            QMessageBox.critical(self, "Could not plot device", str(exc))
            return
        FigureDialog(f"Plot: {name}", fig, self).exec()


    def _on_isosurface_settings(self) -> None:
        self._on_add_entity("add_isosurface")


    def _on_export_csv(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return
        try:
            idx = self.api.results.build_index(output_dir)
            device_names = idx.all_device_names()
        except Exception as exc:
            QMessageBox.critical(self, "Could not load results", str(exc))
            return
        if not device_names:
            QMessageBox.information(self, "No device data", "No device time-series data found.")
            return
        name, ok = QInputDialog.getItem(self, "Export CSV", "Device:", device_names, 0, False)
        if not ok:
            return
        src = idx.find_device_file(name)
        if not src:
            QMessageBox.warning(self, "Not found", f"No CSV file found for device {name!r}.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Export CSV As", f"{name}.csv", "CSV Files (*.csv)")
        if not dest:
            return
        try:
            shutil.copy(src, dest)
        except Exception as exc:
            QMessageBox.critical(self, "Could not export CSV", str(exc))
        else:
            QMessageBox.information(self, "Exported", f"Device data exported to:\n{dest}")


    def _on_generate_report(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return
        dest, selected_filter = QFileDialog.getSaveFileName(
            self, "Generate Report As", "report.html",
            "HTML Report (*.html);;Text Report (*.txt)",
        )
        if not dest:
            return
        fmt = "html" if selected_filter.startswith("HTML") else "text"
        try:
            self.api.results.build_index(output_dir)
            report = self.api.results.generate_report()
            report.save(dest, fmt=fmt)
        except Exception as exc:
            QMessageBox.critical(self, "Could not generate report", str(exc))
        else:
            QMessageBox.information(self, "Report Generated", f"Report saved to:\n{dest}")


    def _on_batch_export(self) -> None:
        output_root = QFileDialog.getExistingDirectory(self, "Batch Study Output Root")
        if not output_root:
            return
        study_name, ok = QInputDialog.getText(
            self, "Batch Export", "Study name (blank = all variants under root):"
        )
        if not ok:
            return
        dest, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Batch Report As", "batch_report.html",
            "HTML Report (*.html);;JSON Report (*.json)",
        )
        if not dest:
            return
        try:
            report = self.api.results.analyze_batch(output_root, study_name=study_name or None)
            if selected_filter.startswith("HTML"):
                report.to_html(dest, title="Batch Study Report")
            else:
                report.to_json(dest)
        except Exception as exc:
            QMessageBox.critical(self, "Could not export batch report", str(exc))
        else:
            QMessageBox.information(self, "Exported", f"Batch report saved to:\n{dest}")


    def _on_export_animation(self) -> None:
        """Render a movie of a result quantity via headless Smokeview."""
        smv_path, _ = QFileDialog.getOpenFileName(
            self, "Open Smokeview File", "", "Smokeview Files (*.smv)"
        )
        if not smv_path:
            return
        schema = {
            "type": "object",
            "properties": {
                "quantity": {"type": "string", "default": "TEMPERATURE"},
                "fps": {"type": "integer", "default": 10},
                "start_time": {"type": "number", "default": 0.0,
                               "description": "Seconds. 0 together with end time 0 = full range."},
                "end_time": {"type": "number", "default": 0.0},
            },
            "required": ["quantity"],
        }
        dialog = SchemaFormDialog("Export Animation", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Export Animation As", "animation.mp4",
            "MP4 Video (*.mp4);;AVI Video (*.avi)",
        )
        if not out_path:
            return
        start = values.get("start_time") or None
        end = values.get("end_time") or None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            rc = self.api.smokeview.render_movie(
                smv_path, out_path, values.get("quantity") or "TEMPERATURE",
                fps=int(values.get("fps") or 10), start_time=start, end_time=end,
            )
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                self, "Could not export animation",
                f"{exc}\n\nCheck the 'smv_binary' setting in Preferences.",
            )
            return
        QApplication.restoreOverrideCursor()
        if rc == 0:
            QMessageBox.information(self, "Exported", f"Animation saved to:\n{out_path}")
        else:
            QMessageBox.warning(
                self, "Export Animation", f"Smokeview exited with return code {rc}."
            )


    # ── Tools Menu Placeholders ────────────────────────────────────────────────

    def _on_tools_validation(self) -> None:
        # Runs plugin-registered rules too, unlike Model > Validate Project
        # (api.validation.validate()) — a superset check, not a duplicate.
        report = self.api.validation.validate_with_plugins()
        TextReportDialog("Validation (with plugin rules)", str(report), self).exec()


    def _on_find_errors(self) -> None:
        report = self.api.validation.validate()
        errors = report.errors
        if not errors:
            QMessageBox.information(self, "No errors", "Validation found no ERROR-severity issues.")
            return
        text = "\n".join(str(e) for e in errors)
        TextReportDialog("Find Errors", text, self).exec()


    def _on_mesh_diagnostics(self) -> None:
        results = self.api.meshes.check_poisson()
        if not results:
            QMessageBox.information(self, "No meshes", "No mesh regions in this project.")
            return
        lines = [
            f"{name}: {'OK — Poisson-compliant' if ok else 'WARNING — not Poisson-compliant'}"
            for name, ok in results.items()
        ]
        TextReportDialog("Mesh Diagnostics", "\n".join(lines), self).exec()


    def _on_placeholder_tools_geometry_repair(self) -> None:
        """Repair geometry issues."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Geometry repair will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_mesh_checker(self) -> None:
        report = self.api.validation.validate()
        mesh_results = [r for r in report.results if "Mesh" in r.rule]
        if not mesh_results:
            QMessageBox.information(self, "No issues", "No mesh-related issues found (overlap, Poisson compliance).")
            return
        text = "\n".join(str(r) for r in mesh_results)
        TextReportDialog("Mesh Checker", text, self).exec()


    def _on_plugin_manager(self) -> None:
        plugins = self.api.plugins.all_plugins()
        lines = [str(p) for p in plugins] if plugins else ["No plugins currently loaded."]
        TextReportDialog("Plugin Manager", "\n".join(lines), self).exec()
        if QMessageBox.question(
            self, "Load More Plugins", "Load additional plugins from a directory?"
        ) != QMessageBox.Yes:
            return
        load_dir = QFileDialog.getExistingDirectory(self, "Plugin Directory")
        if not load_dir:
            return
        try:
            count = self.api.plugins.load_directory(load_dir)
        except Exception as exc:
            QMessageBox.critical(self, "Could not load plugins", str(exc))
        else:
            QMessageBox.information(self, "Plugins Loaded", f"Loaded {count} plugin(s) from:\n{load_dir}")


    # Category -> {unit: factor to the category's base (SI) unit}. Temperature
    # is handled separately since C/F/K aren't related by a simple factor.
    _UNIT_CATEGORIES = {
        "Length": {"m": 1.0, "ft": 0.3048, "in": 0.0254, "mm": 0.001, "cm": 0.01},
        "Mass": {"kg": 1.0, "lb": 0.45359237, "g": 0.001},
        "HRR / Power": {"kW": 1.0, "MW": 1000.0, "BTU/s": 1.055056, "BTU/hr": 0.00029307107},
        "Velocity": {"m/s": 1.0, "ft/s": 0.3048, "ft/min": 0.00508, "mph": 0.44704},
        "Pressure": {"Pa": 1.0, "kPa": 1000.0, "bar": 1.0e5, "atm": 101325.0, "psi": 6894.757},
    }

    @staticmethod
    def _convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
        celsius = {"C": value, "F": (value - 32.0) * 5.0 / 9.0, "K": value - 273.15}[from_unit]
        return {"C": celsius, "F": celsius * 9.0 / 5.0 + 32.0, "K": celsius + 273.15}[to_unit]

    def _on_units_conversion(self) -> None:
        categories = list(self._UNIT_CATEGORIES.keys()) + ["Temperature"]
        category, ok = QInputDialog.getItem(self, "Units Conversion", "Category:", categories, 0, False)
        if not ok:
            return
        units = ["C", "F", "K"] if category == "Temperature" else list(self._UNIT_CATEGORIES[category].keys())
        from_unit, ok = QInputDialog.getItem(self, "Units Conversion", "From:", units, 0, False)
        if not ok:
            return
        to_unit, ok = QInputDialog.getItem(self, "Units Conversion", "To:", units, min(1, len(units) - 1), False)
        if not ok:
            return
        value, ok = QInputDialog.getDouble(self, "Units Conversion", f"Value ({from_unit}):", 0.0, -1.0e12, 1.0e12, 4)
        if not ok:
            return
        if category == "Temperature":
            result = self._convert_temperature(value, from_unit, to_unit)
        else:
            factors = self._UNIT_CATEGORIES[category]
            result = value * factors[from_unit] / factors[to_unit]
        QMessageBox.information(self, "Units Conversion", f"{value:g} {from_unit} = {result:.6g} {to_unit}")

    _CALC_OPS = {
        ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.USub: operator.neg, ast.UAdd: operator.pos,
    }

    @classmethod
    def _safe_eval(cls, expr: str) -> float:
        """Numbers and + - * / ** % () only — no names, no calls, so this
        can never execute arbitrary code (unlike a raw eval())."""
        def _walk(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.BinOp) and type(node.op) in cls._CALC_OPS:
                return cls._CALC_OPS[type(node.op)](_walk(node.left), _walk(node.right))
            if isinstance(node, ast.UnaryOp) and type(node.op) in cls._CALC_OPS:
                return cls._CALC_OPS[type(node.op)](_walk(node.operand))
            raise ValueError("only numbers and + - * / ** % ( ) are allowed")
        return _walk(ast.parse(expr, mode="eval").body)

    def _on_calculator(self) -> None:
        expr, ok = QInputDialog.getText(self, "Calculator", "Expression (+ - * / ** % parentheses):")
        if not ok or not expr:
            return
        try:
            result = self._safe_eval(expr)
        except Exception as exc:
            QMessageBox.warning(self, "Calculator", f"Could not evaluate {expr!r}: {exc}")
            return
        QMessageBox.information(self, "Calculator", f"{expr} = {result:g}")


    def _on_fds_preview(self) -> None:
        from pyfds.io.fds_writer import FdsWriter
        try:
            text = FdsWriter().to_string(self.api.project)
        except Exception as exc:
            QMessageBox.critical(self, "Could not generate preview", str(exc))
            return
        TextReportDialog("FDS Preview (EXPERIMENTAL)", text, self).exec()


    def _on_placeholder_script_console(self) -> None:
        """Open Python script console."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Script console will be available in Phase 3.\n\n"
            "This is a placeholder."
        )


    # ── Window Menu ──────────────────────────────────────────────────────────

    def _window_layout_names(self) -> list:
        settings = QSettings("PyFDS", "PyFDS")
        names = settings.value("window_layout_names", [])
        if isinstance(names, str):
            names = [names]
        return list(names or [])

    def _on_workspace(self) -> None:
        """Save the current window layout (dock/toolbar arrangement) under a name."""
        name, ok = QInputDialog.getText(self, "Save Workspace", "Layout name:")
        if not ok or not name:
            return
        settings = QSettings("PyFDS", "PyFDS")
        names = self._window_layout_names()
        if name not in names:
            names.append(name)
            settings.setValue("window_layout_names", names)
        settings.setValue(f"window_layout/{name}", self.saveState())
        self.statusBar().showMessage(f"Window layout saved as {name!r}.")

    def _on_layouts(self) -> None:
        """Apply a previously saved named window layout."""
        names = self._window_layout_names()
        if not names:
            QMessageBox.information(
                self, "No layouts", "No saved layouts yet — use Workspace to save one first."
            )
            return
        name, ok = QInputDialog.getItem(self, "Load Layout", "Layout:", names, 0, False)
        if not ok or not name:
            return
        state = QSettings("PyFDS", "PyFDS").value(f"window_layout/{name}")
        if state is None:
            QMessageBox.warning(self, "Layout not found", f"No saved layout named {name!r}.")
            return
        self.restoreState(state)
        self.statusBar().showMessage(f"Window layout {name!r} restored.")

    def _on_reset_window_layout(self) -> None:
        """Restore docks/toolbars to their state at application startup."""
        self.restoreState(self._default_window_state)
        self.statusBar().showMessage("Window layout reset to default.")


    # ── Help Menu Placeholders ─────────────────────────────────────────────────

    def _on_placeholder_examples(self) -> None:
        """Browse example projects."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Examples browser will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_placeholder_tutorials(self) -> None:
        """Access tutorials."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Tutorials will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    def _on_keyboard_shortcuts(self) -> None:
        actions = (
            self._new_action, self._open_action, self._save_as_action,
            self._undo_action, self._redo_action, self._cut_action,
            self._copy_action, self._paste_action, self._delete_action,
        )
        lines = [
            f"{action.text().replace('&', ''):<28} {action.shortcut().toString() or '(none)'}"
            for action in actions
        ]
        TextReportDialog("Keyboard Shortcuts", "\n".join(lines), self).exec()


    def _on_placeholder_check_updates(self) -> None:
        """Check for application updates."""
        QMessageBox.information(
            self,
            "Coming Soon",
            "Update checker will be available in Phase 2.\n\n"
            "This is a placeholder."
        )


    # End of placeholder handlers


    def _on_new(self) -> None:
        self.api.new()
        self._current_project_path = None

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "FDS/PyFDS Files (*.fds *.pyfds)")
        if not path:
            return
        try:
            self.api.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
        else:
            self._current_project_path = path
            self._add_recent_path(path)

    def _on_save_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "FDS Files (*.fds);;PyFDS Files (*.pyfds)")
        if not path:
            return
        try:
            self.api.save(path)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
        else:
            self._current_project_path = path
            self._add_recent_path(path)

    def _on_add_entity(self, tool_name: str) -> None:
        tool = get_tool(tool_name)
        dialog = SchemaFormDialog(tool.name, tool.description, tool.input_schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.dispatcher.call(tool.name, dialog.values())
        except Exception as exc:
            QMessageBox.critical(self, "Could not add entity", str(exc))

    def _on_simulation_parameters(self) -> None:
        tool = get_tool("configure_simulation_params")
        # Same schema the agent tool uses, but with defaults patched to the
        # project's *current* values — an Add-Entity dialog starts blank,
        # this one should show what's already set.
        schema = copy.deepcopy(tool.input_schema)
        params = self.api.project.params
        schema["properties"]["t_end"]["default"] = params.t_end
        schema["properties"]["t_begin"]["default"] = params.t_begin
        if params.dt is not None:
            schema["properties"]["dt"]["default"] = params.dt
        schema["properties"]["restrict_time_step"]["default"] = params.restrict_time_step

        dialog = SchemaFormDialog(tool.name, tool.description, schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.dispatcher.call(tool.name, dialog.values())
        except Exception as exc:
            QMessageBox.critical(self, "Could not update simulation parameters", str(exc))

    def _on_delete_selected(self) -> None:
        selected = self.explorer.selected()
        if selected is None:
            return
        attr, entity = selected
        name = getattr(entity, "name", repr(entity))
        if QMessageBox.question(self, "Delete", f"Remove {name!r}?") != QMessageBox.Yes:
            return
        try:
            getattr(self.api, attr).remove(entity)
        except Exception as exc:
            QMessageBox.critical(self, "Could not remove entity", str(exc))

    def _on_edit_properties(self) -> None:
        selected = self.explorer.selected()
        if selected is None:
            return
        _attr, entity = selected
        schema = build_edit_schema(entity)
        dialog = SchemaFormDialog(f"Edit {entity.name}", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            apply_edits(self.api, entity, dialog.values())
        except Exception as exc:
            QMessageBox.critical(self, "Could not update properties", str(exc))
        # apply_edits() goes through api.set_property() -> ModifyPropertyCommand
        # -> the CommandPipeline, which fires COMMAND_EXECUTED — the explorer's
        # own EventBus subscription refreshes it automatically, same as every
        # other mutation in this app.

    def _on_find(self) -> None:
        text, ok = QInputDialog.getText(self, "Find", "Search for (matches entity name):")
        if not ok or not text:
            return
        match = self.explorer.find_entity_by_name(text)
        if match is None:
            QMessageBox.information(self, "Find", f"No entity found matching {text!r}.")
            return
        self.explorer.setCurrentItem(match)

    def _build_entity_context_menu(self, attr: str, entity: Any) -> QMenu:
        """Pure construction, no ``.exec()`` — kept separate so tests can
        inspect the menu's actions without ever risking a real modal popup.

        Scenario/Floor/Group rows get their own branch: all three are plain
        dataclasses stored internally in dicts keyed by name (not FdsEntity
        subclasses living in plain lists), so the generic Rename/Disable
        path — which assumes a bare ``setattr`` is always safe — would
        desync the dict key from the renamed object. Delete is still safe
        (whole-entry removal, not a rename) and reuses the same
        ``_on_delete_selected`` as every other entity type via the
        ``remove(entity)`` aliases on ``ScenarioManager``/``FloorManager``/
        ``GroupManager``."""
        menu = QMenu(self)
        if attr == "scenarios":
            menu.addAction("&Apply", lambda: self._on_apply_scenario(entity.name))
            menu.addAction("&Clone...", lambda: self._on_clone_scenario(entity.name))
            menu.addAction("&Set Override...", lambda: self._on_set_scenario_override(entity))
            menu.addSeparator()
            menu.addAction("&Delete", self._on_delete_selected)
            return menu
        if attr == "floors":
            menu.addAction("&Properties...", self._on_edit_properties)
            menu.addSeparator()
            menu.addAction("&Delete", self._on_delete_selected)
            return menu
        if attr == "groups":
            menu.addAction("&Select Members", lambda: self._on_select_group_members(entity.name))
            menu.addSeparator()
            menu.addAction("&Delete", self._on_delete_selected)
            return menu
        menu.addAction("&Properties...", self._on_edit_properties)
        menu.addAction("Re&name...", lambda: self._on_rename_entity(entity))
        toggle_label = "&Disable Object" if entity.enabled else "&Enable Object"
        menu.addAction(toggle_label, lambda: self._on_toggle_enabled(entity))
        menu.addSeparator()
        menu.addAction("&Delete", self._on_delete_selected)
        return menu

    def _on_explorer_context_menu(self) -> None:
        selected = self.explorer.selected()
        if selected is None:
            return
        attr, entity = selected
        self._build_entity_context_menu(attr, entity).exec(QCursor.pos())

    def _on_rename_entity(self, entity: Any) -> None:
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=entity.name)
        if not ok or not new_name or new_name == entity.name:
            return
        try:
            self.api.set_property(entity, "name", new_name)
        except Exception as exc:
            QMessageBox.critical(self, "Could not rename", str(exc))

    def _on_toggle_enabled(self, entity: Any) -> None:
        try:
            self.api.set_property(entity, "enabled", not entity.enabled)
        except Exception as exc:
            QMessageBox.critical(self, "Could not change enabled state", str(exc))

    def _on_new_from_template(self) -> None:
        presets = self.api.templates.list_presets()
        if not presets:
            QMessageBox.information(self, "No templates", "No scenario templates are available.")
            return
        preset_name, ok = QInputDialog.getItem(
            self, "New From Template", "Template:", presets, 0, False
        )
        if not ok or not preset_name:
            return
        try:
            self.api.templates.apply(preset_name)
        except Exception as exc:
            QMessageBox.critical(self, "Could not apply template", str(exc))

    # ── Scenarios ────────────────────────────────────────────────────────────
    # Scenario create/clone/delete/apply/reset all mutate ScenarioManager's
    # own in-memory store directly (not via the CommandPipeline — see
    # ScenarioManager's docstring), so none of them fire COMMAND_EXECUTED;
    # every handler below calls self.explorer.refresh() itself, same as
    # _on_auto_fix() does for its own direct-mutation path.

    def _on_new_scenario(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["name"],
        }
        dialog = SchemaFormDialog("New Scenario", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self.api.scenarios.create(values["name"], values.get("description", ""))
        except Exception as exc:
            QMessageBox.critical(self, "Could not create scenario", str(exc))
        else:
            self.explorer.refresh()

    def _on_clone_scenario(self, base_name: Optional[str] = None) -> None:
        names = [s.name for s in self.api.scenarios.all()]
        if not names:
            QMessageBox.information(self, "No scenarios", "Create a scenario first.")
            return
        schema = {
            "type": "object",
            "properties": {
                "base_name": {"type": "string", "enum": names, "default": base_name or names[0]},
                "new_name": {"type": "string"},
            },
            "required": ["base_name", "new_name"],
        }
        dialog = SchemaFormDialog("Clone Scenario", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self.api.scenarios.clone(values["base_name"], values["new_name"])
        except Exception as exc:
            QMessageBox.critical(self, "Could not clone scenario", str(exc))
        else:
            self.explorer.refresh()

    def _on_apply_scenario_dialog(self) -> None:
        names = [s.name for s in self.api.scenarios.all()]
        if not names:
            QMessageBox.information(self, "No scenarios", "Create a scenario first.")
            return
        name, ok = QInputDialog.getItem(self, "Apply Scenario", "Scenario:", names, 0, False)
        if not ok or not name:
            return
        self._on_apply_scenario(name)

    def _on_apply_scenario(self, name: str) -> None:
        try:
            self.api.scenarios.apply(name)
        except Exception as exc:
            QMessageBox.critical(self, "Could not apply scenario", str(exc))
        else:
            self.explorer.refresh()
            self._refresh_status()

    def _on_reset_scenario(self) -> None:
        if self.api.scenarios.active is None:
            QMessageBox.information(self, "No active scenario", "No scenario is currently applied.")
            return
        self.api.scenarios.reset()
        self.explorer.refresh()
        self._refresh_status()

    def _on_set_scenario_override(self, entity: Any) -> None:
        names = [s.name for s in self.api.scenarios.all()]
        if not names:
            QMessageBox.information(self, "No scenarios", "Create a scenario first.")
            return
        edit_schema = build_edit_schema(entity)
        fields = list(edit_schema["properties"].keys())
        if not fields:
            QMessageBox.information(self, "No editable fields", f"{entity.name} has no simple fields to override.")
            return
        schema = {
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "enum": names},
                "field_name": {"type": "string", "enum": fields},
                "value": {"type": "string", "description": "New value for this field in the scenario."},
            },
            "required": ["scenario", "field_name", "value"],
        }
        dialog = SchemaFormDialog(f"Set Scenario Override — {entity.name}", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        field_name = values["field_name"]
        prop = edit_schema["properties"].get(field_name, {})
        try:
            value = self._coerce_scenario_value(values["value"], prop)
            self.api.scenarios.set_override(values["scenario"], entity, field_name, value)
        except Exception as exc:
            QMessageBox.critical(self, "Could not set override", str(exc))

    @staticmethod
    def _coerce_scenario_value(raw: str, prop: dict) -> Any:
        """Type-coerce a scenario-override value against *its target
        field's* schema — can't reuse SchemaFormDialog's own coercion
        because that's keyed to the "value" field's own (fixed, "string")
        schema entry, not the dynamically chosen target field."""
        ptype = prop.get("type")
        if ptype == "number":
            return float(raw)
        if ptype == "integer":
            return int(raw)
        if ptype == "boolean":
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if ptype == "array":
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            item_type = prop.get("items", {}).get("type")
            if item_type == "number":
                return [float(p) for p in parts]
            if item_type == "integer":
                return [int(p) for p in parts]
            return parts
        return raw

    def _on_export_scenarios(self) -> None:
        if not self.api.scenarios.all():
            QMessageBox.information(self, "No scenarios", "Create a scenario first.")
            return
        dirpath = QFileDialog.getExistingDirectory(self, "Export Scenarios Folder")
        if not dirpath:
            return
        try:
            written = self.api.scenarios.export_all(dirpath)
        except Exception as exc:
            QMessageBox.critical(self, "Could not export scenarios", str(exc))
        else:
            self.explorer.refresh()
            lines = "\n".join(f"{name}: {path}" for name, path in written.items())
            QMessageBox.information(self, "Exported", f"{len(written)} scenario(s) exported:\n{lines}")

    # ── Floors ───────────────────────────────────────────────────────────────
    # Same direct-mutation caveat as Scenarios above — every handler below
    # refreshes the explorer itself.

    def _on_define_floor(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "z_min": {"type": "number"},
                "z_max": {"type": "number"},
                "description": {"type": "string"},
            },
            "required": ["name", "z_min", "z_max"],
        }
        dialog = SchemaFormDialog("Define Floor", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self.api.floors.define_floor(
                values["name"], values["z_min"], values["z_max"], values.get("description", "")
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not define floor", str(exc))
        else:
            self.explorer.refresh()

    def _on_auto_assign_floors(self) -> None:
        if not self.api.floors.all_floors():
            QMessageBox.information(self, "No floors", "Define a floor first.")
            return
        count = self.api.floors.auto_assign_all()
        self.explorer.refresh()
        QMessageBox.information(self, "Auto-Assign", f"{count} entities assigned to a floor by elevation.")

    def _on_assign_to_floor(self) -> None:
        floors = [f.name for f in self.api.floors.all_floors()]
        if not floors:
            QMessageBox.information(self, "No floors", "Define a floor first.")
            return
        selected = self.explorer.selected()
        if selected is None or selected[0] in ("scenarios", "floors"):
            QMessageBox.information(self, "No entity selected", "Select an entity in the Project Explorer first.")
            return
        _attr, entity = selected
        floor_name, ok = QInputDialog.getItem(self, "Assign to Floor", f"Floor for {entity.name}:", floors, 0, False)
        if not ok or not floor_name:
            return
        try:
            self.api.floors.assign(entity, floor_name)
        except Exception as exc:
            QMessageBox.critical(self, "Could not assign floor", str(exc))
        else:
            self.explorer.refresh()

    def _on_export_floors(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Floors", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            self.api.floors.export_floors(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not export floors", str(exc))
        else:
            QMessageBox.information(self, "Exported", f"Floors exported to:\n{path}")

    def _on_import_floors(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Floors", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            count = self.api.floors.import_floors(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not import floors", str(exc))
        else:
            self.explorer.refresh()
            QMessageBox.information(
                self, "Imported", f"Floors imported; {count} entity assignment(s) re-matched by name."
            )

    def _on_export_db(self, kind: str) -> None:
        path, _ = QFileDialog.getSaveFileName(self, f"Export {kind.title()} Database", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            getattr(self.api.engineering, f"export_{kind}")(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not export", str(exc))
        else:
            QMessageBox.information(self, "Exported", f"{kind.title()} database exported to:\n{path}")

    def _on_export_db_all(self) -> None:
        dirpath = QFileDialog.getExistingDirectory(self, "Export Database Folder")
        if not dirpath:
            return
        try:
            self.api.engineering.export_db(dirpath)
        except Exception as exc:
            QMessageBox.critical(self, "Could not export", str(exc))
        else:
            QMessageBox.information(self, "Exported", f"Database exported to:\n{dirpath}")

    def _on_validate(self) -> None:
        report = self.api.validation.validate()
        TextReportDialog("Validation Report", str(report), self).exec()

    def _on_auto_fix(self) -> None:
        self.api.validation.auto_fix()
        # auto_fix() mutates entities directly (not through CommandPipeline), so
        # it fires no COMMAND_EXECUTED event — refresh the tree/status explicitly.
        report = self.api.validation.validate()
        self.explorer.refresh()
        self._refresh_status()
        TextReportDialog("Auto-Fix Report (after fixing)", str(report), self).exec()

    def _on_convert_to_blocks(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "STL File to Voxelize", "", "STL Files (*.stl)")
        if not path:
            return
        try:
            obstructions = self.api.geom.voxelize(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not voxelize", str(exc))
            return
        QMessageBox.information(self, "Voxelize Complete", f"Created {len(obstructions)} obstruction(s).")

    # ── View menu (3D viewport) ─────────────────────────────────────────────

    def _on_reset_view(self) -> None:
        if hasattr(self.viewport_widget, "reset_view"):
            self.viewport_widget.reset_view()

    def _on_camera_preset(self, preset: CameraPreset) -> None:
        if hasattr(self.viewport_widget, "apply_preset"):
            self.viewport_widget.apply_preset(preset)

    def _on_toggle_wireframe(self, checked: bool) -> None:
        if hasattr(self.viewport_widget, "toggle_wireframe"):
            self.viewport_widget.toggle_wireframe()

    def _on_toggle_visibility(self, flag: VisibilityFlags, visible: bool) -> None:
        if hasattr(self.viewport_widget, "set_visibility"):
            self.viewport_widget.set_visibility(flag, visible)

    # ── Draw-box tool ────────────────────────────────────────────────────────

    def _on_set_draw_mode(self, tool_name: str) -> None:
        if hasattr(self.viewport_widget, "set_draw_mode"):
            self.viewport_widget.set_draw_mode(tool_name)
        self.statusBar().showMessage(
            f"Draw mode ({tool_name}): click two points in the 3D view to set the footprint..."
        )

    def _on_cancel_draw_mode(self) -> None:
        if hasattr(self.viewport_widget, "set_draw_mode"):
            self.viewport_widget.set_draw_mode(None)
        for action in self._draw_actions.values():
            action.setChecked(False)
        self._refresh_status()

    def _on_box_footprint_picked(
        self, tool_name: str, x_min: float, x_max: float, y_min: float, y_max: float
    ) -> None:
        # Viewport3D already auto-exited draw mode after the second click —
        # reflect that in the menu's checked state too.
        for action in self._draw_actions.values():
            action.setChecked(False)

        z_min, ok = QInputDialog.getDouble(self, "Height", "Z min (m):", 0.0, -1000.0, 1000.0, 2)
        if not ok:
            self._refresh_status()
            return
        z_max, ok = QInputDialog.getDouble(self, "Height", "Z max (m):", max(z_min + 3.0, 0.1), -1000.0, 1000.0, 2)
        if not ok:
            self._refresh_status()
            return

        try:
            self.dispatcher.call(tool_name, {"xb": [x_min, x_max, y_min, y_max, z_min, z_max]})
        except Exception as exc:
            QMessageBox.critical(self, "Could not create entity", str(exc))
        self._refresh_status()

    def _on_run_simulation(self) -> None:
        cfg = self.api.config
        if not shutil.which(getattr(cfg, "fds_binary", "") or ""):
            bundled = _default_fds_binary()
            if bundled:
                cfg.set("fds_binary", bundled)
            else:
                path, _ = QFileDialog.getOpenFileName(self, "Locate FDS Executable")
                if not path:
                    return
                cfg.set("fds_binary", path)

        if not shutil.which(getattr(cfg, "smv_binary", "") or ""):
            bundled_smv = _default_smv_binary()
            if bundled_smv:
                cfg.set("smv_binary", bundled_smv)

        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return

        num_processes, ok = QInputDialog.getInt(
            self, "Run Simulation", "Number of MPI processes:", 1, 1, 128
        )
        if not ok:
            return

        self._run_action.setEnabled(False)
        self.statusBar().showMessage("Running simulation...")
        self._run_future = self.api.execution.run_async(
            output_dir=output_dir,
            validate_first=True,
            open_smokeview=self._open_smokeview_action.isChecked(),
            num_processes=num_processes,
        )
        self._run_timer = QTimer(self)
        self._run_timer.timeout.connect(self._poll_run_future)
        self._run_timer.start(500)
        self._last_run_dir = output_dir
        getattr(self, "_show_run_monitor", lambda d: None)(output_dir)   # extras.py: live monitor window

    def _poll_run_future(self) -> None:
        if not self._run_future.done():
            return
        self._run_timer.stop()
        self._run_action.setEnabled(True)
        try:
            result = self._run_future.result()
        except Exception as exc:
            QMessageBox.critical(self, "Simulation failed", str(exc))
            self._refresh_status()
            return
        if result.success:
            QMessageBox.information(
                self, "Simulation complete",
                f"Wall time: {result.wall_time_seconds:.1f}s\nOutput: {result.output_dir}",
            )
        else:
            QMessageBox.warning(self, "Simulation did not complete", result.error or "Unknown error")
        self._refresh_status()

    def _on_resume_simulation(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Original FDS Input File", "", "FDS Files (*.fds)")
        if not path:
            return
        num_processes, ok = QInputDialog.getInt(
            self, "Resume Simulation", "Number of MPI processes:", 1, 1, 128
        )
        if not ok:
            return

        # Mirrors _on_run_simulation's own executor.submit()/QTimer polling —
        # ExecutionManager has no resume_from_checkpoint_async, so the same
        # off-main-thread pattern is applied here directly rather than
        # blocking the UI for the duration of a real FDS resume run.
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._resume_future = executor.submit(
            self.api.execution.resume_from_checkpoint, path, num_processes=num_processes
        )
        executor.shutdown(wait=False)
        self.statusBar().showMessage("Resuming simulation...")
        self._resume_timer = QTimer(self)
        self._resume_timer.timeout.connect(self._poll_resume_future)
        self._resume_timer.start(500)

    def _poll_resume_future(self) -> None:
        if not self._resume_future.done():
            return
        self._resume_timer.stop()
        try:
            result = self._resume_future.result()
        except Exception as exc:
            QMessageBox.critical(self, "Resume failed", str(exc))
            self._refresh_status()
            return
        if result.success:
            QMessageBox.information(
                self, "Resume complete",
                f"Wall time: {result.wall_time_seconds:.1f}s\nOutput: {result.output_dir}",
            )
        else:
            QMessageBox.warning(self, "Resume did not complete", result.error or "Unknown error")
        self._refresh_status()

    def _on_openmp_environment(self) -> None:
        current = self.api.project.misc.openmp_threads or 0
        threads, ok = QInputDialog.getInt(
            self, "OpenMP Environment", "Number of threads (0 = auto):", current, 0, 128
        )
        if not ok:
            return
        self.api.set_property(self.api.project.misc, "openmp_threads", threads or None)

    # ── Results menu ─────────────────────────────────────────────────────────

    def _on_open_smokeview_results(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Smokeview File", "", "Smokeview Files (*.smv)")
        if not path:
            return
        try:
            self.api.smokeview.open(path, blocking=False)
        except Exception as exc:
            QMessageBox.critical(self, "Could not open Smokeview", str(exc))

    def _on_open_results_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Results Folder")
        if not path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _on_view_time_history(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return
        try:
            FigureDialog = _import_figure_dialog()
        except ImportError:
            QMessageBox.critical(
                self, "Plotting unavailable",
                "Install with:\n  pip install pyfds[plot]",
            )
            return
        try:
            idx = self.api.results.build_index(output_dir)
            device_names = idx.all_device_names()
            if not device_names:
                QMessageBox.information(self, "No device data", "No device time-series data found.")
                return
            from pyfds.results.reader import DeviceReader
            from pyfds.results.plotters import plot_device_timeseries
            filepath = idx.find_device_file(device_names[0])
            results = DeviceReader.read(filepath)
            fig = plot_device_timeseries(results)
        except Exception as exc:
            QMessageBox.critical(self, "Could not load results", str(exc))
            return
        FigureDialog("Device Time History", fig, self).exec()

    def _on_archive_results(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "Archive Results As", "", "JSON Files (*.json)")
        if not save_path:
            return
        try:
            self.api.results.build_index(output_dir)
            self.api.results.archive(save_path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not archive results", str(exc))
        else:
            QMessageBox.information(self, "Archived", f"Result index archived to:\n{save_path}")

    def _on_restore_results(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restore Results", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            idx = self.api.results.restore(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not restore results", str(exc))
            return
        TextReportDialog("Restored Result Index", idx.summary(), self).exec()

    # ── Help menu ────────────────────────────────────────────────────────────

    def _on_open_doc(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.information(self, "Not found", f"Expected this file but it's missing:\n{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _on_about(self) -> None:
        QMessageBox.about(
            self, "About PyFDS",
            "PyFDS\n\n"
            "A Python-native FDS/Smokeview modeling backend and desktop GUI — "
            "a PyroSim-workflow-inspired open alternative built on NIST FDS.",
        )

    # ── Status bar ───────────────────────────────────────────────────────────

    def _on_status_event(self, event) -> None:
        self._refresh_status()

    def _refresh_status(self) -> None:
        self.statusBar().showMessage(self.api.info().replace("\n", "   |   "))

    # ── AI assistant dock (optional) ────────────────────────────────────────

    def _build_agent_dock(self) -> QDockWidget:
        dock = QDockWidget("AI Assistant", self)
        dock.setObjectName("AIAssistantDock")
        try:
            import anthropic  # noqa: F401
        except ImportError:
            dock.setWidget(QLabel(
                "AI assistant unavailable.\n\n"
                "Install with:\n  pip install pyfds[agent_anthropic]",
                dock,
            ))
            return dock

        from pyfds.agent import AgentSession
        from pyfds.gui.agent_panel import AgentChatPanel

        session = AgentSession(dispatcher=self.dispatcher)
        dock.setWidget(AgentChatPanel(session, self.api.history, dock))
        return dock

    # ── 3D viewport (optional, central widget) ──────────────────────────────

    def _build_viewport_widget(self) -> Any:
        # QtInteractor needs a real OpenGL-capable native window. Qt's
        # offscreen QPA platform (used by the headless test suite) cannot
        # provide one on this machine — attempting construction there is a
        # native access violation, not a catchable Python exception. Never
        # build the real widget under that platform.
        if QApplication.instance().platformName() == "offscreen":
            return QLabel(
                "3D viewport unavailable under the offscreen Qt platform "
                "(no OpenGL context here).\nRun the desktop app normally to "
                "see the 3D view.",
                self,
            )
        try:
            from pyfds.gui.viewport_3d import Viewport3D
        except ImportError:
            return QLabel(
                "3D viewport unavailable.\n\nInstall with:\n  pip install pyfds[viewport]",
                self,
            )
        return Viewport3D(self.api, self)

    # ── Teardown ─────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        self.explorer.shutdown()
        if hasattr(self.viewport_widget, "shutdown"):
            self.viewport_widget.shutdown()
        for sub_id in self._status_sub_ids:
            self.api.unsubscribe(sub_id)
        super().closeEvent(event)


def main() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
