"""
PyFDS Core Layer
----------------
Foundation infrastructure: events, exceptions, state, configuration.
No FDS domain knowledge lives here — only pure infrastructure primitives.
"""
from .events import EventBus, EventType, Event, get_global_bus
from .exceptions import (
    FdsError, FdsValidationError, FdsExecutionError, FdsParseError,
    FdsSerializationError, FdsPluginError, FdsConfigError, FdsJobError,
    FdsNotFoundError, FdsTimeoutError, FdsBinaryError,
)
from .state import StateManager, StateSnapshot
from .config import FdsConfig, ConfigProfile, get_config

__all__ = [
    "EventBus", "EventType", "Event", "get_global_bus",
    "FdsError", "FdsValidationError", "FdsExecutionError", "FdsParseError",
    "FdsSerializationError", "FdsPluginError", "FdsConfigError", "FdsJobError",
    "FdsNotFoundError", "FdsTimeoutError", "FdsBinaryError",
    "StateManager", "StateSnapshot",
    "FdsConfig", "ConfigProfile", "get_config",
]
