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


def test_fire_engineering_calculators_dialog(app, monkeypatch):
    from pyfds.gui.fire_engineering_dialog import CALCULATIONS
    from pyfds.gui.main_window import MainWindow
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    w = MainWindow(FdsApi())
    assert "Fire Engineering Calculators..." in _entries(_top(w, "Tools"))
    dlg = w._on_fire_engineering()
    for i in range(len(CALCULATIONS)):                     # every calculation runs with its defaults and lists numbers
        dlg.choice.setCurrentIndex(i)
        rows = dlg.calculate()
        assert rows, CALCULATIONS[i][0]
    dlg.choice.setCurrentIndex(1)                          # Heskestad plume: the centreline temperature falls with height
    dlg._inputs["z"].setValue(2.0)
    low = dict(dlg.calculate())
    dlg._inputs["z"].setValue(6.0)
    high = dict(dlg.calculate())
    assert low != high
    dlg.close()
    w.close()


def test_api_engineering_wrappers_call_the_calculations():
    """Four api.engineering wrappers passed argument names the calculations do not take (found by the dialog)."""
    eng = FdsApi().engineering
    assert eng.heskestad_plume(1000.0, 3.0).__class__.__name__ == "HeskestadResult"
    assert eng.ceiling_jet(1000.0, 2.0, 3.0).__class__.__name__ == "CeilingJetResult"
    assert eng.critical_velocity(5000.0, 6.0, 10.0).__class__.__name__ == "CriticalVelocityResult"
    assert eng.smoke_filling_time(1000.0, 100.0, 5.0, 2.0) > 0


def test_detector_response_time_runs_and_a_closer_detector_responds_sooner():
    eng = FdsApi().engineering
    near = eng.detector_response_time(1000.0, 3.0, 1.0)
    far = eng.detector_response_time(1000.0, 3.0, 4.0)
    assert near.activation_time_s is not None and near.peak_jet_temp_c > 20.0
    assert far.activation_time_s is None or far.activation_time_s > near.activation_time_s
