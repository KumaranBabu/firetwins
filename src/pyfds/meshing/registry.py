"""
PyFDS Meshing Engine Registry
==============================
Discovers, probes, and selects meshing engines at runtime.

Detection
---------
Engines are probed once and results cached in memory.  Call
``detect_all(force=True)`` to re-probe after installing new tools.

Selection priority
------------------
For a given capability the registry selects the best available engine:

  1. Explicit ``preferred_name`` argument to ``get_engine()``
  2. Per-capability user preference set via ``set_preferred()``
  3. Highest-priority available engine; commercial engines rank above
     open-source engines at equal priority

Extension
---------
Register additional engine classes with ``register()`` or
``register_many()``.  Third-party packages may also contribute engines
via a ``MeshingPlugin`` (see ``pyfds.plugins.base``).
"""
from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional, Type

from .base import EngineCapabilities, EngineStatus, LicenseType, MeshingEngineBase

logger = logging.getLogger(__name__)

_CAPABILITY_FIELDS = [
    "structured_mesh", "surface_mesh", "volume_mesh",
    "geometry_import", "mesh_refinement", "mesh_optimization",
    "boundary_layers", "parallel",
]


class EngineRegistry:
    """
    Central registry for meshing engine *classes*.

    Maintains:
    - Ordered list of registered engine classes.
    - Detection cache (``EngineStatus`` per engine).
    - Singleton engine instances (created lazily on first use).
    - Per-capability user preferences.
    """

    def __init__(self) -> None:
        self._lock      = threading.Lock()
        self._classes:   List[Type[MeshingEngineBase]] = []
        self._detection: Dict[str, EngineStatus] = {}
        self._instances: Dict[str, MeshingEngineBase] = {}
        self._preferred: Dict[str, str] = {}   # capability -> engine name

    # ── Registration ─────────────────────────────────────────────────────────

    def register(self, engine_class: Type[MeshingEngineBase]) -> None:
        """Add *engine_class* to the registry.  Idempotent — duplicate names are skipped."""
        with self._lock:
            if any(c.name == engine_class.name for c in self._classes):
                logger.debug("EngineRegistry: %r already registered — skipping",
                             engine_class.name)
                return
            self._classes.append(engine_class)
        logger.debug("EngineRegistry: registered %r (priority=%d)",
                     engine_class.name, engine_class.priority)

    def register_many(self, *engine_classes: Type[MeshingEngineBase]) -> None:
        for cls in engine_classes:
            self.register(cls)

    def unregister(self, name: str) -> bool:
        """Remove an engine class by name.  Returns True if it existed."""
        with self._lock:
            before = len(self._classes)
            self._classes = [c for c in self._classes if c.name != name]
            self._detection.pop(name, None)
            self._instances.pop(name, None)
        return len(self._classes) < before

    # ── Detection ─────────────────────────────────────────────────────────────

    def detect_all(self, force: bool = False) -> List[EngineStatus]:
        """
        Probe every registered engine class.

        Returns a list of ``EngineStatus`` sorted by (available, priority)
        descending — so the best candidates appear first.

        Parameters
        ----------
        force:
            Re-probe even when a cached result exists.
        """
        with self._lock:
            classes = list(self._classes)

        statuses: List[EngineStatus] = []
        for cls in classes:
            if cls.name in self._detection and not force:
                statuses.append(self._detection[cls.name])
                continue

            available, version, error = False, None, None
            try:
                available = cls.is_available()
                if available:
                    version = cls.get_version()
            except Exception as exc:
                error = str(exc)
                logger.warning("EngineRegistry: detection error for %r: %s", cls.name, exc)

            status = EngineStatus(
                name=cls.name,
                display_name=cls.display_name,
                available=available,
                version=version,
                priority=cls.priority,
                license_type=cls.license_type,
                capabilities=cls.capabilities,
                error=error,
            )
            with self._lock:
                self._detection[cls.name] = status
            statuses.append(status)
            logger.debug("EngineRegistry: %r available=%s version=%s",
                         cls.name, available, version)

        statuses.sort(key=lambda s: (s.available, s.priority), reverse=True)
        return statuses

    def status(self, engine_name: str) -> Optional[EngineStatus]:
        """Return cached ``EngineStatus`` for *engine_name*, or None if not yet detected."""
        return self._detection.get(engine_name)

    # ── Selection ─────────────────────────────────────────────────────────────

    def get_engine(
        self,
        capability: str,
        preferred_name: Optional[str] = None,
    ) -> Optional[MeshingEngineBase]:
        """
        Return the best available engine for *capability*.

        Selection order:
          1. ``preferred_name`` argument (if given and available)
          2. Per-capability preference set via ``set_preferred()``
          3. Highest-priority available engine (commercial first)

        Returns None only when no engine supports the capability.
        """
        name = preferred_name or self._preferred.get(capability)
        if name:
            engine = self._instantiate(name)
            if engine is not None:
                return engine
            logger.warning(
                "EngineRegistry: preferred engine %r unavailable for %r — falling back",
                name, capability,
            )

        candidates = self._candidates_for(capability)
        if not candidates:
            return None
        return self._instantiate(candidates[0].name)

    def _candidates_for(self, capability: str) -> List[Type[MeshingEngineBase]]:
        """Return available engine classes that support *capability*, best-first."""
        if capability not in _CAPABILITY_FIELDS:
            logger.warning("EngineRegistry: unknown capability %r", capability)
            return []

        with self._lock:
            classes = list(self._classes)

        results: List[Type[MeshingEngineBase]] = []
        for cls in classes:
            if not getattr(cls.capabilities, capability, False):
                continue
            cached = self._detection.get(cls.name)
            if cached is not None:
                available = cached.available
            else:
                try:
                    available = cls.is_available()
                except Exception:
                    available = False
                with self._lock:
                    self._detection[cls.name] = EngineStatus(
                        name=cls.name,
                        display_name=cls.display_name,
                        available=available,
                        version=None,
                        priority=cls.priority,
                        license_type=cls.license_type,
                        capabilities=cls.capabilities,
                    )
            if available:
                results.append(cls)

        # Commercial engines rank first at equal priority
        results.sort(
            key=lambda c: (c.license_type == LicenseType.COMMERCIAL, c.priority),
            reverse=True,
        )
        return results

    def _instantiate(self, name: str) -> Optional[MeshingEngineBase]:
        """Return (or lazily create) the singleton instance for *name*."""
        with self._lock:
            if name in self._instances:
                return self._instances[name]
            cls = next((c for c in self._classes if c.name == name), None)

        if cls is None:
            logger.warning("EngineRegistry: engine %r not registered", name)
            return None
        try:
            if not cls.is_available():
                return None
            instance = cls()
            with self._lock:
                self._instances[name] = instance
            return instance
        except Exception as exc:
            logger.error("EngineRegistry: could not instantiate %r: %s", name, exc)
            return None

    # ── User preferences ──────────────────────────────────────────────────────

    def set_preferred(self, capability: str, engine_name: str) -> None:
        """Pin *engine_name* for *capability*.  Pass '' to clear."""
        if engine_name:
            self._preferred[capability] = engine_name
        else:
            self._preferred.pop(capability, None)

    def get_preferred(self, capability: str) -> Optional[str]:
        return self._preferred.get(capability)

    # ── Query helpers ─────────────────────────────────────────────────────────

    def available_engines(self) -> List[EngineStatus]:
        """Return status records for all engines currently available."""
        return [s for s in self._detection.values() if s.available]

    def all_registered_names(self) -> List[str]:
        with self._lock:
            return [c.name for c in self._classes]

    def __len__(self) -> int:
        with self._lock:
            return len(self._classes)

    def __repr__(self) -> str:
        return f"<EngineRegistry engines={self.all_registered_names()}>"


# ---------------------------------------------------------------------------
# Module-level global registry singleton
# ---------------------------------------------------------------------------

_global_registry: Optional[EngineRegistry] = None
_global_lock = threading.Lock()


def get_engine_registry() -> EngineRegistry:
    """Return (or lazily create) the process-wide engine registry."""
    global _global_registry
    if _global_registry is None:
        with _global_lock:
            if _global_registry is None:
                _global_registry = _build_default_registry()
    return _global_registry


def reset_engine_registry() -> None:
    """Replace the global registry with a fresh default.  Useful in tests."""
    global _global_registry
    with _global_lock:
        _global_registry = _build_default_registry()


def _build_default_registry() -> EngineRegistry:
    """Populate a fresh registry with all built-in engine classes."""
    from .engines.builtin import BuiltinStructuredEngine
    from .engines.gmsh_engine import GmshEngine
    from .engines.tetgen_engine import TetGenEngine
    from .engines.netgen_engine import NetgenEngine

    registry = EngineRegistry()
    registry.register_many(
        GmshEngine,               # priority 70 — full-featured, widely available
        NetgenEngine,             # priority 60 — good quality, LGPL
        TetGenEngine,             # priority 50 — tet-only via binary, dual license
        BuiltinStructuredEngine,  # priority 10 — always available, structured only
    )
    return registry
