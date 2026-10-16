"""Viewport camera, snap settings and view state."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from .viewport_types import (
    CameraPreset,
    ProjectionMode,
    TransformMode,
    VisibilityFlags,
)


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


#: Layers that start hidden: the reference grid and the device name labels (axes, meshes ... start visible).
_OFF_BY_DEFAULT = {"GRID", "LABELS"}


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
        f.name: f.name not in _OFF_BY_DEFAULT for f in VisibilityFlags
    })
    background_color: Tuple[int, int, int]  = (40, 40, 40)
    show_wireframe:   bool                  = False
    render_mode:      str                   = "solid"      # wireframe | solid | outlines | realistic
    mesh_display:     str                   = "outline"    # hidden | outline | lines | boundary
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
            "render_mode": self.render_mode,
            "mesh_display": self.mesh_display,
            "show_normals": self.show_normals,
            "highlight_color": list(self.highlight_color),
            "clip_plane_z": self.clip_plane_z,
        }
