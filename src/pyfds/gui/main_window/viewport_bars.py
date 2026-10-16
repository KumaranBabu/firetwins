"""Viewport toolbars (plan step F2): the View toolbar (render mode, standard views, navigation, snapshot), the vertical
Drawing toolbar (tools) and the Filter toolbar (object types, mesh display, snapping), plus the Tool Properties dock.

Everything goes through ``api.viewport`` or the Qt-free ``ToolManager``, so the bars work and are tested headless; only
navigation style and snapshot need the real 3D widget and say so when it is missing."""
from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QComboBox, QDockWidget, QFileDialog, QLabel, QMessageBox, QToolBar

from pyfds.core.events import EventType
from pyfds.core.viewport import CameraPreset, VisibilityFlags
from pyfds.core.viewport_types import MESH_DISPLAYS, RENDER_MODES
from pyfds.gui.panels.tool_properties import ToolPropertiesPanel

_RENDER_LABELS = {"wireframe": "Wireframe", "solid": "Solid", "outlines": "Outlines", "realistic": "Realistic"}
_VIEWS = [("Front", CameraPreset.FRONT), ("Top", CameraPreset.TOP), ("Left", CameraPreset.LEFT),
          ("Iso", CameraPreset.ISOMETRIC)]
_TOOLS = [("select", "Select"), ("obstruction", "Obstruction"), ("hole", "Hole"), ("vent", "Vent"), ("mesh", "Mesh"),
          ("wall", "Wall"), ("measure", "Measure"), ("paint", "Paint"), ("pick", "Pick surface")]
_FILTERS = [("Meshes", VisibilityFlags.MESHES), ("Obstructions", VisibilityFlags.OBSTRUCTIONS),
            ("Holes", VisibilityFlags.HOLES), ("Vents", VisibilityFlags.VENTS), ("Devices", VisibilityFlags.DEVICES),
            ("Slices", VisibilityFlags.SLICES), ("Init", VisibilityFlags.INIT_REGIONS),
            ("Geometry", VisibilityFlags.GEOMETRY)]
_GRIDS = [0.05, 0.1, 0.25, 0.5, 1.0]
_POLAR = [None, 15.0, 30.0, 45.0, 90.0]
_AGENT_TOOL = {"add_obstruction": "obstruction", "add_vent": "vent", "add_hole": "hole", "add_mesh": "mesh"}
_NAV = [("orbit", "Orbit"), ("turntable", "Turntable (Smokeview-like)"), ("roam", "Roam (WASD)")]


class ViewportBarsMixin:
    def _build_viewport_bars(self) -> None:
        self.tool_manager.subscribe(self._sync_tool_actions)
        self._build_view_toolbar()
        self._build_drawing_toolbar()
        self._build_filter_toolbar()
        self._build_tool_properties_dock()
        self._viewport_bar_subs = [self.api.subscribe(EventType.VIEWPORT_CHANGED, lambda _e: self._sync_viewport_bars())]
        if hasattr(self.viewport_widget, "status_message"):
            self.viewport_widget.status_message.connect(lambda m: self.statusBar().showMessage(m, 8000))
        self._sync_viewport_bars()

    # -- View toolbar -------------------------------------------------------------------------------------------
    def _build_view_toolbar(self) -> None:
        self.addToolBarBreak()                    # the existing toolbars fill the first row; these get their own
        bar = self.addToolBar("View")
        bar.setObjectName("ViewToolBar")
        self.view_bar = bar
        group = QActionGroup(self)
        group.setExclusive(True)
        self._render_actions: Dict[str, Any] = {}
        for mode in RENDER_MODES:
            a = bar.addAction(_RENDER_LABELS[mode])
            a.setCheckable(True)
            a.setToolTip(f"Draw solid objects as: {_RENDER_LABELS[mode].lower()}")
            a.triggered.connect(lambda _c=False, m=mode: self._on_render_mode(m))
            group.addAction(a)
            self._render_actions[mode] = a
        bar.addSeparator()
        for label, preset in _VIEWS:
            a = bar.addAction(label)
            a.setToolTip(f"{label} view")
            a.triggered.connect(lambda _c=False, p=preset: self._on_camera_preset(p))
        bar.addSeparator()
        bar.addWidget(QLabel(" Navigate "))
        self.nav_combo = QComboBox(bar)
        for key, label in _NAV:
            self.nav_combo.addItem(label, key)
        self.nav_combo.setToolTip("How the mouse moves the camera. Roam: W/A/S/D walk, Q/E down/up, arrows or drag to look")
        self.nav_combo.activated.connect(lambda i: self._on_navigation(self.nav_combo.itemData(i)))
        bar.addWidget(self.nav_combo)
        bar.addSeparator()
        self.snapshot_action = bar.addAction("Save image...")
        self.snapshot_action.setToolTip("Save the current 3D view as a picture")
        self.snapshot_action.triggered.connect(lambda _c=False: self._on_save_view_image())

    # -- Drawing toolbar ----------------------------------------------------------------------------------------
    def _build_drawing_toolbar(self) -> None:
        bar = QToolBar("Drawing", self)
        bar.setObjectName("DrawingToolBar")
        bar.setOrientation(Qt.Vertical)
        self.addToolBar(Qt.LeftToolBarArea, bar)
        self.drawing_bar = bar
        group = QActionGroup(self)
        group.setExclusive(True)
        self._tool_actions: Dict[str, Any] = {}
        for name, label in _TOOLS:
            a = bar.addAction(label)
            a.setCheckable(True)
            a.setToolTip(self.tool_manager.tools[name].hint or label)
            a.triggered.connect(lambda _c=False, n=name: self._on_tool_chosen(n))
            group.addAction(a)
            self._tool_actions[name] = a

    def _on_tool_chosen(self, name: str) -> None:
        if hasattr(self.viewport_widget, "activate_tool"):
            self.viewport_widget.activate_tool(name)
        else:
            self.tool_manager.activate(name)
        self.statusBar().showMessage(self.tool_manager.current.hint, 8000)

    def _sync_tool_actions(self) -> None:
        name = self.tool_manager.current.name
        for key, action in getattr(self, "_tool_actions", {}).items():
            action.setChecked(key == name)
        for key, action in getattr(self, "_draw_actions", {}).items():
            action.setChecked(name != "select" and _AGENT_TOOL.get(key, key) == name)

    # -- Filter toolbar -----------------------------------------------------------------------------------------
    def _build_filter_toolbar(self) -> None:
        self.addToolBarBreak()
        bar = self.addToolBar("Filter")
        bar.setObjectName("FilterToolBar")
        self.filter_bar = bar
        bar.addWidget(QLabel(" Show "))
        self._filter_actions: Dict[VisibilityFlags, Any] = {}
        for label, flag in _FILTERS:
            a = bar.addAction(label)
            a.setCheckable(True)
            a.toggled.connect(lambda checked, f=flag: self.api.viewport.set_visibility(f, checked))
            self._filter_actions[flag] = a
        bar.addSeparator()
        bar.addWidget(QLabel(" Mesh "))
        self.mesh_display_combo = QComboBox(bar)
        for m in MESH_DISPLAYS:
            self.mesh_display_combo.addItem(m.capitalize(), m)
        self.mesh_display_combo.setToolTip("Hidden, outline, cell lines on the faces, or a translucent shell")
        self.mesh_display_combo.activated.connect(lambda i: self.api.viewport.set_mesh_display(self.mesh_display_combo.itemData(i)))
        bar.addWidget(self.mesh_display_combo)
        bar.addSeparator()
        self.snap_action = bar.addAction("Snap")
        self.snap_action.setCheckable(True)
        self.snap_action.toggled.connect(lambda on: self.api.viewport.set_snap(enabled=on))
        bar.addWidget(QLabel(" Grid "))
        self.grid_combo = QComboBox(bar)
        for g in _GRIDS:
            self.grid_combo.addItem(f"{self.api.units.to_display(g, 'length'):g} {self.api.units.label('length')}", g)
        self.grid_combo.activated.connect(lambda i: self.api.viewport.set_snap(grid_size=self.grid_combo.itemData(i)))
        bar.addWidget(self.grid_combo)
        bar.addWidget(QLabel(" Polar "))
        self.polar_combo = QComboBox(bar)
        for deg in _POLAR:
            self.polar_combo.addItem("Off" if deg is None else f"{deg:g} deg", deg)
        self.polar_combo.setToolTip("Limit the drawing direction to multiples of this angle from the first point")
        self.polar_combo.activated.connect(lambda i: self.api.viewport.set_snap(polar_step_deg=self.polar_combo.itemData(i)))
        bar.addWidget(self.polar_combo)
        self.ortho_action = bar.addAction("Ortho")
        self.ortho_action.setCheckable(True)
        self.ortho_action.setToolTip("Keep drawing along one axis from the first point")
        self.ortho_action.toggled.connect(lambda on: self.api.viewport.set_snap(ortho=on))

    def _sync_viewport_bars(self) -> None:
        """Make every control show the viewport state (without firing its handler)."""
        st = self.api.viewport.state
        for actions in (self._render_actions, getattr(self, "_render_menu_actions", {})):
            for mode, a in actions.items():
                a.blockSignals(True)
                a.setChecked(mode == st.render_mode)
                a.blockSignals(False)
        for flag, a in self._filter_actions.items():
            a.blockSignals(True)
            a.setChecked(st.is_visible(flag))
            a.blockSignals(False)
        self.mesh_display_combo.blockSignals(True)
        self.mesh_display_combo.setCurrentIndex(max(0, self.mesh_display_combo.findData(st.mesh_display)))
        self.mesh_display_combo.blockSignals(False)
        for action, flag in ((getattr(self, "_grid_action", None), VisibilityFlags.GRID),
                             (getattr(self, "_axes_action", None), VisibilityFlags.AXES),
                             (getattr(self, "_device_labels_action", None), VisibilityFlags.LABELS)):
            if action is not None:
                action.blockSignals(True)
                action.setChecked(st.is_visible(flag))
                action.blockSignals(False)
        self.snap_action.blockSignals(True)
        self.snap_action.setChecked(st.snap.enabled)
        self.snap_action.blockSignals(False)
        self.ortho_action.blockSignals(True)
        self.ortho_action.setChecked(st.snap.ortho)
        self.ortho_action.blockSignals(False)
        self.polar_combo.blockSignals(True)
        self.polar_combo.setCurrentIndex(max(0, self.polar_combo.findData(st.snap.polar_step_deg)))
        self.polar_combo.blockSignals(False)
        i = min(range(len(_GRIDS)), key=lambda k: abs(_GRIDS[k] - st.snap.grid_size))
        self.grid_combo.blockSignals(True)
        self.grid_combo.setCurrentIndex(i)
        self.grid_combo.blockSignals(False)
        self._sync_tool_actions()

    # -- Tool Properties dock -----------------------------------------------------------------------------------
    def _build_tool_properties_dock(self) -> None:
        self.tool_properties = ToolPropertiesPanel(self.api, self.tool_manager, self)
        dock = QDockWidget("Tool Properties", self)
        dock.setObjectName("ToolPropertiesDock")
        dock.setWidget(self.tool_properties)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.tool_properties_dock = dock

    # -- handlers -----------------------------------------------------------------------------------------------
    def _on_render_mode(self, mode: str) -> None:
        self.api.viewport.set_render_mode(mode)

    def _on_navigation(self, style: str) -> None:
        if not hasattr(self.viewport_widget, "set_navigation"):
            self.statusBar().showMessage("Navigation styles need the 3D view (not available here)", 5000)
            return
        self.viewport_widget.set_navigation(style)
        self.statusBar().showMessage(dict(_NAV)[style], 4000)

    def _on_save_view_image(self, path: str = "") -> str:
        if not hasattr(self.viewport_widget, "snapshot"):
            QMessageBox.information(self, "Save Image", "The 3D view is not available here, so there is nothing to save.")
            return ""
        path = path or QFileDialog.getSaveFileName(self, "Save View as Image", "view.png", "Images (*.png *.jpg)")[0]
        if not path:
            return ""
        self.viewport_widget.snapshot(path)
        self.statusBar().showMessage(f"Saved {path}", 5000)
        return path
