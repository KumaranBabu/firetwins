"""Long flat menus are folded into submenus (review 2026-10-29, section 3.1); every entry keeps working."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMenuBar, QMessageBox

from pyfds.api.facade import FdsApi
from pyfds.gui.menu_regroup import regroup


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _entries(menu):
    return [a.text().replace("&", "") for a in menu.actions() if not a.isSeparator()]


def _sub(menu, title):
    return next(a.menu() for a in menu.actions() if a.menu() is not None and a.text().replace("&", "") == title)


def _top(win, title):
    return _sub(win.menuBar(), title)


def test_editor_menus_are_grouped(app, monkeypatch):
    from pyfds.gui.main_window import MainWindow
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    w = MainWindow(FdsApi())
    model = _top(w, "Model")
    checks = _entries(_sub(model, "Model Checks"))
    assert checks[:2] == ["Run Model Checks", "Edit Model Checks..."] and "Find Errors..." in checks
    entries = _entries(model)
    assert entries.index("Model Checks") == entries.index("Auto-Fix") + 1          # beside Validate Project
    assert "Find Errors..." not in _entries(_top(w, "Tools"))                      # moved, not copied
    assert _entries(_sub(_top(w, "Edit"), "Visibility"))[0] == "Hide Selected"
    assert "Wireframe Mode" in _entries(_sub(_top(w, "View"), "Rendering Mode"))
    assert len(entries) < 41                                                       # was 41 in one list
    w.close()


def test_results_window_menus_are_grouped(app, monkeypatch):
    from pyfds.gui.results.window import ResultsWindow
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    w = ResultsWindow(FdsApi())
    assert "Stop Recording" in _entries(_sub(_top(w, "File"), "Movie"))
    assert _entries(_sub(_top(w, "View"), "Units")) == ["Time Display", "Temperature Unit", "Concentration Unit",
                                                         "Mass Fraction Unit"]
    w.close()


def test_regroup_keeps_actions_and_skips_missing_entries(app):
    bar = QMenuBar()
    m = bar.addMenu("&Edit")
    hits = []
    m.addAction("Alpha", lambda: hits.append("a"))
    m.addSeparator()
    m.addAction("Beta", lambda: hits.append("b"))
    made = regroup(bar, [("Edit", "&Group", ["Alpha", "Beta", "Missing"], {}), ("Nowhere", "X", ["Alpha"], {})])
    assert list(made) == ["Group"] and _entries(m) == ["Group"] and not [a for a in m.actions() if a.isSeparator()]
    for a in made["Group"].actions():
        a.trigger()
    assert hits == ["a", "b"]
