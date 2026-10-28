"""
PyFDS Viewport Abstraction
===========================
Pure-data abstractions for 3D viewport state.  Zero rendering code lives here.

Design contract for future GUI
-------------------------------
The backend *owns* viewport state as plain Python data.
A future GUI (PySide6/PyOpenGL or web) subscribes to ``VIEWPORT_CHANGED`` and
``VIEWPORT_CAMERA_CHANGED`` events and reads these structs to rebuild its
render state.  All mutations go through ``ViewportController`` so the history
of camera moves can be tracked and the EventBus is always notified.

This separation means:
- Unit tests can test viewport logic without a display
- AI agents can programmatically set camera positions
- Multiple GUI back-ends (desktop, web, VR) share the same state model

Classes
-------
ViewportCamera          — camera position / orientation (immutable value object)
CameraPreset            — named standard views
TransformMode           — active gizmo mode (select/translate/rotate/scale)
SnapSettings            — grid-snap configuration
ViewportState           — full mutable state: camera + mode + visibility flags
ViewportController      — mutates ViewportState, emits events, supports undo

Coordinate system
-----------------
Right-handed. X = East, Y = North, Z = Up (FDS convention).
"""
from __future__ import annotations

import math
import threading
from typing import Any, Dict, Optional, Tuple

from .viewport_types import (  # noqa: F401  (re-exported)
    CameraPreset,
    ProjectionMode,
    TransformMode,
    VisibilityFlags,
)
from .viewport_camera import (  # noqa: F401  (re-exported)
    SnapSettings,
    ViewportCamera,
    ViewportState,
)



class ViewportController:
    """
    The single point of contact for all viewport mutations.

    Maintains a ``ViewportState`` instance and emits
    ``VIEWPORT_CHANGED`` / ``VIEWPORT_CAMERA_CHANGED`` events through the
    global EventBus on every state change.

    A future GUI creates one ViewportController per 3D panel and subscribes
    to the events to trigger a repaint.

    Example::

        vc = ViewportController()
        vc.set_camera(ViewportCamera.from_preset(CameraPreset.ISOMETRIC))
        vc.set_transform_mode(TransformMode.TRANSLATE)
        vc.zoom(1.5)
    """

    def __init__(self, state: Optional[ViewportState] = None) -> None:
        self._state = state or ViewportState()
        self._lock  = threading.Lock()

    @property
    def state(self) -> ViewportState:
        with self._lock:
            return self._state

    # ── Camera ───────────────────────────────────────────────────────────────

    def set_camera(self, camera: ViewportCamera) -> None:
        with self._lock:
            self._state.camera = camera
        self._emit_camera(camera)

    def apply_preset(self, preset: CameraPreset, distance: float = 15.0) -> None:
        self.set_camera(ViewportCamera.from_preset(preset, distance))

    def orbit(self, delta_yaw_deg: float, delta_pitch_deg: float) -> None:
        with self._lock:
            new_cam = self._state.camera.orbit(delta_yaw_deg, delta_pitch_deg)
            self._state.camera = new_cam
        self._emit_camera(new_cam)

    def pan(self, dx_world: float, dy_world: float) -> None:
        with self._lock:
            new_cam = self._state.camera.pan(dx_world, dy_world)
            self._state.camera = new_cam
        self._emit_camera(new_cam)

    def zoom(self, factor: float) -> None:
        with self._lock:
            new_cam = self._state.camera.zoom_to(factor)
            self._state.camera = new_cam
        self._emit_camera(new_cam)

    def frame_all(self, bbox: Optional[Tuple[float, ...]] = None) -> None:
        """
        Frame the camera to show *bbox* = (xmin,xmax,ymin,ymax,zmin,zmax).

        If bbox is None a default view is used.
        """
        if bbox is None:
            self.apply_preset(CameraPreset.ISOMETRIC, distance=15.0)
            return
        cx = (bbox[0] + bbox[1]) * 0.5
        cy = (bbox[2] + bbox[3]) * 0.5
        cz = (bbox[4] + bbox[5]) * 0.5
        diagonal = math.sqrt(
            (bbox[1] - bbox[0]) ** 2 +
            (bbox[3] - bbox[2]) ** 2 +
            (bbox[5] - bbox[4]) ** 2
        )
        dist = max(diagonal * 1.5, 1.0)
        new_cam = ViewportCamera(
            position=(cx + dist * 0.6, cy - dist * 0.6, cz + dist * 0.5),
            target=(cx, cy, cz),
            up=(0.0, 0.0, 1.0),
        )
        with self._lock:
            self._state.camera = new_cam
        self._emit_camera(new_cam)

    # ── Mode / visibility ─────────────────────────────────────────────────────

    def set_transform_mode(self, mode: TransformMode) -> None:
        with self._lock:
            self._state.transform_mode = mode
        self._emit_state()

    def set_visibility(self, flag: VisibilityFlags, visible: bool) -> None:
        with self._lock:
            self._state.set_visibility(flag, visible)
        self._emit_state()

    def toggle_wireframe(self) -> None:
        with self._lock:
            self._state.show_wireframe = not self._state.show_wireframe
            self._state.render_mode = "wireframe" if self._state.show_wireframe else "solid"
        self._emit_state()

    def set_render_mode(self, mode: str) -> None:
        """wireframe | solid | outlines (solid with edges) | realistic (smooth shading)."""
        from .viewport_types import RENDER_MODES
        if mode not in RENDER_MODES:
            raise ValueError(f"render mode must be one of {', '.join(RENDER_MODES)}")
        with self._lock:
            self._state.render_mode = mode
            self._state.show_wireframe = mode == "wireframe"
        self._emit_state()

    def set_mesh_display(self, mode: str) -> None:
        """hidden | outline | lines | boundary."""
        from .viewport_types import MESH_DISPLAYS
        if mode not in MESH_DISPLAYS:
            raise ValueError(f"mesh display must be one of {', '.join(MESH_DISPLAYS)}")
        with self._lock:
            self._state.mesh_display = mode
            self._state.set_visibility(VisibilityFlags.MESHES, mode != "hidden")
        self._emit_state()

    def set_clip_plane(self, z: Optional[float]) -> None:
        with self._lock:
            self._state.clip_plane_z = z
        self._emit_state()

    def set_snap(self, **kwargs: Any) -> None:
        """Update snap settings by keyword: grid_size=0.05, enabled=True, etc."""
        with self._lock:
            for k, v in kwargs.items():
                setattr(self._state.snap, k, v)
        self._emit_state()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return self._state.to_dict()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _emit_camera(self, camera: ViewportCamera) -> None:
        try:
            from pyfds.core.events import get_global_bus, EventType
            bus = get_global_bus()
            bus.emit(EventType.VIEWPORT_CAMERA_CHANGED, camera, source="ViewportController")
            bus.emit(EventType.VIEWPORT_CHANGED, self._state, source="ViewportController")
        except Exception:
            pass

    def _emit_state(self) -> None:
        try:
            from pyfds.core.events import get_global_bus, EventType
            get_global_bus().emit(EventType.VIEWPORT_CHANGED, self._state,
                                  source="ViewportController")
        except Exception:
            pass

    def __repr__(self) -> str:
        mode = self._state.transform_mode.name
        proj = self._state.camera.projection.name
        return f"<ViewportController mode={mode} projection={proj}>"
