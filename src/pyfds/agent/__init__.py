"""
PyFDS Agent Tool Layer
=======================
Exposes a subset of ``FdsApi`` manager methods as framework-agnostic tool
definitions (JSON Schema) that an LLM agent can call.

Design contract (see memory: ai-agentic-gui):
  The agent is one more *consumer* of ``FdsApi`` — it calls the exact same
  manager methods a human-driven GUI button would call. There is no
  separate "AI mode" and no direct mutation of project/domain objects.
  This keeps undo/redo, validation, and GUI sync (via the EventBus)
  correct for both humans and the agent automatically.

``registry.TOOL_REGISTRY`` is the single source of truth. It is rendered
into an Anthropic Messages API tool list by ``dispatcher.AgentToolDispatcher``
for the embedded desktop-app agent loop.
"""
from .registry import ToolSpec, TOOL_REGISTRY
from .dispatcher import AgentToolDispatcher
from .anthropic_loop import AgentSession, ToolCallLogEntry

__all__ = [
    "ToolSpec", "TOOL_REGISTRY", "AgentToolDispatcher",
    "AgentSession", "ToolCallLogEntry",
]
