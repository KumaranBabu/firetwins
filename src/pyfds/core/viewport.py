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

import copy
import math
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class CameraPreset(Enum):
    """Standard orthographic view directions."""
    FRONT       = auto()   # -Y → +Y look direction
    BACK        = auto()   # +Y → -Y
    LEFT        = auto()   # +X → -X
    RIGHT       = auto()   # -X → +X
    TOP         = auto()   # -Z → +Z (plan view)
    BOTTOM      = auto()   # +Z → -Z
    ISOMETRIC   = auto()   # classic 3/4 view


class TransformMode(Enum):
    """Active transform gizmo / interaction mode."""
    SELECT      = auto()   # click-to-select (default)
    TRANSLATE   = auto()   # move entities
    ROTATE      = auto()   # rotate entities
    SCALE       = auto()   # uniform/non-uniform scale
    MEASURE     = auto()   # distance / angle measurement tool


class ProjectionMode(Enum):
    """Camera projection type."""
    PERSPECTIVE  = auto()
    ORTHOGRAPHIC = auto()


class VisibilityFlags(Enum):
    """Named visibility layer toggles."""
    MESHES          = auto()
    OBSTRUCTIONS    = auto()
    VENTS           = auto()
    DEVICES         = auto()
    SLICES          = auto()
    BOUNDARIES      = auto()
    ISOSURFACES     = auto()
    HVAC            = auto()
    INIT_REGIONS    = auto()
    PROFILES        = auto()
    GEOMETRY        = auto()
    GRID            = auto()
    AXES            = auto()
    LABELS          = auto()


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ViewportCamera:
    """
    Immutable camera state.

    All positions / directions are in FDS world coordinates (metres).

    Attributes
    ----------
    position : (x, y, z) — camera eye position
    target   : (x, y, z) — look-at point
    up       : (x, y, z) — up vector (default Z-up)
    fov_deg  : vertical field-of-view in degrees (perspective mode)
    near     : near clip distance (m)
    far      : far clip distance (m)
    zoom     : orthographic zoom factor (ignored in perspective)
    projection : PERSPECTIVE or ORTHOGRAPHIC
    """
    position:   Tuple[float, float, float] = (10.0, -10.0, 8.0)
    target:     Tuple[float, float, float] = (0.0,  0.0,   0.0)
    up:         Tuple[float, float, float] = (0.0,  0.0,   1.0)
    fov_deg:    float = 45.0
    near:       float = 0.01
    far:        float = 10_000.0
    zoom:       float = 1.0
    projection: ProjectionMode = ProjectionMode.PERSPECTIVE

    # ── Derived properties ────────────────────────────────────────────────

    @property
    def distance(self) -> float:
        """Distance from eye to target."""
        dx = self.position[0] - self.target[0]
        dy = self.position[1] - self.target[1]
        dz = self.position[2] - self.target[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def orbit(self, delta_yaw_deg: float, delta_pitch_deg: float) -> "ViewportCamera":
        """Return a new camera orbited around target by (yaw, pitch) angles."""
        import math
        dx = self.position[0] - self.target[0]
        dy = self.position[1] - self.target[1]
        dz = self.position[2] - self.target[2]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0

        # Current azimuth and elevation
        azimuth   = math.atan2(dy, dx)
        elevation = math.asin(max(-1.0, min(1.0, dz / dist)))

        azimuth   += math.radians(delta_yaw_deg)
        elevation  = max(
            math.radians(-89), min(math.radians(89),
            elevation + math.radians(delta_pitch_deg))
        )

        new_dx = dist * math.cos(elevation) * math.cos(azimuth)
        new_dy = dist * math.cos(elevation) * math.sin(azimuth)
        new_dz = dist * math.sin(elevation)

        return ViewportCamera(
            position=(
                self.target[0] + new_dx,
                self.target[1] + new_dy,
                self.target[2] + new_dz,
            ),
            target=self.target,
            up=self.up,
            fov_deg=self.fov_deg,
            near=self.near,
            far=self.far,
            zoom=self.zoom,
            projection=self.projection,
        )

    def pan(self, dx_world: float, dy_world: float) -> "ViewportCamera":
        """Return a new camera panned by (dx, dy) in the view plane."""
        new_pos = (
            self.position[0] + dx_world,
            self.position[1] + dy_world,
            self.position[2],
        )
        new_tgt = (
            self.target[0] + dx_world,
            self.target[1] + dy_world,
            self.target[2],
        )
        return ViewportCamera(
            position=new_pos, target=new_tgt,
            up=self.up, fov_deg=self.fov_deg,
            near=self.near, far=self.far,
            zoom=self.zoom, projection=self.projection,
        )

    def zoom_to(self, factor: float) -> "ViewportCamera":
        """Return a camera with the eye moved closer/farther by *factor*."""
        if self.projection == ProjectionMode.ORTHOGRAPHIC:
            return ViewportCamera(
                position=self.position, target=self.target, up=self.up,
                fov_deg=self.fov_deg, near=self.near, far=self.far,
                zoom=max(0.001, self.zoom * factor),
                projection=self.projection,
            )
        # Perspective: move along view direction
        dx = self.position[0] - self.target[0]
        dy = self.position[1] - self.target[1]
        dz = self.position[2] - self.target[2]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        new_dist = max(0.01, dist / factor)
        scale = new_dist / dist
        return ViewportCamera(
            position=(
                self.target[0] + dx * scale,
                self.target[1] + dy * scale,
                self.target[2] + dz * scale,
            ),
            target=self.target, up=self.up,
            fov_deg=self.fov_deg, near=self.near, far=self.far,
            zoom=self.zoom, projection=self.projection,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": list(self.position),
            "target":   list(self.target),
            "up":       list(self.up),
            "fov_deg":  self.fov_deg,
            "near":     self.near,
            "far":      self.far,
            "zoom":     self.zoom,
            "projection": self.projection.name,
        }

    @classmethod
    def from_preset(cls, preset: CameraPreset, distance: float = 15.0) -> "ViewportCamera":
        """Return a standard camera from a named preset."""
        d = distance
        _PRESET_MAP = {
            CameraPreset.FRONT:      ((0, -d, 0),   (0, 0, 0), (0, 0, 1)),
            CameraPreset.BACK:       ((0,  d, 0),   (0, 0, 0), (0, 0, 1)),
            CameraPreset.LEFT:       ((-d, 0, 0),   (0, 0, 0), (0, 0, 1)),
            CameraPreset.RIGHT:      (( d, 0, 0),   (0, 0, 0), (0, 0, 1)),
            CameraPreset.TOP:        ((0, 0,  d),   (0, 0, 0), (0, 1, 0)),
            CameraPreset.BOTTOM:     ((0, 0, -d),   (0, 0, 0), (0, 1, 0)),
            CameraPreset.ISOMETRIC:  (( d, -d,  d*0.7), (0, 0, 0), (0, 0, 1)),
        }
        pos, tgt, up = _PRESET_MAP[preset]
        return cls(position=pos, target=tgt, up=up)


# ---------------------------------------------------------------------------
# Snap settings
# ---------------------------------------------------------------------------

@dataclass
class SnapSettings:
    """Grid and object snapping configuration."""
    enabled:        bool  = True
    grid_size:      float = 0.1     # metres per grid division
    angle_step_deg: float = 15.0    # rotation snap increment
    snap_to_grid:   bool  = True
    snap_to_vertex: bool  = False
    snap_to_edge:   bool  = False
    snap_to_face:   bool  = False
    snap_to_mesh:   bool  = True        # solution-mesh grid lines / intersections
    tolerance:      float = 0.25        # metres: how close the cursor must be to snap
    ortho:          bool  = False       # constrain to the dominant axis from the anchor point
    polar_step_deg: Optional[float] = None   # constrain the XY angle to multiples of this

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "grid_size": self.grid_size,
            "angle_step_deg": self.angle_step_deg,
            "snap_to_grid": self.snap_to_grid,
            "snap_to_vertex": self.snap_to_vertex,
            "snap_to_edge": self.snap_to_edge,
            "snap_to_face": self.snap_to_face,
            "snap_to_mesh": self.snap_to_mesh,
            "tolerance": self.tolerance,
            "ortho": self.ortho,
            "polar_step_deg": self.polar_step_deg,
        }


# ---------------------------------------------------------------------------
# Viewport state (mutable, owned by ViewportController)
# ---------------------------------------------------------------------------

@dataclass
class ViewportState:
    """
    Full mutable viewport configuration.

    This is the data contract between the backend and GUI.  A GUI reads this
    struct to configure its renderer; the backend updates it and emits events.
    """
    camera:         ViewportCamera          = field(default_factory=ViewportCamera)
    transform_mode: TransformMode           = TransformMode.SELECT
    snap:           SnapSettings            = field(default_factory=SnapSettings)
    visibility:     Dict[str, bool]         = field(default_factory=lambda: {
        f.name: True for f in VisibilityFlags
    })
    background_color: Tuple[int, int, int]  = (40, 40, 40)
    show_wireframe:   bool                  = False
    show_normals:     bool                  = False
    highlight_color:  Tuple[int, int, int]  = (255, 200, 0)
    clip_plane_z:     Optional[float]       = None   # horizontal section cut (m)

    def set_visibility(self, flag: VisibilityFlags, visible: bool) -> None:
        self.visibility[flag.name] = visible

    def is_visible(self, flag: VisibilityFlags) -> bool:
        return self.visibility.get(flag.name, True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "camera": self.camera.to_dict(),
            "transform_mode": self.transform_mode.name,
            "snap": self.snap.to_dict(),
            "visibility": dict(self.visibility),
            "background_color": list(self.background_color),
            "show_wireframe": self.show_wireframe,
            "show_normals": self.show_normals,
            "highlight_color": list(self.highlight_color),
            "clip_plane_z": self.clip_plane_z,
        }


# ---------------------------------------------------------------------------
# ViewportController — mutates ViewportState and emits events
# ---------------------------------------------------------------------------

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
