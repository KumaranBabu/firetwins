"""PyFDS main window (the model editor).

Run directly::

    python -m pyfds.gui.main_window
"""
from __future__ import annotations

import shutil  # noqa: F401  (re-exported: tests patch ``main_window.shutil``)

from PySide6.QtGui import QDesktopServices  # noqa: F401  (re-exported)
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox  # noqa: F401  (re-exported)

from .explorer import ProjectExplorer
from .window import MainWindow

__all__ = ["MainWindow", "ProjectExplorer", "main"]


def main() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._persist_layout = True      # remember the dock arrangement between sessions
    window.restore_saved_layout()
    window.show()
    app.exec()
