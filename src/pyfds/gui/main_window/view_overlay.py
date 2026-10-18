"""The icon strip that floats over the 3D view: the important View controls one click away, so the toolbars can stay hidden.

The strip holds buttons for *existing* QActions (render mode, standard views, grid, axes, snap, save image, panels, focus), so a
button is always in step with the menu entry and toolbar button that do the same thing. The first button folds the strip away."""
from __future__ import annotations

from typing import Iterable, List, Optional

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QWidget

_STYLE = """
QFrame#ViewOverlay { background: #2b2d31; border: 1px solid #4a4d55; border-radius: 6px; }
QFrame#ViewOverlay QToolButton { border: 1px solid transparent; border-radius: 4px; background: transparent; }
QFrame#ViewOverlay QToolButton:hover { background: #41444b; }
QFrame#ViewOverlay QToolButton:checked { background: #4b4f8c; border-color: #6a6fd0; }
QFrame#ViewOverlay QFrame#OverlaySeparator { background: #4a4d55; max-width: 1px; }
"""
_MARGIN = 8


class ViewOverlay(QFrame):
    """A small dark strip at the top-left corner of *host* (the 3D view widget)."""

    def __init__(self, host: QWidget, groups: Iterable[List[object]], collapse_icon=None) -> None:
        super().__init__(host)
        self.setObjectName("ViewOverlay")
        self.setStyleSheet(_STYLE)
        self.setAttribute(Qt.WA_NativeWindow, True)        # the 3D view is a native OpenGL window: a plain child would be hidden behind it
        self._host = host
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self.fold_button = self._button(None, "Show or hide this strip of view controls")
        self.fold_button.setCheckable(True)
        self.fold_button.setChecked(True)
        if collapse_icon is not None:
            self.fold_button.setIcon(collapse_icon)
        self.fold_button.toggled.connect(self.set_expanded)
        row.addWidget(self.fold_button)
        self.body = QWidget(self)
        body_row = QHBoxLayout(self.body)
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(2)
        row.addWidget(self.body)
        self.buttons: List[QToolButton] = []
        for n, group in enumerate(groups):
            if n:
                sep = QFrame(self.body)
                sep.setObjectName("OverlaySeparator")
                sep.setFixedSize(1, 20)
                body_row.addWidget(sep)
            for item in group:
                b = self._button(item if isinstance(item, QAction) else None)
                if not isinstance(item, QAction):
                    item(b)                                  # a callable customises the button (e.g. gives it a menu)
                body_row.addWidget(b)
                self.buttons.append(b)
        host.installEventFilter(self)
        self.adjustSize()
        self.place()

    def _button(self, action: Optional[QAction], tip: str = "") -> QToolButton:
        b = QToolButton(self)
        b.setAutoRaise(True)
        b.setIconSize(QSize(20, 20))
        b.setFixedSize(28, 28)
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)
        if action is not None:
            b.setDefaultAction(action)
            if not action.toolTip():
                b.setToolTip(action.text().replace("&", ""))
        if tip:
            b.setToolTip(tip)
        return b

    @property
    def expanded(self) -> bool:
        return not self.body.isHidden()

    def set_expanded(self, on: bool) -> None:
        self.body.setVisible(bool(on))
        if self.fold_button.isChecked() != bool(on):
            self.fold_button.setChecked(bool(on))
        self.adjustSize()

    def place(self) -> None:
        self.move(_MARGIN, _MARGIN)
        self.raise_()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._host and event.type() in (QEvent.Resize, QEvent.Show):
            self.place()
        return False
