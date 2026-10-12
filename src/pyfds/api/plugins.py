"""Plugin management.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, TYPE_CHECKING


if TYPE_CHECKING:
    from .facade import FdsApi

logger = logging.getLogger(__name__)


class PluginManager:
    """Load and query plugins."""

    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    def load_directory(self, directory: str, *, recursive: bool = False) -> int:
        from pyfds.plugins.loader import PluginLoader
        return PluginLoader().load_directory(directory, recursive=recursive)

    def load_entry_points(self) -> int:
        from pyfds.plugins.loader import PluginLoader
        return PluginLoader().load_entry_points()

    def register(self, plugin: Any) -> None:
        from pyfds.plugins.loader import get_registry
        get_registry().register(plugin)

    def all_plugins(self) -> List[Any]:
        from pyfds.plugins.loader import get_registry
        return get_registry().all_plugins()

    def get(self, name: str) -> Optional[Any]:
        from pyfds.plugins.loader import get_registry
        return get_registry().get(name)
