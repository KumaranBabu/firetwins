"""``api.config`` — the active ``FdsConfig`` plus a project-aware ``configure_simulation``."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .facade import FdsApi


class ApiConfigProxy:
    """Wraps FdsConfig, adding project-aware configure_simulation() shim."""
    __slots__ = ("_api", "_cfg")

    def __init__(self, api: "FdsApi", cfg) -> None:
        object.__setattr__(self, "_api", api)
        object.__setattr__(self, "_cfg", cfg)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_cfg"), name)

    def configure_simulation(self, t_end=None, t_begin=None, **kwargs):
        """Set simulation parameters as ONE undoable step (a failure rolls all back)."""
        from pyfds.automation.commands import GroupCommand, ModifyPropertyCommand
        api = object.__getattribute__(self, "_api")
        params = api.project.params
        changes = {}
        if t_end is not None:
            changes["t_end"] = float(t_end)
        if t_begin is not None:
            changes["t_begin"] = float(t_begin)
        changes.update({k: v for k, v in kwargs.items() if hasattr(params, k)})
        if not changes:
            return
        result = api.history.execute(GroupCommand(
            [ModifyPropertyCommand(params, k, v) for k, v in changes.items()],
            label="configure simulation (" + ", ".join(changes) + ")",
        ))
        if not result.success:
            raise ValueError(result.message)
