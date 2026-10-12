"""
Interactive 3D viewport — thin ``pyvistaqt.QtInteractor`` wrapper.

All scene-building logic lives in ``viewport_scene.py`` (pure data, fully
unit tested). This widget only owns the ``QtInteractor``, rebuilds the
scene on every project mutation, and forwards camera-preset/visibility
requests to ``api.viewport`` (``ViewportController``) so the AI agent and
the GUI drive the same camera state — never touches ``api.project`` or a
VTK camera position directly from a "business logic" decision, only from
raw mouse interaction (which VTK's own trackball interactor handles
natively; that live-drag state is intentionally NOT written back to
``ViewportController`` in this version — see the module docstring in
``core/viewport.py`` and the resume notes in memory for why that's a
deliberate, documented scope boundary rather than an oversight).

Left-clicking an entity emits ``entity_picked(manager_attr, entity)`` —
``MainWindow`` forwards this straight into ``ProjectExplorer.select_entity()``,
so a viewport click drives the exact same Delete/Edit-Properties/right-click
handlers a tree click does. There is no separate "picked in 3D" code path.

``set_draw_mode(tool_name)`` switches the viewport into a two-click
box-footprint tool (for "add_obstruction"/"add_vent"/"add_hole"): first
click records one XY corner, second click records the opposite corner and
emits ``box_footprint_picked(tool_name, x_min, x_max, y_min, y_max)`` —
``MainWindow`` prompts for the Z range and then calls the dispatcher with
the same tool name any other "Add..." menu action uses. Z is always
discarded from both picks; a permanent semi-transparent ground plane at
Z=0 (added in ``refresh()``) guarantees there is always something
pickable to compute an XY point against, even in a brand-new empty
project. Draw mode and entity-select mode are mutually exclusive — only
one of ``enable_mesh_picking``/``enable_point_picking`` is ever registered
with the plotter at a time.

``QtInteractor`` needs a real OpenGL-capable native window handle. Qt's
offscreen QPA platform (used by the headless test suite) cannot provide
one on this machine — attempting construction there is not a catchable
Python exception, it is a native access violation that kills the whole
process. **Never construct this class under the offscreen platform.**
``main_window.py`` guards this by checking
``QApplication.instance().platformName()`` before importing this module at
all. This widget is therefore verified by a live desktop launch, not the
automated test suite.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

import pyvista as pv
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget
from pyvistaqt import QtInteractor

from pyfds.api import FdsApi
from pyfds.core.events import EventType
from pyfds.core.viewport import CameraPreset
from pyfds.gui.viewport_scene import FIELD_DATA_KEY, build_scene, entity_key, preset_distance

_GROUND_PLANE_COLOR = "#33373c"

_REFRESH_EVENTS = (
    EventType.COMMAND_EXECUTED,
    EventType.UNDO_PERFORMED,
    EventType.REDO_PERFORMED,
    EventType.HISTORY_CLEARED,
    EventType.PROJECT_LOADED,
    EventType.PROJECT_CREATED,
    EventType.VIEWPORT_CHANGED,
)


class Viewport3D(QWidget):
    """3D scene view. Rebuilds from ``api`` state; never mutates it directly."""

    #: Emitted when the user clicks an entity in the 3D view — (manager_attr, entity),
    #: the exact pair ProjectExplorer.selected() returns, so a single click here
    #: drives the same Delete/Edit-Properties/right-click handlers as a tree click.
    entity_picked = Signal(str, object)

    #: Emitted after every pick (plain or Ctrl) with the *full* resolved
    #: selection — [(manager_attr, entity), ...] — the same shape
    #: ProjectExplorer.selected_entities() returns, so MainWindow can mirror
    #: a viewport multi-pick into the tree with one call
    #: (explorer.select_entities(...)), same idea as entity_picked already
    #: mirrors a single pick.
    selection_changed = Signal(list)

    #: Emitted after the second click of a draw-box sequence —
    #: (tool_name, x_min, x_max, y_min, y_max). MainWindow prompts for the
    #: Z range and calls the dispatcher with the same tool_name any other
    #: "Add..." menu action uses.
    box_footprint_picked = Signal(str, float, float, float, float)

    def __init__(self, api: FdsApi, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._api = api
        self._entity_lookup: Dict[str, Tuple[str, Any]] = {}
        self._selected_keys: Set[str] = set()
        self._draw_mode: Optional[str] = None
        self._draw_first_point: Optional[Tuple[float, float]] = None

        self.plotter = QtInteractor(self)
        self.plotter.set_background("#202225")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plotter.interactor)

        self._sub_ids = [api.subscribe(t, self._on_scene_event) for t in _REFRESH_EVENTS]
        self._camera_sub_id = api.subscribe(EventType.VIEWPORT_CAMERA_CHANGED, self._on_camera_event)

        self.refresh()
        self.plotter.reset_camera()  # sensible initial framing only, once

    # ── Event-driven refresh ─────────────────────────────────────────────────

    def _on_scene_event(self, event) -> None:
        self.refresh()

    def _on_camera_event(self, event) -> None:
        self._sync_camera(event.payload)

    def refresh(self) -> None:
        """Rebuild every actor from current project state. Camera untouched —
        add/remove/undo shouldn't yank the user's view around."""
        self.plotter.clear()
        self._entity_lookup = {}

        # Permanent Z=0 reference surface — visual grid aid, and guarantees
        # enable_point_picking (the draw tool) always has something pickable
        # to compute an XY point against, even in a brand-new empty project.
        ground_size = max(preset_distance(self._api) * 2, 20.0)
        ground = pv.Plane(center=(0, 0, 0), direction=(0, 0, 1), i_size=ground_size, j_size=ground_size)
        self.plotter.add_mesh(ground, color=_GROUND_PLANE_COLOR, opacity=0.25, show_edges=False)

        highlight = tuple(self._api.viewport.state.highlight_color)
        for spec in build_scene(self._api):
            key = entity_key(spec.manager_attr, spec.entity) if spec.entity is not None else None
            color = highlight if key in self._selected_keys else spec.color
            self.plotter.add_mesh(
                spec.mesh, color=color, style=spec.style,
                opacity=spec.opacity, label=spec.label,
            )
            if spec.entity is not None:
                self._entity_lookup[key] = (spec.manager_attr, spec.entity)
        # Multi-selected entities may have been removed by whatever
        # triggered this refresh (delete, undo, ...) — drop any stale keys
        # so a later Move/Rotate/Scale doesn't try to act on a dead entity.
        self._selected_keys &= set(self._entity_lookup)
        self._register_picking()
        self.plotter.render()

    def _register_picking(self) -> None:
        """(Re-)register whichever picking mode is currently active. Called
        after every refresh() — clear() drops the previous picking observer
        along with the old actors — and whenever set_draw_mode() switches
        modes. Draw mode and entity-select mode are mutually exclusive.

        disable_picking() first is required, not optional: pyvista raises
        PyVistaPickingError ("Picking is already enabled") if
        enable_point_picking() is called while enable_mesh_picking() (or
        vice versa) is still active — confirmed empirically switching into
        draw mode crashed with exactly this error before adding this call.
        """
        self.plotter.disable_picking()
        if self._draw_mode is None:
            # use_actor=False so the callback receives the picked *mesh*, not
            # the actor — confirmed empirically that VTK's picker does not
            # reliably hand back the same Python actor wrapper add_mesh()
            # returned, so identity-based actor lookup silently failed; the
            # mesh's field_data key (set in build_scene) survives regardless
            # of wrapper identity.
            #
            # color=None: pyvista's own single-actor highlight-on-pick is
            # replaced by our own multi-entity highlighting in refresh()
            # (recolors every currently-selected mesh from
            # self._selected_keys) — its built-in highlight only ever tracks
            # one actor at a time, which can't represent a multi-select.
            self.plotter.enable_mesh_picking(
                callback=self._on_mesh_picked, use_actor=False, left_clicking=True,
                show_message=False, color=None,
            )
        else:
            # picker="cell" (vtkCellPicker) computes the exact continuous
            # ray/face intersection point — the default "point" picker
            # (vtkPointPicker) only *snaps to existing mesh vertices* within
            # a small screen-pixel tolerance, so on a coarse ground plane
            # (11x11 vertices over 40x40m = 4m spacing) almost every click
            # misses entirely. Confirmed empirically as the cause of the
            # draw tool silently doing nothing on the first attempt.
            self.plotter.enable_point_picking(
                callback=self._on_draw_point_picked, left_clicking=True,
                show_message=False, picker="cell",
            )

    def _on_mesh_picked(self, mesh) -> None:
        try:
            key = str(mesh.field_data[FIELD_DATA_KEY][0])
        except (KeyError, IndexError):
            return
        picked = self._entity_lookup.get(key)
        if picked is None:
            return

        # Ctrl-click toggles membership (standard multi-select convention,
        # same as ProjectExplorer's Ctrl/Shift-click ExtendedSelection); a
        # plain click replaces the selection with just this one entity —
        # unchanged single-pick behavior for everyone not using multi-select.
        ctrl_held = False
        try:
            ctrl_held = bool(self.plotter.iren.interactor.GetControlKey())
        except AttributeError:
            pass  # picker fired outside a real interactor (shouldn't happen live)

        if ctrl_held:
            if key in self._selected_keys:
                self._selected_keys.discard(key)
            else:
                self._selected_keys.add(key)
        else:
            self._selected_keys = {key}

        self.entity_picked.emit(*picked)
        self.selection_changed.emit(
            [self._entity_lookup[k] for k in self._selected_keys if k in self._entity_lookup]
        )
        # Deferred: a full plotter.clear()+rebuild synchronously inside VTK's
        # own picking callback would tear down the very actor whose pick
        # event is still executing — same reasoning as the HVAC Network
        # Editor's QTimer-deferred drag-commit (hvac_network_editor.py).
        QTimer.singleShot(0, self.refresh)

    # ── Draw-box tool ────────────────────────────────────────────────────────

    def set_draw_mode(self, tool_name: Optional[str]) -> None:
        """tool_name is "add_obstruction"/"add_vent"/"add_hole", or None to
        return to normal entity-select picking."""
        self._draw_mode = tool_name
        self._draw_first_point = None
        self._register_picking()

    def _on_draw_point_picked(self, point) -> None:
        x, y = float(point[0]), float(point[1])
        if self._draw_first_point is None:
            self._draw_first_point = (x, y)
            return
        x1, y1 = self._draw_first_point
        tool_name = self._draw_mode
        # One box per tool activation (v1 simplification) — back to
        # entity-select picking once the footprint is captured.
        self.set_draw_mode(None)
        self.box_footprint_picked.emit(tool_name, min(x1, x), max(x1, x), min(y1, y), max(y1, y))

    # ── Camera ───────────────────────────────────────────────────────────────

    def reset_view(self) -> None:
        self.plotter.reset_camera()

    def apply_preset(self, preset: CameraPreset) -> None:
        # Distance scales to the actual model extent — a fixed distance would
        # put a 2m room and a 200m tunnel at the same arbitrary zoom level.
        self._api.viewport.apply_preset(preset, distance=preset_distance(self._api))
        # the preset looks at the origin; fit the camera to the model (keeping the view direction) so a
        # model that sits away from (0, 0, 0) is centred and fills the view
        self.plotter.reset_camera()
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

    # ── Teardown ─────────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        for sub_id in self._sub_ids:
            self._api.unsubscribe(sub_id)
        self._api.unsubscribe(self._camera_sub_id)
        self.plotter.close()
