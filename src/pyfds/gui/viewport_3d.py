"""
Interactive 3D viewport — thin ``pyvistaqt.QtInteractor`` wrapper.

All scene-building logic lives in ``viewport_scene.py`` (pure data, fully unit tested) and all drawing-tool logic in
``viewport_tools/`` (also Qt-free and tested). This widget owns the ``QtInteractor``, rebuilds the scene on every
project mutation, turns mouse and key events into ``Hit`` objects for the active tool (``viewport_input.py``), draws
the tool's preview (``viewport_preview.py``) and forwards camera-preset/visibility requests to ``api.viewport`` so the
AI agent and the GUI drive the same camera state.

With the *Select* tool a click selects an object and emits ``entity_picked(manager_attr, entity)`` /
``selection_changed``; ``MainWindow`` mirrors that into the project tree. With any other tool the click goes to the
tool, which creates objects through ``api`` itself (so there are no dialogs while drawing and each drawing is one undo
step). Dragging never counts as a click, so rotating the view cannot draw.

``QtInteractor`` needs a real OpenGL-capable native window handle. Qt's offscreen QPA platform (used by the headless
test suite) cannot provide one on this machine — attempting construction there is not a catchable Python exception,
it is a native access violation that kills the whole process. **Never construct this class under the offscreen
platform.** ``window.py`` guards this by checking ``QApplication.instance().platformName()`` before importing this
module at all. This widget is therefore verified by a live desktop launch, not the automated test suite.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

import pyvista as pv
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget
from pyvistaqt import QtInteractor

from pyfds.api import FdsApi
from pyfds.core.events import EventType
from pyfds.core.viewport import CameraPreset, VisibilityFlags
from pyfds.gui.viewport_environment import Environment, set_lights
from pyfds.gui.viewport_input import install_input, pick_hit
from pyfds.gui.viewport_preview import PreviewLayer
from pyfds.gui.viewport_quality import ViewportQualityMixin
from pyfds.gui.viewport_scene import FIELD_DATA_KEY, build_scene, entity_key, preset_distance, scene_bbox
from pyfds.gui.viewport_tools import SELECT, Hit, ToolManager
from pyfds.gui.viewport_tools.roam import RoamCamera

_GROUND_PLANE_COLOR = "#33373c"
_NAVIGATION = ("orbit", "turntable", "roam")
#: Draw-menu tool names (agent tool names) -> viewport tools
_TOOL_FOR = {"add_obstruction": "obstruction", "add_vent": "vent", "add_hole": "hole", "add_mesh": "mesh"}

_REFRESH_EVENTS = (
    EventType.COMMAND_EXECUTED,
    EventType.UNDO_PERFORMED,
    EventType.REDO_PERFORMED,
    EventType.HISTORY_CLEARED,
    EventType.PROJECT_LOADED,
    EventType.PROJECT_CREATED,
    EventType.VIEWPORT_CHANGED,
)


class Viewport3D(ViewportQualityMixin, QWidget):
    """3D scene view. Rebuilds from ``api`` state; edits only through the tools (which call ``api``)."""

    #: A click in the 3D view selected one object — (manager_attr, entity), as ProjectExplorer.selected() returns.
    entity_picked = Signal(str, object)
    #: The full selection after every pick (plain or Ctrl): [(manager_attr, entity), ...].
    selection_changed = Signal(list)
    #: Kept for older callers; the drawing tools no longer ask for a footprint through this signal.
    box_footprint_picked = Signal(str, float, float, float, float)
    cursor_moved = Signal(object)      # (x, y, z) in model coordinates under the mouse, or None when it leaves
    context_requested = Signal(object, object)   # (manager_attr, entity) under a right click or None, global position
    tool_changed = Signal(str)         # the active tool's name
    status_message = Signal(str)       # what the tool wants the status bar to say

    def __init__(self, api: FdsApi, parent: Optional[QWidget] = None, tools: Optional[ToolManager] = None) -> None:
        super().__init__(parent)
        self._api = api
        self._entity_lookup: Dict[str, Tuple[str, Any]] = {}
        self._selected_keys: Set[str] = set()
        self._navigation = "orbit"
        self._roam: Optional[RoamCamera] = None
        self.tools = tools or ToolManager(api)
        self.tools.subscribe(self._on_tool_change)
        self._drawing = False                    # a non-select tool is active (meshes then must not catch clicks)

        self.plotter = QtInteractor(self)
        self.plotter.set_background("#202225")
        self._preview = PreviewLayer(self.plotter)
        self._environment = Environment()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plotter.interactor)

        self._sub_ids = [api.subscribe(t, self._on_scene_event) for t in _REFRESH_EVENTS]
        self._camera_sub_id = api.subscribe(EventType.VIEWPORT_CAMERA_CHANGED, self._on_camera_event)

        import vtk
        from .viewport_cursor import install_cursor_tracking
        self._picker = vtk.vtkCellPicker()
        self._picker.SetTolerance(0.0005)
        self._cursor_filter = install_cursor_tracking(self.plotter, self._on_cursor)
        self._input_filter = install_input(self.plotter, self._on_click, self._on_double_click, self._on_key,
                                           self._on_wheel, self._on_drag, self._on_context)

        self.refresh()
        self._fit()  # sensible initial framing only, once
        try:                                                  # the anti-aliasing chosen in Hardware & Graphics Settings
            from PySide6.QtCore import QSettings
            self.set_antialiasing(str(QSettings("PyFDS", "PyFDS").value("graphics/antialiasing", "off") or "off"))
        except Exception:
            pass

    # ── Event-driven refresh ─────────────────────────────────────────────────

    def _on_scene_event(self, event) -> None:
        self.refresh()

    def _on_camera_event(self, event) -> None:
        self._sync_camera(event.payload)

    def refresh(self) -> None:
        """Rebuild every actor from current project state. Camera untouched —
        add/remove/undo shouldn't yank the user's view around."""
        self._preview.clear()
        self.plotter.clear()
        self._entity_lookup = {}
        self._mesh_actors = []

        # Permanent Z=0 reference surface — visual grid aid, and a floor for the drawing tools to hit even in a
        # brand-new empty project.
        ground_size = max(preset_distance(self._api) * 2, 20.0)
        ground = pv.Plane(center=(0, 0, 0), direction=(0, 0, 1), i_size=ground_size, j_size=ground_size)
        self.plotter.add_mesh(ground, color=_GROUND_PLANE_COLOR, opacity=0.25, show_edges=False)

        highlight = tuple(self._api.viewport.state.highlight_color)
        for spec in build_scene(self._api):
            key = entity_key(spec.manager_attr, spec.entity) if spec.entity is not None else None
            color = highlight if key in self._selected_keys else spec.color
            # While drawing, mesh boxes and decorations must not intercept clicks meant for the floor or objects.
            pickable = not spec.helper and not (self._drawing and spec.entity_kind == "mesh")
            extra = {"pbr": True, "metallic": spec.pbr[0], "roughness": spec.pbr[1]} if spec.pbr else {}
            if spec.texture:
                extra["texture"] = self._texture(spec.texture)
                color = "white"                 # the image supplies the colour (a selection still tints it)
                if key in self._selected_keys:
                    color = highlight
            actor = self.plotter.add_mesh(
                spec.mesh, color=color, style=spec.style, opacity=spec.opacity, label=spec.label,
                show_edges=spec.edges, edge_color="#101010",
                smooth_shading=spec.smooth, split_sharp_edges=spec.smooth, pickable=pickable, **extra,
            )
            if spec.texture and spec.pbr:
                tex = extra["texture"]          # physically based shading takes its colour image from the property
                tex.SetUseSRGBColorSpace(True)
                actor.GetProperty().SetBaseColorTexture(tex)
            if spec.entity_kind == "mesh":
                self._mesh_actors.append(actor)
            if spec.entity is not None:
                self._entity_lookup[key] = (spec.manager_attr, spec.entity)
        self._selected_keys &= set(self._entity_lookup)
        # clear() removed the lights, and an unlit scene is drawn flat (and cannot shade physically based materials)
        set_lights(self.plotter)
        self._draw_decorations()
        self._environment.apply(self.plotter, self._api.viewport.state.render_mode == "realistic")
        self._draw_preview()
        self.plotter.render()

    def _texture(self, data: str):
        """The ``pv.Texture`` for base64 image data, decoded once and kept (a refresh redraws every actor)."""
        cache = self.__dict__.setdefault("_textures", {})
        if data not in cache:
            import base64
            import io
            import numpy as np
            import pyvista as pv
            from PIL import Image
            img = Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")
            cache[data] = pv.Texture(np.asarray(img))
        return cache[data]

    def _draw_decorations(self) -> None:
        """Reference grid, orientation axes and device name labels (View > Show, Devices > Device Labels)."""
        state = self._api.viewport.state
        p = self.plotter
        try:
            p.remove_bounds_axes()
        except Exception:
            pass
        bbox = scene_bbox(self._api)
        if state.is_visible(VisibilityFlags.GRID) and bbox is not None:
            p.show_bounds(bounds=bbox, grid="back", location="outer", ticks="outside", color="#8a8f98",
                          font_size=8, show_xlabels=True, show_ylabels=True, show_zlabels=True,
                          xtitle="X (m)", ytitle="Y (m)", ztitle="Z (m)")
        if state.is_visible(VisibilityFlags.AXES):
            if not getattr(self, "_axes_shown", False):
                p.show_axes()
                self._axes_shown = True
        elif getattr(self, "_axes_shown", False):
            p.hide_axes()
            self._axes_shown = False
        if state.is_visible(VisibilityFlags.LABELS):
            points = [(tuple(d.xyz), d.name) for d in self._api.devices.all()
                      if getattr(d, "enabled", True) and getattr(d, "xyz", None) is not None]
            if points:
                p.add_point_labels([pt for pt, _n in points], [n for _pt, n in points], font_size=11,
                                   text_color="#f5d76e", shape=None, show_points=False, always_visible=True,
                                   pickable=False, name="pyfds_device_labels")

    # ── Tools ────────────────────────────────────────────────────────────────

    def activate_tool(self, name: str) -> None:
        self.tools.activate(_TOOL_FOR.get(name, name))

    def set_draw_mode(self, tool_name: Optional[str]) -> None:
        """Older entry point: an agent tool name ("add_obstruction" ...) starts that tool, None returns to Select."""
        self.tools.activate(SELECT if tool_name is None else _TOOL_FOR.get(tool_name, tool_name))

    def _on_tool_change(self) -> None:
        drawing = self.tools.current.name != SELECT
        if drawing != self._drawing:
            self._drawing = drawing
            self.refresh()                       # pickability of the mesh boxes changes
        else:
            self._draw_preview()
        self.tool_changed.emit(self.tools.current.name)

    def _draw_preview(self) -> None:
        p = self.tools.preview()
        self._preview.show(p)
        for msg in self.tools.take_messages() or [p.text]:
            if msg:
                self.status_message.emit(msg)

    def _hit_at(self, x: int, y: int) -> Optional[Hit]:
        got = pick_hit(self.plotter, self._picker, x, y)
        if self.tools.current.name == SELECT and self._mesh_actors and got is not None:
            # A mesh box encloses the objects inside it, so its faces are hit first. Look through it for an object;
            # the mesh is selected only when nothing else is there.
            for a in self._mesh_actors:
                a.SetPickable(False)
            inside = pick_hit(self.plotter, self._picker, x, y)
            for a in self._mesh_actors:
                a.SetPickable(True)
            if inside is not None and inside[2] is not None and not inside[2].startswith("meshes:"):
                got = inside
        if got is None:
            return None
        point, normal, key = got
        return Hit(point, normal, self._entity_lookup.get(key) if key else None)

    def _on_cursor(self, point) -> None:
        self.cursor_moved.emit(point)
        if point is not None and self.tools.current.active():
            self.tools.move(Hit(tuple(point)))

    # ── Mouse and keys ───────────────────────────────────────────────────────

    def _on_click(self, x: int, y: int, ctrl: bool) -> None:
        if self._roam is not None:
            return
        hit = self._hit_at(x, y)
        if hit is None:
            return
        if self.tools.current.name == SELECT:
            self._select(hit, ctrl)
        else:
            self.tools.click(hit)

    def _on_context(self, x: int, y: int, global_pos) -> None:
        if self._roam is not None:
            return
        hit = self._hit_at(x, y)
        self.context_requested.emit(hit.entity if hit is not None else None, global_pos)

    def _on_double_click(self, x: int, y: int) -> None:
        if self.tools.current.active():
            self.tools.finish()

    def _on_key(self, key: int, _modifiers: int) -> bool:
        if key == Qt.Key_Escape:
            if self.tools.escape():
                return True
            return self.tools.current.name != SELECT
        if key in (Qt.Key_Return, Qt.Key_Enter) and self.tools.current.active():
            self.tools.finish()
            return True
        if self._roam is not None:
            moves = {Qt.Key_W: (1, 0, 0), Qt.Key_S: (-1, 0, 0), Qt.Key_D: (0, 1, 0), Qt.Key_A: (0, -1, 0),
                     Qt.Key_E: (0, 0, 1), Qt.Key_Q: (0, 0, -1)}
            turns = {Qt.Key_Left: (1, 0), Qt.Key_Right: (-1, 0), Qt.Key_Up: (0, 1), Qt.Key_Down: (0, -1)}
            if key in moves:
                self._roam.move(*moves[key])
            elif key in turns:
                self._roam.look(turns[key][0] * self._roam.turn, turns[key][1] * self._roam.turn)
            else:
                return False
            self._apply_roam()
            return True
        return False

    def _on_wheel(self, direction: int) -> bool:
        if self._roam is None:
            return False
        self._roam.move(forward=direction)
        self._apply_roam()
        return True

    def _on_drag(self, dx: int, dy: int) -> bool:
        if self._roam is None:
            return False
        self._roam.look(-dx * 0.25, -dy * 0.25)
        self._apply_roam()
        return True

    # ── Selection ────────────────────────────────────────────────────────────

    def _select(self, hit: Hit, ctrl: bool) -> None:
        if hit.entity is None:
            return
        key = entity_key(*hit.entity)
        if ctrl:
            self._selected_keys.symmetric_difference_update({key})
        else:
            self._selected_keys = {key}
        self.entity_picked.emit(*hit.entity)
        self.selection_changed.emit([self._entity_lookup[k] for k in self._selected_keys if k in self._entity_lookup])
        QTimer.singleShot(0, self.refresh)

    # ── Camera ───────────────────────────────────────────────────────────────

    def _fit(self) -> None:
        """Frame the model (not the big floor plane that is always drawn), keeping the view direction."""
        bbox = scene_bbox(self._api)
        if bbox is None:
            self.plotter.reset_camera()
        else:
            self.plotter.reset_camera(bounds=bbox)

    def reset_view(self) -> None:
        self._fit()
        self.plotter.render()

    def apply_preset(self, preset: CameraPreset) -> None:
        # Distance scales to the actual model extent — a fixed distance would
        # put a 2m room and a 200m tunnel at the same arbitrary zoom level.
        self._api.viewport.apply_preset(preset, distance=preset_distance(self._api))
        # the preset looks at the origin; fit the camera to the model (keeping the view direction)
        self._fit()
        self.plotter.render()

    def toggle_wireframe(self) -> None:
        self._api.viewport.toggle_wireframe()

    def set_visibility(self, flag, visible: bool) -> None:
        self._api.viewport.set_visibility(flag, visible)

    def _sync_camera(self, camera) -> None:
        self.plotter.camera.position = camera.position
        self.plotter.camera.focal_point = camera.target
        self.plotter.camera.up = camera.up
        self.plotter.render()

    # ── Navigation styles (UX-19, UX-20) ─────────────────────────────────────

    @property
    def navigation(self) -> str:
        return self._navigation

    def set_navigation(self, style: str) -> None:
        """orbit (trackball), turntable (Z stays up — the Smokeview feel) or roam (first person: WASD, Q/E, arrows,
        wheel, drag to look)."""
        if style not in _NAVIGATION:
            raise ValueError(f"navigation must be one of {', '.join(_NAVIGATION)}")
        if style == "roam":
            cam = self.plotter.camera
            self._roam = RoamCamera.looking(cam.position, cam.focal_point)
            bbox = scene_bbox(self._api)
            if bbox is not None:
                self._roam.set_step_for_model(bbox)
            import vtk
            self.plotter.iren.interactor.SetInteractorStyle(vtk.vtkInteractorStyleUser())
            self._apply_roam()
        else:
            self._roam = None
            (self.plotter.enable_terrain_style if style == "turntable" else self.plotter.enable_trackball_style)()
        self._navigation = style

    def _apply_roam(self) -> None:
        cam = self.plotter.camera
        cam.position = self._roam.position
        cam.focal_point = self._roam.focal_point(max(1.0, self._roam.step * 8))
        cam.up = (0.0, 0.0, 1.0)
        self.plotter.reset_camera_clipping_range()
        self.plotter.render()

    # ── Teardown ─────────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        for sub_id in self._sub_ids:
            self._api.unsubscribe(sub_id)
        self._api.unsubscribe(self._camera_sub_id)
        self.plotter.close()
