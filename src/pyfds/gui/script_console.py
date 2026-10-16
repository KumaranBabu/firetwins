"""Script Console (Tools): type Python against the open project.

``api`` is the application's ``FdsApi`` (every change it makes is an undo step like any other), ``window`` is the main
window. A line that is an expression shows its value, like a Python prompt; anything else is run as a statement. This is the
user's own code running in the user's own session: there is no sandbox, by design.
"""
from __future__ import annotations

import contextlib
import io
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

BANNER = ("Python console. `api` is the project's FdsApi, `window` is the main window.\n"
          "Run with the Run button or Ctrl+Enter; Alt+Up / Alt+Down recall earlier input.\n"
          "Example:  api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1])\n")


@dataclass
class ScriptResult:
    output: str = ""          # what the code printed
    value: Optional[str] = None   # repr of the last expression, if it was one
    error: str = ""           # a short traceback when the code failed

    @property
    def ok(self) -> bool:
        return not self.error


class ScriptSession:
    """One console's namespace and history; separate from any widget so it can be tested directly."""

    def __init__(self, api: Any, window: Any = None) -> None:
        self.namespace: Dict[str, Any] = {"api": api, "window": window, "__name__": "__console__"}
        self.history: List[str] = []

    def execute(self, source: str) -> ScriptResult:
        source = source.rstrip()
        if not source.strip():
            return ScriptResult()
        self.history.append(source)
        buf = io.StringIO()
        result = ScriptResult()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                try:
                    code = compile(source, "<console>", "eval")
                except SyntaxError:
                    exec(compile(source, "<console>", "exec"), self.namespace)         # noqa: S102 (the user's own code)
                else:
                    value = eval(code, self.namespace)                                  # noqa: S307
                    if value is not None:
                        result.value = repr(value)
                        self.namespace["_"] = value
        except SystemExit:
            result.error = "SystemExit is ignored here: close the console window instead."
        except BaseException:                                                           # noqa: BLE001 - report, never crash
            tb = traceback.format_exc().splitlines()
            keep = [ln for ln in tb if "<console>" in ln or not ln.startswith("  File")]
            result.error = "\n".join(keep[-6:])
        result.output = buf.getvalue()
        return result

    def recall(self, index: int, step: int) -> int:
        """History navigation: the new position after moving *step* (-1 older, +1 newer); len(history) = blank."""
        return max(0, min(len(self.history), index + step))


class ScriptConsoleDialog(QDialog):
    def __init__(self, api: Any, window: Any = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.session = ScriptSession(api, window)
        self.setWindowTitle("Script Console")
        self.resize(760, 520)
        self._pos = 0
        v = QVBoxLayout(self)
        self.output = QPlainTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setPlainText(BANNER)
        v.addWidget(self.output, 3)
        v.addWidget(QLabel("Input", self))
        self.input = QPlainTextEdit(self)
        self.input.setPlaceholderText("api.meshes.all()")
        self.input.setMaximumHeight(140)
        self.input.installEventFilter(self)
        v.addWidget(self.input, 1)
        row = QHBoxLayout()
        self.run_button = QPushButton("Run (Ctrl+Enter)", self)
        self.run_button.clicked.connect(lambda _c=False: self.run())
        self.clear_button = QPushButton("Clear output", self)
        self.clear_button.clicked.connect(lambda _c=False: self.output.setPlainText(BANNER))
        row.addWidget(self.run_button)
        row.addWidget(self.clear_button)
        row.addStretch(1)
        v.addLayout(row)

    def run(self, source: Optional[str] = None) -> ScriptResult:
        """Run *source* (default: the input box), append the outcome to the output, and clear the input."""
        text = self.input.toPlainText() if source is None else source
        result = self.session.execute(text)
        if text.strip():
            self.output.appendPlainText(">>> " + text.replace("\n", "\n... "))
            if result.output:
                self.output.appendPlainText(result.output.rstrip("\n"))
            if result.value is not None:
                self.output.appendPlainText(result.value)
            if result.error:
                self.output.appendPlainText(result.error)
        if source is None:
            self.input.clear()
        self._pos = len(self.session.history)
        return result

    def eventFilter(self, obj, event):                                               # noqa: N802 (Qt API)
        from PySide6.QtCore import QEvent
        if obj is self.input and event.type() == QEvent.KeyPress:
            ctrl, alt = bool(event.modifiers() & Qt.ControlModifier), bool(event.modifiers() & Qt.AltModifier)
            if ctrl and event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.run()
                return True
            if alt and event.key() in (Qt.Key_Up, Qt.Key_Down):
                self.recall(-1 if event.key() == Qt.Key_Up else 1)
                return True
        return super().eventFilter(obj, event)

    def recall(self, step: int) -> None:
        self._pos = self.session.recall(self._pos, step)
        self.input.setPlainText(self.session.history[self._pos] if self._pos < len(self.session.history) else "")
