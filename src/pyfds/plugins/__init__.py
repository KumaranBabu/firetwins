"""PyFDS Plugin Architecture — base interfaces, registry, and loader."""
from .base import (
    PluginBase,
    WriterPlugin,
    ValidationPlugin,
    ParserPlugin,
    WorkflowPlugin,
    PresetPlugin,
    ResultPlugin,
    PluginMetadata,
)
from .loader import PluginLoader, PluginRegistry, get_registry

__all__ = [
    "PluginBase",
    "WriterPlugin", "ValidationPlugin", "ParserPlugin",
    "WorkflowPlugin", "PresetPlugin", "ResultPlugin",
    "PluginMetadata",
    "PluginLoader", "PluginRegistry", "get_registry",
]
