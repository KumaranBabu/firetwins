"""Centre of the main window: a "Model" tab (3D editor view) and a closable "Results" tab holding the results viewer."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtWidgets import QLabel, QTabBar, QTabWidget


class CentralTabsMixin:
    def _build_central_tabs(self) -> None:
        """Put the 3D view in the first tab; the results viewer is added when the first results are opened."""
        self.view_tabs = QTabWidget(self)
        self.view_tabs.setDocumentMode(True)
        self.view_tabs.setTabsClosable(True)
        self.view_tabs.addTab(self.viewport_widget, "Model")
        self.view_tabs.tabBar().setTabButton(0, QTabBar.RightSide, None)      # the Model tab cannot be closed
        self.view_tabs.tabCloseRequested.connect(self._on_close_view_tab)
        self.setCentralWidget(self.view_tabs)
        self._results_window = None

    def show_results_tab(self, smv: Optional[str] = None) -> Any:
        """Show the results viewer in its own tab next to the model (created on first use) and open *smv* in it."""
        from pyfds.gui.results.window import ResultsWindow
        from PySide6.QtCore import Qt
        win = self._results_window
        if win is None:
            win = ResultsWindow(self.api, self)
            win.setWindowFlags(Qt.Widget)             # a plain child widget, not a separate top-level window
            self._results_window = win
            self.view_tabs.addTab(win, "Results")
        self.view_tabs.setCurrentWidget(win)
        if smv:
            win.open_results(smv)
        return win

    def show_model_tab(self) -> None:
        self.view_tabs.setCurrentWidget(self.viewport_widget)

    def _on_close_view_tab(self, index: int) -> None:
        widget = self.view_tabs.widget(index)
        if widget is self.viewport_widget:
            return
        self.view_tabs.removeTab(index)
        if widget is self._results_window:
            self._results_window = None
        widget.close()
        widget.deleteLater()

    def _update_cursor_label(self, point) -> None:
        if point is None:
            self.cursor_label.setText("")
        else:
            self.cursor_label.setText("x %.2f  y %.2f  z %.2f m" % tuple(point))

    def _build_cursor_label(self) -> None:
        self.cursor_label = QLabel("")
        self.cursor_label.setMinimumWidth(190)
        self.statusBar().insertPermanentWidget(0, self.cursor_label)
        if hasattr(self.viewport_widget, "cursor_moved"):
            self.viewport_widget.cursor_moved.connect(self._update_cursor_label)
