"""
Tool registry — the single source of truth for agent-callable operations.

Every ``ToolSpec.handler`` does nothing but call an ``FdsApi`` manager
method. There is no direct domain/model mutation here: the agent is bound
by the exact same rules (undo/redo, validation, EventBus notifications) as
a human clicking a GUI button.

The tool definitions live in ``pyfds.agent.tools.<area>`` (one module per
area); this module only assembles them in a stable order.
"""
from __future__ import annotations

from typing import List

from .tools.base import ToolSpec, _find_entity_by_name, _remove_from  # noqa: F401
from .tools import modeling, devices, materials, output, hvac, environment, organization, engineering, project, entities, advanced, mesh, building, physics, library, editing, results_scene, results_viewer, importing, systems  # noqa: E402

TOOL_REGISTRY: List[ToolSpec] = [
    *modeling.TOOLS,
    *devices.TOOLS,
    *materials.TOOLS,
    *output.TOOLS,
    *hvac.TOOLS,
    *environment.TOOLS,
    *organization.TOOLS,
    *engineering.TOOLS,
    *project.TOOLS,
    *entities.TOOLS,
    *advanced.TOOLS,
    *mesh.TOOLS,
    *building.TOOLS,
    *physics.TOOLS,
    *library.TOOLS,
    *editing.TOOLS,
    *results_scene.TOOLS,
    *results_viewer.TOOLS,
    *importing.TOOLS,
    *systems.TOOLS,
]

_BY_NAME = {t.name: t for t in TOOL_REGISTRY}
if len(_BY_NAME) != len(TOOL_REGISTRY):       # fail loudly on a copy-paste duplicate
    _seen: set = set()
    _dupes = sorted({t.name for t in TOOL_REGISTRY if t.name in _seen or _seen.add(t.name)})
    raise RuntimeError(f"duplicate agent tool names: {_dupes}")


def get_tool(name: str) -> ToolSpec:
    try:
        return _BY_NAME[name]
    except KeyError:
        raise KeyError(f"Unknown tool {name!r}") from None
