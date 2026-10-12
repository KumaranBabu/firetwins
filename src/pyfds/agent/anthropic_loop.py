"""
Embedded Anthropic tool-use agent loop.

Runs in-process inside the GUI (or a CLI/script) — no separate server. Sends
the conversation plus ``AgentToolDispatcher.anthropic_tools()`` to Claude,
executes any ``tool_use`` blocks it returns via the dispatcher, feeds
``tool_result`` blocks back, and repeats until Claude returns a plain text
turn. Every tool call is appended to ``AgentSession.log`` so a GUI chat
panel can render "plain-English action, undo" rows.

Requires the optional ``anthropic`` package
(``pip install pyfds[agent_anthropic]``); this module is only imported when
the embedded-agent panel is actually used, never by the headless backend.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .dispatcher import AgentToolDispatcher
from .registry import get_tool

DEFAULT_MODEL = "claude-sonnet-5"

DEFAULT_SYSTEM_PROMPT = (
    "You are an assistant embedded in PyFDS, a fire-modeling CAD/simulation tool. "
    "You help a fire safety engineer build and check an FDS model through the "
    "provided tools. Prefer the engineering calculator tools (characterise_fire, "
    "recommend_cell_size, ceiling_jet, heskestad_plume, critical_velocity, "
    "smoke_filling_time, two_layer_zone_model, detector_response_time) to check "
    "or justify a design choice BEFORE calling a mutating tool like add_mesh or "
    "add_obstruction — proactively recommend the better engineering choice rather "
    "than only doing exactly what is literally asked. Always call validate_project "
    "after a batch of model changes and report any failures."
)


@dataclass
class ToolCallLogEntry:
    """One agent-driven action — enough for a GUI to show it and undo it."""
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    mutated: bool
    error: Optional[str] = None


@dataclass
class AgentSession:
    """
    A running conversation between the user and Claude, backed by an
    ``FdsApi`` instance via ``AgentToolDispatcher``.

    Usage::

        session = AgentSession(dispatcher=AgentToolDispatcher(api))
        reply = session.send("Add a 500 kW fire in a 5x5x3 m room and size the mesh for it")
        for entry in session.log:
            print(entry.tool_name, entry.arguments, "mutated" if entry.mutated else "advisory")
    """
    dispatcher: AgentToolDispatcher
    model: str = DEFAULT_MODEL
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_tool_iterations: int = 10
    on_tool_call: Optional[Callable[[ToolCallLogEntry], None]] = None
    client: Any = None

    messages: List[Dict[str, Any]] = field(default_factory=list)
    log: List[ToolCallLogEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.client is None:
            import anthropic
            self.client = anthropic.Anthropic()

    def send(self, user_text: str) -> str:
        """Send a user message, run the tool loop, return Claude's final text reply."""
        self.messages.append({"role": "user", "content": user_text})

        for _ in range(self.max_tool_iterations):
            response = self.client.messages.create(
                model=self.model,
                system=self.system_prompt,
                max_tokens=4096,
                tools=self.dispatcher.anthropic_tools(),
                messages=self.messages,
            )
            self.messages.append({"role": "assistant", "content": response.content})

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                return "".join(b.text for b in response.content if b.type == "text")

            tool_results = []
            for block in tool_uses:
                entry = self._run_tool(block.name, block.input or {})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _stringify(entry.error or entry.result),
                    **({"is_error": True} if entry.error else {}),
                })
            self.messages.append({"role": "user", "content": tool_results})

        raise RuntimeError(f"Exceeded max_tool_iterations={self.max_tool_iterations}")

    def _run_tool(self, name: str, arguments: Dict[str, Any]) -> ToolCallLogEntry:
        try:
            spec = get_tool(name)
            result = self.dispatcher.call(name, arguments)
            entry = ToolCallLogEntry(tool_name=name, arguments=arguments, result=result, mutated=spec.mutates)
        except Exception as exc:
            entry = ToolCallLogEntry(tool_name=name, arguments=arguments, result=None, mutated=False, error=str(exc))
        self.log.append(entry)
        if self.on_tool_call:
            self.on_tool_call(entry)
        return entry


def _stringify(value: Any) -> str:
    try:
        return json.dumps(value)
    except TypeError:
        return str(value)
