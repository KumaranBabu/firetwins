"""
Smoke tests — AgentChatPanel (src/pyfds/gui/agent_panel.py).

Runs Qt with the offscreen platform plugin so this works headless (no
display needed / suitable for CI). Uses a real ``AgentSession`` with an
injected fake Anthropic client (same pattern as test_agent_session.py) so
these tests exercise the full send -> tool-call -> undo/redo wiring without
needing the real anthropic package or network access.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(name, tool_input, id_="toolu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=id_)


class _ScriptedClient:
    def __init__(self, responses):
        self._responses = list(responses)

        class _Messages:
            def create(inner_self, **kwargs):
                return self._responses.pop(0)

        self.messages = _Messages()


def _make_session(responses):
    from pyfds.agent import AgentSession, AgentToolDispatcher
    from pyfds.api import FdsApi
    api = FdsApi()
    dispatcher = AgentToolDispatcher(api)
    session = AgentSession(dispatcher=dispatcher, client=_ScriptedClient(responses))
    return session, api


def _send_and_wait(panel, text: str) -> None:
    """Trigger a send and block until the background _SendWorker QThread
    finishes and its queued succeeded/failed signal has been delivered on
    this (main) thread — AgentSession.send() now runs off-thread so
    _on_send() returns before the reply is ready."""
    panel.input_box.setText(text)
    panel._on_send()
    panel._worker.wait()
    QApplication.processEvents()


def test_panel_constructs_with_undo_redo_disabled():
    from pyfds.gui.agent_panel import AgentChatPanel
    session, api = _make_session([])
    panel = AgentChatPanel(session, api.history)
    assert panel.undo_button.isEnabled() is False
    assert panel.redo_button.isEnabled() is False


def test_send_renders_transcript_and_enables_undo():
    from pyfds.gui.agent_panel import AgentChatPanel
    session, api = _make_session([
        SimpleNamespace(content=[_tool_use_block("add_mesh", {"ijk": [10, 10, 5], "xb": [0, 4, 0, 4, 0, 2]})]),
        SimpleNamespace(content=[_text_block("Added the mesh.")]),
    ])
    panel = AgentChatPanel(session, api.history)

    _send_and_wait(panel, "add a mesh")

    text = panel.transcript.toPlainText()
    assert "You: add a mesh" in text
    assert "add_mesh" in text
    assert "Assistant: Added the mesh." in text
    assert panel.undo_button.isEnabled() is True
    assert len(api.meshes.all()) == 1


def test_undo_button_reverts_agent_mutation():
    from pyfds.gui.agent_panel import AgentChatPanel
    session, api = _make_session([
        SimpleNamespace(content=[_tool_use_block("add_mesh", {"ijk": [10, 10, 5], "xb": [0, 4, 0, 4, 0, 2]})]),
        SimpleNamespace(content=[_text_block("Added the mesh.")]),
    ])
    panel = AgentChatPanel(session, api.history)
    _send_and_wait(panel, "add a mesh")
    assert len(api.meshes.all()) == 1

    panel._on_undo()

    assert len(api.meshes.all()) == 0
    assert panel.undo_button.isEnabled() is False
    assert panel.redo_button.isEnabled() is True


def test_input_disabled_while_send_in_flight_and_reenabled_after():
    from pyfds.gui.agent_panel import AgentChatPanel
    session, api = _make_session([SimpleNamespace(content=[_text_block("Hi.")])])
    panel = AgentChatPanel(session, api.history)

    panel.input_box.setText("hello")
    panel._on_send()
    # Worker just started — busy state should already be set on this thread
    # (set_busy(True) runs synchronously in _on_send before .start()).
    assert panel.input_box.isEnabled() is False
    assert panel.send_button.isEnabled() is False

    panel._worker.wait()
    QApplication.processEvents()

    assert panel.input_box.isEnabled() is True
    assert panel.send_button.isEnabled() is True


def test_send_failure_appends_error_and_reenables_input():
    from pyfds.gui.agent_panel import AgentChatPanel

    class _BrokenClient:
        class _Messages:
            def create(self, **kwargs):
                raise RuntimeError("network unreachable")
        messages = _Messages()

    from pyfds.agent import AgentSession, AgentToolDispatcher
    from pyfds.api import FdsApi
    api = FdsApi()
    session = AgentSession(dispatcher=AgentToolDispatcher(api), client=_BrokenClient())
    panel = AgentChatPanel(session, api.history)

    _send_and_wait(panel, "add a mesh")

    assert "network unreachable" in panel.transcript.toPlainText()
    assert panel.input_box.isEnabled() is True
    assert panel.send_button.isEnabled() is True


def test_empty_input_does_not_start_a_worker():
    from pyfds.gui.agent_panel import AgentChatPanel
    session, api = _make_session([])
    panel = AgentChatPanel(session, api.history)

    panel.input_box.setText("   ")
    panel._on_send()

    assert not hasattr(panel, "_worker")
