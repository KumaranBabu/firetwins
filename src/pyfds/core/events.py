"""
PyFDS Event Bus
===============
Typed, thread-safe publish/subscribe message system.

Design contract for future GUI:
  A GUI widget subscribes by calling ``bus.subscribe(EventType.OBJECT_ADDED, my_callback)``.
  The backend emits events via ``bus.emit(EventType.OBJECT_ADDED, payload)``.
  The GUI never calls domain methods directly; it only reacts to events and
  dispatches user intents through the FdsApi controller.

Thread safety:
  Subscriber lists are protected by a threading.Lock.
  Callbacks are invoked synchronously on the emitting thread by default.
  Use ``defer=True`` on subscribe to queue callbacks onto a provided executor.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event taxonomy
# ---------------------------------------------------------------------------

class EventType(Enum):
    # ── Project / session lifecycle ─────────────────────────────────────────
    PROJECT_CREATED     = auto()
    PROJECT_LOADED      = auto()
    PROJECT_SAVED       = auto()
    PROJECT_CLOSED      = auto()
    PROJECT_DIRTY       = auto()       # unsaved changes exist
    PROJECT_CLEAN       = auto()       # changes saved / reverted
    UNITS_CHANGED       = auto()       # payload = "SI" | "EN"
    VIEWS_CHANGED       = auto()       # saved views, section box or selection history changed
    VISIBILITY_CHANGED  = auto()       # objects hidden / shown
    WRITE_PROTECTION_CHANGED = auto()  # payload = bool

    # ── Entity lifecycle ────────────────────────────────────────────────────
    OBJECT_ADDED        = auto()
    OBJECT_REMOVED      = auto()
    OBJECT_MODIFIED     = auto()       # property changed on any entity
    COLLECTION_CLEARED  = auto()       # e.g., all meshes removed

    # ── Command / history ───────────────────────────────────────────────────
    COMMAND_EXECUTED    = auto()
    UNDO_PERFORMED      = auto()
    REDO_PERFORMED      = auto()
    HISTORY_CLEARED     = auto()

    # ── Validation ──────────────────────────────────────────────────────────
    VALIDATION_STARTED  = auto()
    VALIDATION_PASSED   = auto()
    VALIDATION_FAILED   = auto()       # payload = List[str] errors

    # ── Simulation execution ────────────────────────────────────────────────
    JOB_QUEUED          = auto()
    JOB_STARTED         = auto()
    JOB_PROGRESS        = auto()       # payload = {"step": int, "time": float, "pct": float}
    JOB_COMPLETED       = auto()       # payload = Job
    JOB_FAILED          = auto()       # payload = Job + error
    JOB_CANCELLED       = auto()
    JOB_OUTPUT_LINE     = auto()       # payload = str (live stdout line)

    # ── Batch / parametric ──────────────────────────────────────────────────
    BATCH_STARTED       = auto()
    BATCH_VARIANT_DONE  = auto()
    BATCH_COMPLETED     = auto()

    # ── Results / post-processing ────────────────────────────────────────────
    RESULTS_INDEXED     = auto()
    RESULTS_LOADED      = auto()

    # ── Smokeview ───────────────────────────────────────────────────────────
    SMV_LAUNCHED        = auto()
    SMV_EXITED          = auto()
    SMV_SCRIPT_SAVED    = auto()

    # ── Plugin system ───────────────────────────────────────────────────────
    PLUGIN_LOADED       = auto()
    PLUGIN_UNLOADED     = auto()

    # ── Configuration ───────────────────────────────────────────────────────
    CONFIG_CHANGED      = auto()

    # ── Meshing ─────────────────────────────────────────────────────────────
    MESH_ENGINE_DETECTED     = auto()   # payload = List[EngineStatus]
    MESH_ENGINE_SELECTED     = auto()   # payload = {"engine": name, "capability": str}
    MESH_GENERATION_STARTED  = auto()   # payload = {"engine": name, "type": str}
    MESH_GENERATION_COMPLETED = auto()  # payload = {"engine": name, "n_blocks"/"type": ...}
    MESH_GENERATION_FAILED   = auto()   # payload = {"engine": name, "error": str}
    GEOMETRY_IMPORTED        = auto()   # payload = {"engine": name, "path": str}

    # ── Selection ───────────────────────────────────────────────────────────
    SELECTION_CHANGED   = auto()       # payload = SelectionChangedPayload
    SELECTION_CLEARED   = auto()       # payload = None

    # ── Viewport ────────────────────────────────────────────────────────────
    VIEWPORT_CHANGED         = auto()  # payload = ViewportState
    VIEWPORT_CAMERA_CHANGED  = auto()  # payload = ViewportCamera

    # ── Auto-fix / repair ───────────────────────────────────────────────────
    AUTO_FIX_APPLIED    = auto()       # payload = {"rule": str, "entity": str, "fix": str}

    # ── Entity lifecycle extras ──────────────────────────────────────────────
    ENTITY_DUPLICATED   = auto()       # payload = {"original": FdsEntity, "copy": FdsEntity}

    # ── Schema ──────────────────────────────────────────────────────────────
    SCHEMA_REGISTERED   = auto()       # payload = EntitySchema

    # ── Generic / extension ─────────────────────────────────────────────────
    CUSTOM              = auto()       # for plugin-defined events


# ---------------------------------------------------------------------------
# Event envelope
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """Immutable envelope carrying a typed payload through the bus."""
    type: EventType
    payload: Any = None
    source: Optional[str] = None          # e.g., "GeometryManager", "JobQueue"
    timestamp: float = field(default_factory=time.monotonic)

    def __repr__(self) -> str:
        src = f" from={self.source!r}" if self.source else ""
        return f"<Event type={self.type.name}{src} at t={self.timestamp:.3f}>"


# ---------------------------------------------------------------------------
# Subscription record
# ---------------------------------------------------------------------------

@dataclass
class _Subscription:
    id: int
    event_type: Optional[EventType]       # None = subscribe to all
    callback: Callable[[Event], None]
    defer: bool                           # True = push to thread-pool executor
    tags: Set[str]                        # optional filter tags


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

class EventBus:
    """
    Central publish/subscribe hub.

    Usage (backend)::

        bus = EventBus()
        bus.emit(EventType.OBJECT_ADDED, payload=mesh, source="GeometryManager")

    Usage (future GUI)::

        sub_id = bus.subscribe(EventType.OBJECT_ADDED, on_entity_added)
        # ... later ...
        bus.unsubscribe(sub_id)
    """

    def __init__(self, name: str = "default", max_workers: int = 4) -> None:
        self.name = name
        self._lock = threading.Lock()
        self._subs: List[_Subscription] = []
        self._counter = 0
        self._executor: Optional[ThreadPoolExecutor] = None
        self._max_workers = max_workers

    # ── Subscription management ─────────────────────────────────────────────

    def subscribe(
        self,
        event_type: Optional[EventType],
        callback: Callable[[Event], None],
        *,
        defer: bool = False,
        tags: Optional[Set[str]] = None,
    ) -> int:
        """
        Register ``callback`` to be invoked when ``event_type`` is emitted.

        Parameters
        ----------
        event_type:
            The event to listen for. Pass ``None`` to receive ALL events.
        callback:
            Callable accepting a single ``Event`` argument.
        defer:
            If True the callback is dispatched via an internal ThreadPoolExecutor
            (non-blocking). Use this for I/O-heavy GUI update callbacks.
        tags:
            Optional metadata tags for selective ``emit_tagged`` calls.

        Returns
        -------
        int
            Subscription ID; pass to :meth:`unsubscribe` to remove.
        """
        with self._lock:
            self._counter += 1
            sub = _Subscription(
                id=self._counter,
                event_type=event_type,
                callback=callback,
                defer=defer,
                tags=tags or set(),
            )
            self._subs.append(sub)
            if defer and self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=self._max_workers,
                    thread_name_prefix="pyfds-event-worker",
                )
        logger.debug("EventBus[%s] subscribed id=%d type=%s", self.name, sub.id,
                     event_type.name if event_type else "*")
        return sub.id

    def unsubscribe(self, sub_id: int) -> bool:
        """Remove subscription by ID. Returns True if found."""
        with self._lock:
            before = len(self._subs)
            self._subs = [s for s in self._subs if s.id != sub_id]
            removed = len(self._subs) < before
        logger.debug("EventBus[%s] unsubscribed id=%d removed=%s",
                     self.name, sub_id, removed)
        return removed

    def unsubscribe_all(self) -> None:
        """Remove every subscription. Useful for teardown in tests."""
        with self._lock:
            self._subs.clear()

    # ── Emission ────────────────────────────────────────────────────────────

    def emit(
        self,
        event_type: EventType,
        payload: Any = None,
        source: Optional[str] = None,
    ) -> None:
        """
        Emit an event to all matching subscribers.

        Parameters
        ----------
        event_type:
            The event category.
        payload:
            Arbitrary data; the contract between emitter and subscriber.
        source:
            Human-readable origin label (e.g. class name) for debugging.
        """
        event = Event(type=event_type, payload=payload, source=source)
        with self._lock:
            targets = [
                s for s in self._subs
                if s.event_type is None or s.event_type == event_type
            ]

        for sub in targets:
            try:
                if sub.defer and self._executor:
                    self._executor.submit(sub.callback, event)
                else:
                    sub.callback(event)
            except Exception as exc:
                logger.error(
                    "EventBus[%s] callback id=%d raised %s: %s",
                    self.name, sub.id, type(exc).__name__, exc,
                    exc_info=True,
                )

    def emit_event(self, event: Event) -> None:
        """Emit a pre-constructed Event envelope (useful for replay/logging)."""
        self.emit(event.type, payload=event.payload, source=event.source)

    # ── Context manager support ──────────────────────────────────────────────

    def __enter__(self) -> "EventBus":
        return self

    def __exit__(self, *_) -> None:
        self.shutdown()

    def shutdown(self) -> None:
        """Shut down the deferred executor. Call during application teardown."""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

    # ── Diagnostics ──────────────────────────────────────────────────────────

    @property
    def subscription_count(self) -> int:
        with self._lock:
            return len(self._subs)

    def subscriptions_for(self, event_type: EventType) -> int:
        """Return the number of active subscriptions for a given event type."""
        with self._lock:
            return sum(
                1 for s in self._subs
                if s.event_type is None or s.event_type == event_type
            )

    def __repr__(self) -> str:
        return f"<EventBus name={self.name!r} subs={self.subscription_count}>"


# ---------------------------------------------------------------------------
# Module-level global bus (singleton convenience)
# ---------------------------------------------------------------------------

_global_bus: Optional[EventBus] = None
_global_lock = threading.Lock()


def get_global_bus() -> EventBus:
    """Return (or lazily create) the process-wide default EventBus."""
    global _global_bus
    if _global_bus is None:
        with _global_lock:
            if _global_bus is None:
                _global_bus = EventBus(name="global")
    return _global_bus


def reset_global_bus() -> None:
    """Replace the global bus with a fresh instance. Useful in tests."""
    global _global_bus
    with _global_lock:
        if _global_bus:
            _global_bus.shutdown()
        _global_bus = EventBus(name="global")
