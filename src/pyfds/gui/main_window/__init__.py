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
    from pyfds.gui.theme import apply_theme, saved_theme
    apply_theme(saved_theme(), app, remember=False)
    window = MainWindow()
    window.api.library.use_default_path()      # the user library is kept between sessions
    window._persist_layout = True      # remember the dock arrangement between sessions
    window.restore_saved_layout()
    window.restore_keymap()            # shortcuts changed in Help > Keyboard Shortcuts
    window.showMaximized()             # always start as large as the screen allows; the saved geometry is what "restore down" returns to
    app.exec()
