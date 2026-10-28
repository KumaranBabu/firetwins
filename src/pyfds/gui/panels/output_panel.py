"""Output panel: application log lines and a read-only preview of the FDS input the project would write."""
from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget

_MONO = "font-family: Consolas, monospace; font-size: 11px;"


class _Relay(QObject):
    line = Signal(str)


class _QtLogHandler(logging.Handler):
    """Forwards log records to a Qt signal (safe to emit from worker threads)."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.relay = _Relay()
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.relay.line.emit(self.format(record))
        except RuntimeError:                      # the panel is gone
            pass


class OutputPanel(QWidget):
    def __init__(self, api: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._api = api
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)                       # flat inner tabs: the outer Messages tab bar is already there
        root.addWidget(self.tabs)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        self.log.setStyleSheet(_MONO)
        self.tabs.addTab(self.log, "Log")

        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_fds)
        row.addWidget(refresh)
        col.addLayout(row)
        self.fds = QPlainTextEdit()
        self.fds.setReadOnly(True)
        self.fds.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.fds.setStyleSheet(_MONO)
        col.addWidget(self.fds, 1)
        self.tabs.addTab(box, "FDS Input")
        self.tabs.currentChanged.connect(lambda i: self.refresh_fds() if i == 1 else None)

        self._handler = _QtLogHandler()
        self._handler.relay.line.connect(self.log.appendPlainText)
        logging.getLogger("pyfds").addHandler(self._handler)
        if logging.getLogger("pyfds").getEffectiveLevel() > logging.INFO:
            logging.getLogger("pyfds").setLevel(logging.INFO)

    def refresh_fds(self) -> None:
        try:
            self.fds.setPlainText(self._api.fds_text())
        except Exception as exc:                  # an incomplete model must not break the panel
            self.fds.setPlainText(f"Cannot generate the FDS input yet: {exc}")

    def shutdown(self) -> None:
        logging.getLogger("pyfds").removeHandler(self._handler)
