"""
Dockable chat/action-log panel — the AI agent's presence in the traditional
GUI.

The panel is optional (per user decision: the traditional GUI is primary,
AI is an add-on the user can ignore entirely). It only talks to the backend
through an ``AgentSession`` (which itself only calls ``FdsApi`` manager
methods via ``AgentToolDispatcher``) and the shared ``HistoryManager`` —
never the domain model directly, same rule as every other widget.

Each tool call the agent makes is rendered as a plain-English transcript
line; mutating calls are undo-able through the *same* global Undo/Redo
buttons a human-driven action would use (``FdsApi`` has one linear command
history shared by both paths — see ai-agentic-gui memory).

``AgentSession.send()`` does blocking network I/O (one or more Anthropic
API round-trips) — running it directly on the Qt main thread would freeze
the whole app, including the 3D viewport and every other dock, for the
duration of the request. ``_on_send()`` instead runs it on a background
``_SendWorker`` QThread and only touches widgets again from the
``succeeded``/``failed`` signal handlers, which Qt marshals back onto the
main thread automatically. The tool calls themselves change the model, and
the model's listeners (Project Explorer, panels) rebuild widgets, so each
tool call is handed to the main thread (``_MainThreadCall``) and the worker
waits for its result. The input row is disabled while a request is in
flight — both to give the user feedback and because ``AgentSession``'s
``messages``/``log`` lists are plain, non-thread-safe Python lists; only
ever one send in flight at a time.
"""
from __future__ import annotations

from typing import Any, Protocol

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton,
)


class _SendsMessages(Protocol):
    """The subset of ``AgentSession`` this panel depends on."""
    log: list

    def send(self, user_text: str) -> str: ...


def _describe(entry: Any) -> str:
    args = ", ".join(f"{k}={v!r}" for k, v in entry.arguments.items())
    if entry.error:
        return f"  ↳ {entry.tool_name}({args}) ✗ {entry.error}"
    kind = "mutated" if entry.mutated else "advisory"
    return f"  ↳ {entry.tool_name}({args}) ✓ [{kind}]"


class _MainThreadCall(QObject):
    """Runs a function on the thread this object lives on (the GUI thread) and returns its result to the caller,
    which blocks until it is done. Called from the GUI thread itself it simply runs the function."""
    _request = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._request.connect(self._run, Qt.BlockingQueuedConnection)

    def __call__(self, fn: Any) -> Any:
        if QThread.currentThread() is self.thread():
            return fn()
        box: dict = {}
        self._request.emit((fn, box))
        if "error" in box:
            raise box["error"]
        return box.get("result")

    @Slot(object)
    def _run(self, job: Any) -> None:
        fn, box = job
        try:
            box["result"] = fn()
        except Exception as exc:                 # handed back to the worker, which reports it to the assistant
            box["error"] = exc


class _SendWorker(QThread):
    """Runs one ``AgentSession.send()`` call off the Qt main thread."""
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, session: _SendsMessages, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._text = text

    def run(self) -> None:
        try:
            reply = self._session.send(self._text)
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(reply)


class AgentChatPanel(QWidget):
    """
    A minimal chat + action-log widget. Embed with
    ``main_window.addDockWidget(Qt.RightDockWidgetArea, dock)`` where
    ``dock`` wraps an ``AgentChatPanel`` instance.
    """

    def __init__(self, session: _SendsMessages, history: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._history = history
        self._rendered_log_count = 0
        if hasattr(session, "tool_executor"):
            session.tool_executor = _MainThreadCall(self)

        self.transcript = QTextEdit(self)
        self.transcript.setReadOnly(True)

        self.input_box = QLineEdit(self)
        self.input_box.setPlaceholderText("Ask the assistant to model, check, or size something...")
        self.input_box.returnPressed.connect(self._on_send)

        self.send_button = QPushButton("Send", self)
        self.send_button.clicked.connect(self._on_send)

        self.undo_button = QPushButton("Undo", self)
        self.undo_button.clicked.connect(self._on_undo)
        self.redo_button = QPushButton("Redo", self)
        self.redo_button.clicked.connect(self._on_redo)

        input_row = QHBoxLayout()
        input_row.addWidget(self.input_box)
        input_row.addWidget(self.send_button)

        history_row = QHBoxLayout()
        history_row.addWidget(self.undo_button)
        history_row.addWidget(self.redo_button)
        history_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.transcript)
        layout.addLayout(input_row)
        layout.addLayout(history_row)

        self.refresh_history_buttons()

    # ── Actions ──────────────────────────────────────────────────────────────

    def _on_send(self) -> None:
        text = self.input_box.text().strip()
        if not text:
            return
        self.input_box.clear()
        self._append(f"You: {text}")
        self._set_busy(True)

        self._worker = _SendWorker(self._session, text, self)
        self._worker.succeeded.connect(self._on_send_succeeded)
        self._worker.failed.connect(self._on_send_failed)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_send_succeeded(self, reply: str) -> None:
        for entry in self._session.log[self._rendered_log_count:]:
            self._append(_describe(entry))
        self._rendered_log_count = len(self._session.log)

        self._append(f"Assistant: {reply}")
        self.refresh_history_buttons()
        self._set_busy(False)

    def _on_send_failed(self, error_text: str) -> None:
        self._append(f"(error: {error_text})")
        self._set_busy(False)

    def _on_undo(self) -> None:
        self._history.undo()
        self._append("(undo)")
        self.refresh_history_buttons()

    def _on_redo(self) -> None:
        self._history.redo()
        self._append("(redo)")
        self.refresh_history_buttons()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _append(self, line: str) -> None:
        self.transcript.append(line)

    def _set_busy(self, busy: bool) -> None:
        self.input_box.setEnabled(not busy)
        self.send_button.setEnabled(not busy)

    def refresh_history_buttons(self) -> None:
        self.undo_button.setEnabled(bool(self._history.can_undo()))
        self.redo_button.setEnabled(bool(self._history.can_redo()))
