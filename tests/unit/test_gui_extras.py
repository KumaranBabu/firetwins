"""GUI additions: room dialog, library browser, run monitor, results viewer, menu wiring (headless Qt)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                   # noqa: E402
from PySide6.QtWidgets import QApplication                      # noqa: E402

from pyfds.api import FdsApi                                    # noqa: E402
from pyfds.gui.library_dialog import LibraryDialog              # noqa: E402
from pyfds.gui.results_viewer import ResultsViewerDialog        # noqa: E402
from pyfds.gui.room_dialog import RoomDialog                    # noqa: E402
from pyfds.gui.run_monitor import RunMonitorDialog, read_hrr, read_progress   # noqa: E402

FIX = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh(ijk=(40, 30, 20), xb=(0, 6, 0, 4.5, 0, 3), name="DOMAIN")
    return a


# -- room dialog -----------------------------------------------------------------------------------
def test_room_dialog_values_drive_add_room(app, api):
    dlg = RoomDialog(["INERT"])
    dlg._add_row("S", 3.0, 0.9, 2.1, 0.0)
    dlg._add_row("E", 2.25, 1.2, 1.05, 0.9)
    v = dlg.values()
    assert v["xb"] == [0.6, 5.4, 0.6, 3.9] and len(v["openings"]) == 2
    r = api.geom.add_room(**v)
    assert len(r["walls"]) == 5 and len(r["holes"]) == 2


def test_room_dialog_rejects_a_bad_wall_letter(app):
    dlg = RoomDialog(["INERT"])
    dlg._add_row("Q", 1, 1, 1, 0)
    with pytest.raises(ValueError):
        dlg.values()
    dlg.table.selectRow(0)
    dlg._remove_row()
    assert dlg.table.rowCount() == 0 and "openings" not in dlg.values()


# -- library browser -------------------------------------------------------------------------------
def test_library_dialog_lists_shows_and_adds(app, api, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))   # a modal would hang the run
    dlg = LibraryDialog(api, None, "surfaces")
    assert dlg.names.count() > 3
    items = dlg.names.findItems("gypsum_wall_25mm", Qt.MatchExactly)
    dlg.names.setCurrentItem(items[0])
    assert "GYP_BOARD" in dlg.fields.toPlainText() and dlg.new_name.text() == "GYPSUM_WALL_25MM"
    dlg.add_button.click()
    assert api.surfaces.get("GYPSUM_WALL_25MM") and api.materials.get("GYP_BOARD")
    assert "Added" in dlg.status.text()
    dlg.add_button.click()                                         # a second add is refused, nothing breaks
    assert len(api.surfaces.all()) == 1 and warned and "already exists" in warned[0]


def test_library_dialog_category_switch_and_filter(app, api):
    dlg = LibraryDialog(api)
    dlg.category.setCurrentIndex(dlg.category.findData("heat_detectors"))
    assert dlg.names.count() >= 2 and dlg.names.currentItem() is not None
    dlg.search.setText("74")
    assert [dlg.names.item(i).text() for i in range(dlg.names.count())] == ["heat_detector_74C"]
    dlg.search.setText("no such thing")
    assert dlg.names.count() == 0 and not dlg.add_button.isEnabled()


# -- run monitor -----------------------------------------------------------------------------------
def _fake_run(tmp_path, finished: bool, error: bool = False):
    out = tmp_path / "case.out"
    lines = ["Time Step 1", "  Step Size: 0.1 s, Total Time:    5.00000 s", "  Step Size: 0.1 s, Total Time:   10.00000 s"]
    if finished:
        lines.append("STOP: FDS completed successfully (CHID: case)")
    if error:
        lines.append("ERROR(101): Problem with MISC line.")
    out.write_text("\n".join(lines))
    (tmp_path / "case_hrr.csv").write_text("s,kW\nTime,HRR\n0.0,0.0\n5.0,40.0\n10.0,150.0\n")
    return tmp_path


def test_progress_and_hrr_readers(tmp_path):
    d = _fake_run(tmp_path, finished=False)
    assert read_progress(d / "case.out", 20.0) == (10.0, "running")
    assert read_progress(d / "missing.out", 20.0) == (0.0, "waiting")
    assert read_hrr(d / "case_hrr.csv") == [(0.0, 0.0), (5.0, 40.0), (10.0, 150.0)]
    assert read_hrr(d / "nope.csv") == []
    d2 = _fake_run(tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path, finished=True)
    assert read_progress(d2 / "case.out", 20.0) == (20.0, "done")
    assert read_progress(_fake_run(tmp_path, False, error=True) / "case.out", 20.0)[1] == "failed"


def test_run_monitor_shows_running_then_done(app, tmp_path):
    d = _fake_run(tmp_path, finished=False)
    mon = RunMonitorDialog(str(d), "case", 20.0, interval_ms=10_000)
    assert mon.headline.text() == "Running" and mon.bar.value() == 500
    assert "heat release now 150 kW" in mon.detail.text() and not mon.results_button.isEnabled()
    _fake_run(tmp_path, finished=True)
    mon.refresh()
    assert mon.headline.text() == "Finished" and mon.bar.value() == 1000 and mon.results_button.isEnabled()
    assert not mon.timer.isActive()


def test_run_monitor_before_fds_starts_and_after_failure(app, tmp_path):
    mon = RunMonitorDialog(str(tmp_path), "case", 20.0, interval_ms=10_000)
    assert mon.headline.text().startswith("Waiting") and mon.bar.value() == 0
    _fake_run(tmp_path, finished=False, error=True)
    mon.refresh()
    assert "error" in mon.headline.text() and not mon.results_button.isEnabled()


# -- results viewer --------------------------------------------------------------------------------
def test_results_viewer_plays_a_real_slice_file(app, api, tmp_path):
    shutil.copy(FIX / "slice_temperature_mesh1.sf", tmp_path / "case_1_1.sf")
    v = ResultsViewerDialog(api, None, str(tmp_path))
    assert v.layers.count() == 1 and v.slider.maximum() == 2 and v.image.pixmap() is not None
    assert "t = 0.0 s" in v.time_label.text()
    v.slider.setValue(2)
    assert "t = 10.0 s" in v.time_label.text() and v.vmax.value() > v.vmin.value()
    v._step(-1)
    assert "t = 5.0 s" in v.time_label.text()
    v._seek(0)
    v._toggle()
    assert v.play.text() == "Pause" and api.scene.playback.playing
    v._tick()
    v._toggle()
    assert v.play.text() == "Play"
    v.cmap.setCurrentText("viridis")
    v.auto.setChecked(False)
    v.vmin.setValue(0.0); v.vmax.setValue(500.0)
    assert v.image.pixmap() is not None
    v.px.setValue(0.5); v.py.setValue(0.6); v.pz.setValue(0.3)     # the slice is the plane y = 4 x 0.15 m
    assert "temperature" in v.probe_out.text()
    v.close()


def test_results_viewer_with_no_results_stays_quiet(app, api, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    v = ResultsViewerDialog(api, None)
    assert not v.slider.isEnabled()
    v.open_folder(str(tmp_path))
    assert shown and not v.slider.isEnabled()
    v.close()


# -- menu wiring -----------------------------------------------------------------------------------
def test_main_window_has_the_new_entries_and_no_placeholders_left_for_them(app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from pyfds.gui.main_window import MainWindow
    w = MainWindow(FdsApi())
    texts = {}

    def collect(menu_action):                       # top-level menus and the submenus folded into them (Draw, HVAC ...)
        menu = menu_action.menu()
        texts[menu_action.text().replace("&", "")] = [a.text().replace("&", "") for a in menu.actions()]
        for a in menu.actions():
            if a.menu() is not None:
                collect(a)
    for top in w.menuBar().actions():
        if top.menu():
            collect(top)
    assert "Draw Room (walls, door, window)..." in texts["Draw"]
    assert {"Library...", "Open Mesh Boundaries"} <= set(texts["Model"])
    assert "Results Viewer..." in texts["Results"]
    # Run > Monitor Simulation used to say "Coming Soon"; without a run it now explains what to do
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    for top in w.menuBar().actions():
        if top.text().replace("&", "") == "Analysis":
            for act in top.menu().actions():
                if act.text().replace("&", "") == "Monitor Simulation...":
                    act.trigger()
    assert shown and "Start a run first" in shown[0]
    w.close()
