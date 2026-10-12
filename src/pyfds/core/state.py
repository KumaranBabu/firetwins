"""
PyFDS State Manager
===================
Provides immutable point-in-time snapshots of the project graph and a
``StateManager`` that tracks the current snapshot and notifies subscribers
on every change.

GUI contract:
  The future GUI subscribes to ``StateManager.on_change`` callbacks.
  It receives a ``StateSnapshot`` which is a serializable dict — no Pydantic
  models, no FDS domain objects — safe to pass across thread boundaries or
  serialize to JSON for view-model rendering.
"""
from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Snapshot: immutable, serializable view of project state
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StateSnapshot:
    """
    Immutable, JSON-serializable summary of the current project state.

    All values are plain Python types (str, int, float, bool, list, dict).
    This is the primary data contract between the backend and any future GUI.
    """
    timestamp: float
    project_id: str
    chid: str
    title: str
    filepath: Optional[str]
    is_dirty: bool
    t_end: float
    t_begin: float
    mesh_count: int
    obstruction_count: int
    surface_count: int
    vent_count: int
    device_count: int
    material_count: int
    reaction_count: int
    slice_count: int
    boundary_count: int
    isosurface_count: int
    hvac_node_count: int
    hvac_duct_count: int
    validation_errors: List[str]
    extra: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict for JSON serialization or GUI view-models."""
        return {
            "timestamp": self.timestamp,
            "project_id": self.project_id,
            "chid": self.chid,
            "title": self.title,
            "filepath": self.filepath,
            "is_dirty": self.is_dirty,
            "simulation": {
                "t_begin": self.t_begin,
                "t_end": self.t_end,
            },
            "entity_counts": {
                "meshes": self.mesh_count,
                "obstructions": self.obstruction_count,
                "surfaces": self.surface_count,
                "vents": self.vent_count,
                "devices": self.device_count,
                "materials": self.material_count,
                "reactions": self.reaction_count,
                "slices": self.slice_count,
                "boundaries": self.boundary_count,
                "isosurfaces": self.isosurface_count,
                "hvac_nodes": self.hvac_node_count,
                "hvac_ducts": self.hvac_duct_count,
            },
            "validation_errors": list(self.validation_errors),
            "extra": copy.deepcopy(self.extra),
        }


# ---------------------------------------------------------------------------
# State factory
# ---------------------------------------------------------------------------

def build_snapshot(
    project: Any,
    *,
    filepath: Optional[str] = None,
    is_dirty: bool = False,
    validation_errors: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> StateSnapshot:
    """
    Build a ``StateSnapshot`` from a live ``FdsProject``.

    The project object is only read here; the snapshot holds primitives.
    """
    return StateSnapshot(
        timestamp=time.monotonic(),
        project_id=getattr(project, "_project_id", ""),
        chid=getattr(project, "chid", "pyfds"),
        title=getattr(project, "title", ""),
        filepath=filepath,
        is_dirty=is_dirty,
        t_begin=project.params.t_begin,
        t_end=project.params.t_end,
        mesh_count=len(project.meshes),
        obstruction_count=len(project.obstructions),
        surface_count=len(project.surfaces),
        vent_count=len(project.vents),
        device_count=len(project.devices),
        material_count=len(project.materials),
        reaction_count=len(project.reactions),
        slice_count=len(project.slices),
        boundary_count=len(project.bndfs),
        isosurface_count=len(project.isofs),
        hvac_node_count=len(project.hvac_nodes),
        hvac_duct_count=len(project.hvac_ducts),
        validation_errors=list(validation_errors or []),
        extra=extra or {},
    )


# ---------------------------------------------------------------------------
# StateManager
# ---------------------------------------------------------------------------

class StateManager:
    """
    Tracks the most recent ``StateSnapshot`` and notifies registered
    callbacks whenever the state transitions.

    Thread safety:
        Snapshot replacement is atomic (Python object reference assignment).
        Subscriber lists are protected by a list copy-on-read pattern.

    GUI contract:
        ``manager.on_change(callback)`` is the attachment point for GUI views.
        The callback receives the new ``StateSnapshot`` and must not block.
    """

    def __init__(self) -> None:
        self._snapshot: Optional[StateSnapshot] = None
        self._listeners: List[Callable[[StateSnapshot], None]] = []
        self._history: List[StateSnapshot] = []
        self._max_history: int = 100

    # ── Public API ───────────────────────────────────────────────────────────

    def update(self, snapshot: StateSnapshot) -> None:
        """Store a new snapshot and notify all registered listeners."""
        self._snapshot = snapshot
        self._history.append(snapshot)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        self._notify(snapshot)

    @property
    def current(self) -> Optional[StateSnapshot]:
        """The most recent snapshot, or None if no project is open."""
        return self._snapshot

    def on_change(self, callback: Callable[[StateSnapshot], None]) -> None:
        """
        Register a callback invoked on every state transition.

        Parameters
        ----------
        callback:
            Callable receiving a single ``StateSnapshot`` argument.
            Must be non-blocking. For heavy GUI work use ``defer=True``
            on the EventBus subscription instead.
        """
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[StateSnapshot], None]) -> None:
        """Deregister a previously registered callback."""
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def history(self, limit: int = 10) -> List[StateSnapshot]:
        """Return the last *limit* snapshots, newest first."""
        return list(reversed(self._history[-limit:]))

    def clear(self) -> None:
        """Reset state (e.g., when a session closes)."""
        self._snapshot = None
        self._history.clear()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _notify(self, snapshot: StateSnapshot) -> None:
        for listener in list(self._listeners):
            try:
                listener(snapshot)
            except Exception as exc:
                logger.error("StateManager listener raised %s: %s",
                             type(exc).__name__, exc, exc_info=True)
