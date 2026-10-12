"""
Dispatcher — binds ``TOOL_REGISTRY`` to a live ``FdsApi`` instance and
renders it into the Anthropic Messages API tool-use format
(``input_schema``) the embedded desktop-app agent loop uses.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable, Dict, List, Optional, Sequence

from .registry import TOOL_REGISTRY, get_tool


def _serialize(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple, set)):
        return [_serialize(o) for o in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serialize(v) for k, v in dataclasses.asdict(obj).items()}
    return str(obj)


#: Mutating tools that must NOT be wrapped in a transaction: history
#: navigation cannot run inside one, and applying a template replaces the whole
#: project (a document-level operation, not an undoable edit).
NON_TRANSACTIONAL_TOOLS = frozenset({"undo", "redo", "apply_template"})


class AgentToolDispatcher:
    """Wraps an ``FdsApi`` instance; the agent's only door into the backend.

    Every mutating tool call runs inside ``api.transaction(..., actor="agent")``
    so it is attributed to the agent, is atomic (a failure leaves no partial
    change) and is ONE undo step. :meth:`run_plan` extends that to a whole
    multi-step task.

    ``approver`` (optional) is called as ``approver(tool_names, arguments)``
    before anything mutating runs; returning False raises ``PermissionError``.
    """

    def __init__(self, api: Any, approver: Optional[Callable[[List[str], Any], bool]] = None) -> None:
        self.api = api
        self.approver = approver

    def anthropic_tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in TOOL_REGISTRY
        ]

    def call(self, name: str, arguments: Dict[str, Any] | None = None) -> Any:
        """Invoke a tool by name with keyword *arguments*; returns a JSON-safe result."""
        spec = get_tool(name)
        if spec.mutates and name not in NON_TRANSACTIONAL_TOOLS:
            self._approve([name], arguments)
            with self.api.transaction(f"agent: {name}", actor="agent"):
                result = spec.handler(self.api, **(arguments or {}))
        else:
            result = spec.handler(self.api, **(arguments or {}))
        return _serialize(result)

    def run_plan(self, steps: Sequence[Dict[str, Any]], label: str = "agent plan") -> List[Any]:
        """Run several tool calls as ONE atomic, undoable task.

        ``steps`` is a list of ``{"name": ..., "arguments": {...}}``. All tool
        names are validated (and the approver consulted) before anything runs.
        If any step fails, every earlier step is rolled back and the error
        propagates; on success a single undo reverts the whole plan.
        """
        specs = []
        for step in steps:
            spec = get_tool(step["name"])
            if spec.name in NON_TRANSACTIONAL_TOOLS:
                raise ValueError(f"Tool {spec.name!r} cannot be part of a plan")
            specs.append(spec)
        if any(sp.mutates for sp in specs):
            self._approve([sp.name for sp in specs if sp.mutates], [s.get("arguments") for s in steps])
        results: List[Any] = []
        with self.api.transaction(label, actor="agent"):
            for spec, step in zip(specs, steps):
                results.append(_serialize(spec.handler(self.api, **(step.get("arguments") or {}))))
        return results

    def _approve(self, names: List[str], arguments: Any) -> None:
        if self.approver is not None and not self.approver(names, arguments):
            raise PermissionError(f"Agent action denied: {', '.join(names)}")
