"""Dockable panels: Properties, Validation, Run Monitor (headless Qt)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.main_window import MainWindow  # noqa: E402
from pyfds.gui.run_monitor import RunMonitorPanel  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app):
    w = MainWindow(FdsApi())
    yield w
    w.close()


def _field(panel, name):
    return panel._fields[name]


def test_panels_exist_and_have_toggles(win):
    assert win.properties_dock.windowTitle() == "Properties"
    assert win.messages_dock.windowTitle() == "Messages"
    assert win.messages_tabs.count() == 2
    titles = [a.text().replace("&", "") for a in win.menuBar().actions()]
    assert "Window" in titles
    assert win.properties_dock.toggleViewAction().text() == "Properties"


def test_properties_panel_edits_selected_object(win):
    ob = win.api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="BOX")
    win.explorer.refresh()
    win.explorer.select_entity("obstructions", ob)
    panel = win.properties_panel
    assert "BOX" in panel.title.text() and panel.apply_button.isEnabled()
    assert panel.apply() == 0                       # nothing edited yet
    field = _field(panel, "x_max")
    field.setText("2.5")
    assert panel.apply() == 1
    assert ob.x_max == 2.5 and _field(panel, "x_max").text() == "2.5"
    win.api.undo()
    assert ob.x_max == 1.0


def test_properties_panel_reports_bad_input(app):
    errors = []
    api = FdsApi()
    ob = api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="BOX")
    from pyfds.gui.panels import PropertiesPanel
    panel = PropertiesPanel(api, on_error=errors.append)
    panel.show_entity("obstructions", ob)
    _field(panel, "x_max").setText("abc")
    assert panel.apply() == 0 and errors


def test_properties_panel_clears_without_selection(win):
    win.properties_panel.show_entity(None, None)
    assert win.properties_panel.title.text() == "Nothing selected"
    assert not win.properties_panel.apply_button.isEnabled()
    assert win.properties_panel.apply() == 0


def test_validation_panel_lists_findings_and_jumps(win):
    win._on_validate()
    panel = win.validation_panel
    assert panel.count() == len(win.api.validation.validate().results)
    jumped = []
    win.explorer.find_entity_by_name = lambda name: jumped.append(name)
    win._on_finding_activated("X")
    assert jumped == ["X"]


def test_run_panel_idle_then_watches(win, tmp_path):
    assert isinstance(win.run_panel, RunMonitorPanel) and win.run_panel.state == "idle"
    (tmp_path / "case.out").write_text("Total Time: 5.0 s\n")
    win.run_panel.watch(str(tmp_path), "case", 20.0)
    assert win.run_panel.headline.text() == "Running" and win.run_panel.bar.value() == 250
    win.run_panel.timer.stop()


def test_monitor_menu_uses_the_panel(win, tmp_path):
    (tmp_path / "case.out").write_text("Total Time: 1.0 s\n")
    win._last_run_dir = str(tmp_path)
    win.api.project.chid = "case"
    win._show_run_monitor()
    assert win.messages_tabs.currentWidget() is win.run_panel and not win.messages_dock.isHidden()
    win.run_panel.timer.stop()
