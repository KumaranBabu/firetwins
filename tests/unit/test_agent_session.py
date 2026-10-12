"""
Unit tests — embedded Anthropic tool-use loop (src/pyfds/agent/anthropic_loop.py).

A fake Anthropic client is injected (``client=...``) so these tests exercise
the tool-call loop, logging, and error handling without the real
``anthropic`` package or network access.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


def _make_dispatcher():
    from pyfds.agent import AgentToolDispatcher
    from pyfds.api import FdsApi
    return AgentToolDispatcher(FdsApi())


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(name, tool_input, id_="toolu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=id_)


class _ScriptedClient:
    """Fake Anthropic client that returns a pre-scripted sequence of responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

        class _Messages:
            def create(inner_self, **kwargs):
                self.calls.append(kwargs)
                return self._responses.pop(0)

        self.messages = _Messages()


def test_send_returns_text_when_no_tool_use():
    from pyfds.agent import AgentSession
    client = _ScriptedClient([SimpleNamespace(content=[_text_block("hello")])])
    session = AgentSession(dispatcher=_make_dispatcher(), client=client)

    reply = session.send("hi")

    assert reply == "hello"
    assert session.log == []


def test_send_executes_tool_and_logs_it():
    from pyfds.agent import AgentSession
    client = _ScriptedClient([
        SimpleNamespace(content=[_tool_use_block("add_mesh", {"ijk": [10, 10, 5], "xb": [0, 4, 0, 4, 0, 2]})]),
        SimpleNamespace(content=[_text_block("Added the mesh.")]),
    ])
    dispatcher = _make_dispatcher()
    session = AgentSession(dispatcher=dispatcher, client=client)

    reply = session.send("add a mesh")

    assert reply == "Added the mesh."
    assert len(session.log) == 1
    entry = session.log[0]
    assert entry.tool_name == "add_mesh"
    assert entry.mutated is True
    assert entry.error is None
    assert len(dispatcher.api.meshes.all()) == 1


def test_send_records_tool_error_without_raising():
    from pyfds.agent import AgentSession
    client = _ScriptedClient([
        SimpleNamespace(content=[_tool_use_block("remove_obstruction", {"name": "ghost"})]),
        SimpleNamespace(content=[_text_block("Could not find that obstruction.")]),
    ])
    session = AgentSession(dispatcher=_make_dispatcher(), client=client)

    reply = session.send("remove ghost")

    assert "Could not find" in reply
    assert session.log[0].error is not None


def test_on_tool_call_callback_invoked():
    from pyfds.agent import AgentSession
    client = _ScriptedClient([
        SimpleNamespace(content=[_tool_use_block("list_meshes", {})]),
        SimpleNamespace(content=[_text_block("done")]),
    ])
    seen = []
    session = AgentSession(dispatcher=_make_dispatcher(), client=client, on_tool_call=seen.append)

    session.send("list meshes")

    assert len(seen) == 1
    assert seen[0].tool_name == "list_meshes"


def test_exceeding_max_tool_iterations_raises():
    from pyfds.agent import AgentSession
    responses = [
        SimpleNamespace(content=[_tool_use_block("list_meshes", {}, id_=f"toolu_{i}")])
        for i in range(3)
    ]
    client = _ScriptedClient(responses)
    session = AgentSession(dispatcher=_make_dispatcher(), client=client, max_tool_iterations=3)

    with pytest.raises(RuntimeError):
        session.send("loop forever")
