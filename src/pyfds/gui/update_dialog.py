"""Check for Updates dialog: runs the (read-only) check on a worker thread so the window never freezes on a slow network."""
from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget


_COLOURS = {"up_to_date": "#15803d", "ahead": "#15803d", "behind": "#b45309", "diverged": "#b45309", "unknown": "#6b7280"}


class _Worker(QThread):
    done = Signal(object)

    def __init__(self, check: Callable[[], Any], failed: Callable[[str], Any], parent=None) -> None:
        super().__init__(parent)
        self._check = check
        self._failed = failed

    def run(self) -> None:                                              # noqa: D401 (Qt API)
        try:
            self.done.emit(self._check())
        except Exception as exc:                                        # the check must never take the app down
            self.done.emit(self._failed(f"The check failed: {exc}"))


class UpdateDialog(QDialog):
    def __init__(self, api: Any, parent: Optional[QWidget] = None, check: Optional[Callable[[], Any]] = None,
                 start: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle("Check for Updates")
        self.resize(480, 190)
        self.status: Any = None
        v = QVBoxLayout(self)
        self.label = QLabel("Checking the remote repository...", self)
        self.label.setWordWrap(True)
        v.addWidget(self.label)
        self.detail = QLabel("", self)
        self.detail.setStyleSheet("color: #6b7280;")
        v.addWidget(self.detail)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)
        self._worker = _Worker(check or api.updates.check, api.updates.unknown, self)
        self._worker.done.connect(self.show_result)
        if start:
            self._worker.start()

    def show_result(self, status: Any) -> None:
        self.status = status
        self.label.setText(status.message)
        self.label.setStyleSheet(f"font-weight: 600; color: {_COLOURS.get(status.state, '#6b7280')};")
        if status.local:
            self.detail.setText(f"This copy: {status.local[:10]}" + (f"    Remote: {status.remote[:10]}" if status.remote else ""))

    def wait(self, ms: int = 30000) -> bool:
        """Block until the check has finished and its result has been shown (used by tests and scripts)."""
        from PySide6.QtWidgets import QApplication
        finished = self._worker.wait(ms)
        QApplication.processEvents()                                    # the result arrives as a queued signal
        return finished

    def done(self, result: int) -> None:                                # noqa: D401 (Qt API)
        if self._worker.isRunning():
            self._worker.wait(5000)
        super().done(result)
