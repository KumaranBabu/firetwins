"""Model > Simulation Parameters, every tab, in the real window on the screen (a new project, as in example 1 step 2,
with T_END = 60 s). Writes <out>/NN_simulation_parameters[_tab].png and prints each tab's fields and values.

    python client_demos/simparams_shots.py <out folder>
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from demo_kit import ROOT  # noqa: E402,F401  (puts src on the path, real screen)

from PySide6.QtCore import QTimer                                                   # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QLineEdit, QMessageBox  # noqa: E402

from pyfds.api import FdsApi                                                        # noqa: E402
from pyfds.gui.main_window import MainWindow                                        # noqa: E402

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
app = QApplication.instance() or QApplication([])
from pyfds.gui.theme import apply_theme, saved_theme                                # noqa: E402
apply_theme(saved_theme(), app, remember=False)
win = MainWindow(FdsApi())
win.restore_keymap = lambda: None
win.showMaximized()


def pump(s: float) -> None:
    end = time.monotonic() + s
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def fields(w) -> list:
    """(label, value) of the visible form rows of the current tab."""
    rows = []
    for lab in w.findChildren(QLabel):
        buddy = lab.buddy()
        if buddy is not None and buddy.isVisible():
            val = buddy.currentText() if isinstance(buddy, QComboBox) else buddy.text() if isinstance(buddy, QLineEdit) \
                else getattr(buddy, "value", lambda: "?")()
            rows.append((lab.text(), val))
    return rows


def handler() -> None:
    dlg = app.activeModalWidget()
    if dlg is None:
        QTimer.singleShot(150, handler)
        return
    dlg.field_widget("time", "t_end").set_value(60.0)
    tabs = dlg.tabs
    for i in range(tabs.count()):
        tabs.setCurrentIndex(i)
        pump(0.5)
        name = tabs.tabText(i).replace("&", "")
        file = OUT / ("simulation_parameters.png" if i == 0 else f"simulation_parameters_{name.lower().replace(' ', '_')}.png")
        dlg.grab().save(str(file))
        print(f"== {name} -> {file.name}")
        for lab, val in fields(tabs.widget(i)):
            print(f"   {lab}: {val}")
    sys.stdout.flush()
    dlg.reject()


QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
pump(2.0)
QTimer.singleShot(400, handler)
win._on_simulation_parameters()
pump(0.5)
import os  # noqa: E402
os._exit(0)
