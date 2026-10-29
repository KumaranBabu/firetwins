"""
PyFDS Plugin Loader & Registry
================================
Discovers, loads, and manages PyFDS plugins from three sources:

  1. **Directory scan** — Python ``.py`` files and packages in a given
     directory that expose a ``PYFDS_PLUGIN = True`` module-level flag
     and a ``register(registry)`` callable.

  2. **Entry points** — Packages installed via pip that declare the
     ``pyfds.plugins`` entry-points group (standard Python packaging).
     Each entry point must resolve to a class or instance with a
     ``metadata`` attribute (``PluginMetadata``).

  3. **Manual registration** — Programmatic ``registry.register(plugin)``
     calls from scripts or the public API.

Thread safety
-------------
The registry uses a ``threading.Lock`` for all mutations.  Reads are
lock-free (snapshot copy).

EventBus integration
--------------------
``PLUGIN_LOADED`` and ``PLUGIN_UNLOADED`` events are emitted through the
global EventBus whenever a plugin's registration state changes.

Example::

    from pyfds.plugins.loader import PluginLoader, get_registry

    # Load everything from a custom directory
    loader = PluginLoader()
    loader.load_directory("/path/to/my/plugins")

    # Auto-discover entry-point plugins from installed packages
    loader.load_entry_points()

    # Query
    registry = get_registry()
    print(registry.all_plugins())
    val_rules = registry.get_validation_rules()
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from .base import (
    PluginBase, PluginMetadata,
    ValidationPlugin, WriterPlugin, ParserPlugin,
    WorkflowPlugin, PresetPlugin, ResultPlugin,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PluginRegistry
# ---------------------------------------------------------------------------

class PluginRegistry:
    """
    Central store for all registered plugin instances.

    Plugins are stored by their ``metadata.name``.  Registering a plugin
    with an existing name replaces the previous registration (with a warning).
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._plugins: Dict[str, Any] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, plugin: Any) -> None:
        """
        Register *plugin* in the registry.

        *plugin* must have a ``metadata`` attribute (``PluginMetadata``),
        or at least a ``name`` attribute.
        """
        meta = getattr(plugin, "metadata", None)
        name = (meta.name if meta else None) or getattr(plugin, "name", None)
        if not name:
            raise ValueError(f"Plugin {plugin!r} has no name or metadata")

        with self._lock:
            if name in self._plugins:
                logger.warning("PluginRegistry: replacing existing plugin %r", name)
            self._plugins[name] = plugin

        # Invoke optional on_load hook
        if hasattr(plugin, "on_load"):
            try:
                plugin.on_load(self)
            except Exception as exc:
                logger.error("PluginRegistry: on_load error for %r: %s", name, exc)

        self._emit("PLUGIN_LOADED", plugin)
        logger.info("PluginRegistry: registered plugin %r", name)

    def unregister(self, name: str) -> bool:
        """Remove a plugin by name. Returns True if it existed."""
        with self._lock:
            plugin = self._plugins.pop(name, None)
        if plugin is None:
            return False
        if hasattr(plugin, "on_unload"):
            try:
                plugin.on_unload(self)
            except Exception as exc:
                logger.error("PluginRegistry: on_unload error for %r: %s", name, exc)
        self._emit("PLUGIN_UNLOADED", plugin)
        logger.info("PluginRegistry: unregistered plugin %r", name)
        return True

    # ── Query ─────────────────────────────────────────────────────────────────

    def all_plugins(self) -> List[Any]:
        with self._lock:
            return list(self._plugins.values())

    def get(self, name: str) -> Optional[Any]:
        with self._lock:
            return self._plugins.get(name)

    def get_by_type(self, plugin_type) -> List[Any]:
        """Return all plugins that are instances of (or compatible with) *plugin_type*."""
        with self._lock:
            plugins = list(self._plugins.values())
        return [p for p in plugins if isinstance(p, plugin_type)]

    # ── Aggregate helpers (used by core systems) ──────────────────────────────

    def get_validation_rules(self) -> List[Any]:
        """Collect all validation rules contributed by ``ValidationPlugin`` instances."""
        rules: List[Any] = []
        for plugin in self.get_by_type(ValidationPlugin):
            try:
                rules.extend(plugin.validation_rules())
            except Exception as exc:
                logger.error("PluginRegistry: validation_rules error in %r: %s",
                             getattr(plugin, "name", "?"), exc)
        return rules

    def get_writer_plugins(self) -> List[Any]:
        return self.get_by_type(WriterPlugin)

    def get_parser_plugins(self) -> List[Any]:
        return self.get_by_type(ParserPlugin)

    def get_workflow_steps(self) -> List[Any]:
        steps: List[Any] = []
        for plugin in self.get_by_type(WorkflowPlugin):
            try:
                steps.extend(plugin.workflow_steps())
            except Exception as exc:
                logger.error("PluginRegistry: workflow_steps error: %s", exc)
        return steps

    def get_scenario_templates(self) -> List[Any]:
        templates: List[Any] = []
        for plugin in self.get_by_type(PresetPlugin):
            try:
                templates.extend(plugin.scenario_templates())
            except Exception as exc:
                logger.error("PluginRegistry: scenario_templates error: %s", exc)
        return templates

    def get_result_plugins(self) -> List[Any]:
        return self.get_by_type(ResultPlugin)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _emit(self, event_name: str, payload: Any) -> None:
        try:
            from pyfds.core.events import get_global_bus, EventType
            etype = getattr(EventType, event_name, None)
            if etype:
                get_global_bus().emit(etype, payload, source="PluginRegistry")
        except Exception:
            pass

    def __len__(self) -> int:
        with self._lock:
            return len(self._plugins)

    def __repr__(self) -> str:
        return f"<PluginRegistry plugins={list(self._plugins.keys())}>"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_global_registry: Optional[PluginRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> PluginRegistry:
    """Return the process-wide plugin registry (created on first call)."""
    global _global_registry
    if _global_registry is None:
        with _registry_lock:
            if _global_registry is None:
                _global_registry = PluginRegistry()
    return _global_registry


# ---------------------------------------------------------------------------
# PluginLoader
# ---------------------------------------------------------------------------

class PluginLoader:
    """
    Discovers and registers plugins from directories and entry points.

    All successfully loaded plugins are registered in the provided (or global)
    registry automatically.

    Parameters
    ----------
    registry : PluginRegistry, optional
        Target registry. Defaults to the global singleton.
    """

    def __init__(self, registry: Optional[PluginRegistry] = None) -> None:
        self._registry = registry if registry is not None else get_registry()

    # ── Directory loading ─────────────────────────────────────────────────────

    def load_directory(self, directory: str, *, recursive: bool = False) -> int:
        """
        Scan *directory* for Python plugin files/packages and load them.

        A valid plugin module must:
          - Set ``PYFDS_PLUGIN = True`` at module level.
          - Define a ``register(registry)`` callable OR expose a class/instance
            with a ``metadata`` attribute.

        Parameters
        ----------
        directory : str
            Directory to scan.
        recursive : bool
            If True, also scan sub-directories.

        Returns
        -------
        int
            Number of plugins successfully loaded.
        """
        dir_path = Path(directory)
        if not dir_path.is_dir():
            logger.warning("PluginLoader: directory not found: %s", directory)
            return 0

        count = 0
        pattern = "**/*.py" if recursive else "*.py"
        for py_file in sorted(dir_path.glob(pattern)):
            if py_file.name.startswith("_"):
                continue
            if self._load_file(py_file):
                count += 1

        # Also check sub-packages (directories with __init__.py)
        init_pattern = "**/__init__.py" if recursive else "*/__init__.py"
        for init_file in sorted(dir_path.glob(init_pattern)):
            pkg_dir = init_file.parent
            if self._load_package(pkg_dir):
                count += 1

        logger.info("PluginLoader: loaded %d plugins from %s", count, directory)
        return count

    def _load_file(self, py_file: Path) -> bool:
        """Import a single .py file as a plugin module. Return True on success."""
        module_name = f"_pyfds_plugin_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                return False
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            if not getattr(module, "PYFDS_PLUGIN", False):
                return False   # not flagged as a plugin

            # Try register() function first
            if hasattr(module, "register") and callable(module.register):
                module.register(self._registry)
                return True

            # Fall back: look for any class with PluginMetadata
            for attr_name in dir(module):
                obj = getattr(module, attr_name, None)
                if obj is None:
                    continue
                if isinstance(obj, type) and issubclass(obj, PluginBase) and obj is not PluginBase:
                    self._registry.register(obj())
                    return True
                if isinstance(obj, PluginBase):
                    self._registry.register(obj)
                    return True

        except Exception as exc:
            logger.error("PluginLoader: failed to load %s: %s", py_file, exc)
        return False

    def _load_package(self, pkg_dir: Path) -> bool:
        """Import a plugin package (directory with __init__.py)."""
        init_file   = pkg_dir / "__init__.py"
        if not init_file.exists():
            return False
        return self._load_file(init_file)

    # ── Entry-point loading ───────────────────────────────────────────────────

    def load_entry_points(self, group: str = "pyfds.plugins") -> int:
        """
        Discover and register all plugins advertised via Python entry points
        in the ``pyfds.plugins`` group.

        Compatible with both ``importlib.metadata`` (Python 3.9+) and
        the ``pkg_resources`` fallback.

        Returns
        -------
        int
            Number of plugins loaded.
        """
        count = 0
        eps = self._discover_entry_points(group)
        for ep in eps:
            try:
                plugin_class_or_instance = ep.load()
                if isinstance(plugin_class_or_instance, type):
                    plugin = plugin_class_or_instance()
                else:
                    plugin = plugin_class_or_instance
                self._registry.register(plugin)
                count += 1
                logger.info("PluginLoader: entry-point plugin loaded: %s", ep.name)
            except Exception as exc:
                logger.error("PluginLoader: entry-point %s failed: %s", ep.name, exc)

        logger.info("PluginLoader: %d entry-point plugins loaded from group %r", count, group)
        return count

    @staticmethod
    def _discover_entry_points(group: str) -> list:
        """Return entry points for *group* using importlib.metadata or pkg_resources."""
        try:
            from importlib.metadata import entry_points
            # Python 3.12+ uses select(); 3.9-3.11 may use group keyword or dict access
            eps = entry_points()
            if hasattr(eps, "select"):
                return list(eps.select(group=group))
            return list(eps.get(group, []))
        except Exception:
            pass
        try:
            import pkg_resources
            return list(pkg_resources.iter_entry_points(group))
        except Exception:
            pass
        return []

    # ── Manual convenience ────────────────────────────────────────────────────

    def register(self, plugin: Any) -> None:
        """Manually register a plugin instance."""
        self._registry.register(plugin)

    def load_class(self, plugin_class: Type, *args, **kwargs) -> None:
        """Instantiate *plugin_class* with given args and register it."""
        self._registry.register(plugin_class(*args, **kwargs))
