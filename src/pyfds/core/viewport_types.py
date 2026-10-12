"""Viewport enums."""
from __future__ import annotations

from enum import Enum, auto


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
