"""Shared pieces for the agent tool modules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]
    mutates: bool = True


def _remove_from(manager, entity_id: str) -> None:
    entity = manager.get(entity_id)
    if entity is None:
        raise KeyError(f"{entity_id!r} not found")
    manager.remove(entity)


def _find_entity_by_name(api, name: str) -> Any:
    for entity in api.project.all_entities:
        if getattr(entity, "name", None) == name:
            return entity
    raise KeyError(f"No entity named {name!r} found in the project.")


def _configure_simulation_params(api, t_end, t_begin=0.0, dt=None, restrict_time_step=True) -> None:
    # Three separate undo-able commands rather than one bulk mutation —
    # api.set_timing()/set_property() are the existing undo-able primitives
    # for &TIME fields; there's no single command that covers all of them
    # at once, and SimulationParams (unlike FdsEntity subclasses) isn't
    # itself observer/undo-aware.
    api.set_timing(t_end=t_end, t_begin=t_begin)
    api.set_property(api.project.params, "dt", dt)
    api.set_property(api.project.params, "restrict_time_step", bool(restrict_time_step))
