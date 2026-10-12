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
    assert win.messages_tabs.count() == 4
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


def test_layers_panel_toggles_viewport_flags(win):
    from pyfds.core.viewport import VisibilityFlags
    from PySide6.QtCore import Qt
    panel = win.layers_panel
    item = panel._items[VisibilityFlags.OBSTRUCTIONS]
    item.setCheckState(Qt.Unchecked)
    assert not win.api.viewport.state.is_visible(VisibilityFlags.OBSTRUCTIONS)
    panel.set_all(True)
    assert win.api.viewport.state.is_visible(VisibilityFlags.OBSTRUCTIONS) and item.checkState() == Qt.Checked
    win.api.viewport.set_visibility(VisibilityFlags.VENTS, False)
    panel.sync()
    assert panel._items[VisibilityFlags.VENTS].checkState() == Qt.Unchecked


def test_output_panel_previews_fds_and_logs(win):
    import logging
    win.output_panel.refresh_fds()
    assert "&HEAD" in win.output_panel.fds.toPlainText()
    logging.getLogger("pyfds.test").info("hello panel")
    assert "hello panel" in win.output_panel.log.toPlainText()


def test_results_panel_lists_and_opens(app, tmp_path):
    from pyfds.gui.panels.results_panel import ResultsPanel, find_result_sets
    (tmp_path / "run1").mkdir()
    (tmp_path / "run1" / "case.smv").write_text("x")
    assert [p.name for p in find_result_sets(str(tmp_path))] == ["case.smv"]
    opened = []
    panel = ResultsPanel(lambda: str(tmp_path), opened.append)
    assert panel.list.count() == 1 and panel.open_button.isEnabled()
    panel.open_selected()
    assert opened and opened[0].endswith("case.smv")
    empty = ResultsPanel(lambda: None, opened.append)
    assert empty.list.count() == 0 and not empty.open_button.isEnabled()


def test_workspaces_show_the_right_panels(win):
    win.show()
    win._apply_workspace("run")
    assert not win.messages_dock.isHidden() and win.messages_tabs.currentWidget() is win.run_panel
    assert win.properties_dock.isHidden()
    win._apply_workspace("model")
    assert not win.properties_dock.isHidden() and not win.layers_dock.isHidden()
    win._apply_workspace("results")
    assert win.messages_tabs.currentWidget() is win.results_panel and win.properties_dock.isHidden()


def test_status_labels_follow_selection_and_run(win, tmp_path):
    ob = win.api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="BOX")
    win.explorer.refresh()
    win.explorer.select_entity("obstructions", ob)
    assert win.selection_label.text() == "1 selected"
    (tmp_path / "case.out").write_text("Total Time: 5.0 s\n")
    win.run_panel.watch(str(tmp_path), "case", 20.0)
    win._update_run_label()
    assert win.run_label.text() == "Run: running 25%"
    win.run_panel.timer.stop()


def test_results_open_in_a_tab_beside_the_model(win, monkeypatch):
    from pyfds.gui.results.window import ResultsWindow
    opened = []
    monkeypatch.setattr(ResultsWindow, "open_results", lambda self, smv=None: opened.append(smv))
    assert win.view_tabs.count() == 1
    first = win.show_results_tab("a.smv")
    assert win.view_tabs.count() == 2 and win.view_tabs.currentWidget() is first and opened == ["a.smv"]
    assert win._results_window is first and not first.isWindow()
    assert win.show_results_tab("b.smv") is first and win.view_tabs.count() == 2     # reused, not duplicated
    win.show_model_tab()
    assert win.view_tabs.currentWidget() is win.viewport_widget
    win._on_close_view_tab(0)                                                      # the Model tab cannot be closed
    assert win.view_tabs.count() == 2
    win._on_close_view_tab(1)
    assert win.view_tabs.count() == 1 and win._results_window is None


def test_cursor_label_formats_and_clears(win):
    win._update_cursor_label((1.0, 2.5, 0.0))
    assert win.cursor_label.text() == "x 1.00  y 2.50  z 0.00 m"
    win._update_cursor_label(None)
    assert win.cursor_label.text() == ""


def test_ray_floor_point():
    from pyfds.gui.viewport_cursor import ray_floor_point
    assert ray_floor_point((0, 0, 10), (2, 4, -10)) == (1.0, 2.0, 0.0)
    assert ray_floor_point((0, 0, 5), (1, 1, 5)) is None          # parallel to the floor
    assert ray_floor_point((0, 0, 5), (1, 1, 9)) is None          # floor is behind the ray
