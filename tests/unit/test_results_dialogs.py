"""Results dialogs built on the real fixture: screenshot / movie plans, section box, tour editor, skybox, settings panels."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from pyfds.api.facade import FdsApi
from pyfds.gui.results import dialogs
from pyfds.gui.results.window import ResultsWindow

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"
SL = "root/FDS Results/2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1"


@pytest.fixture()
def win(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    shutil.copytree(FIX, tmp_path / "r")
    msgs = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: msgs.append(a[2]))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    w = ResultsWindow(FdsApi())
    w.msgs = msgs
    w.open_results(str(tmp_path / "r" / "rroom.smv"))
    w._toggle(SL)
    yield w
    w.close()


def test_screenshot_dialog_plans_single_multiple_and_file(win, tmp_path):
    d = dialogs.ScreenshotDialog(win.viewer, win, (400, 300))
    d.path.setText(str(tmp_path / "s.png"))
    d.mode.setCurrentText("single")
    d.time.setValue(2.0)
    (s,) = d.shots()
    assert s.time == 2.0 and d.size() == (400, 300)
    d.mode.setCurrentText("multiple")
    d.start.setValue(0)
    d.end.setValue(4)
    d.step.setValue(2)
    assert [x.time for x in d.shots()] == [0, 2, 4]
    (tmp_path / "t.tsv").write_text("1\t<current view>\n3\t<current view>\n")
    d.mode.setCurrentText("file")
    d.tsv.setText(str(tmp_path / "t.tsv"))
    assert len(d.shots()) == 2


def test_movie_dialog_plan_uses_window_size_or_custom(win, tmp_path):
    d = dialogs.MovieDialog(win.viewer, win, (1001, 601))
    d.path.setText(str(tmp_path / "m.mp4"))
    d.begin.setValue(0)
    d.end.setValue(2)
    d.fps.setValue(5)
    p = d.plan()
    assert p.size == (1000, 600) and len(p.times) == 11
    d.use_window.setChecked(False)
    d.w.setValue(640)
    d.h.setValue(360)
    assert d.plan().size == (640, 360)


def test_section_box_dialog_applies_all_planes_or_none(win):
    win.viewer.add_section_box()
    d = dialogs.SectionBoxDialog(win.viewer, win)
    chk, val = d.rows["x_min"]
    chk.setChecked(True)
    val.setValue(0.4)
    d.apply()
    assert win.viewer.active_leaves() and dict(__import__("pyfds.api.viz", fromlist=["views"]).views.active_section(win.viewer.viz).active()) == {"x_min": 0.4}
    chk2, val2 = d.rows["x_max"]
    chk2.setChecked(True)
    val2.setValue(0.1)                              # below x_min: rejected as a whole
    with pytest.raises(ValueError):
        d.apply()
    assert list(__import__("pyfds.api.viz", fromlist=["views"]).views.active_section(win.viewer.viz).active()) == ["x_min"]
    win.viewer.remove_section_box()
    with pytest.raises(ValueError):
        dialogs.SectionBoxDialog(win.viewer, win)


def test_tour_editor_add_shift_duplicate_remove(win):
    win.viewer.new_tour("Orbit")
    ed = dialogs.TourEditor(win.viewer, "Orbit", win)
    win.viewer.set_time(0.0)
    ed.add()
    win.viewer.set_camera(win.viewer.standard_view("top"))
    win.viewer.add_keyframe(4.0, "Orbit")
    ed.reload()
    assert ed.table.rowCount() == 2
    ed.table.selectRow(1)
    win.viewer.shift_keyframes([1], offset=1.0, view="Orbit")
    ed.reload()
    assert ed.table.item(1, 0).text() == "5"
    ed.table.item(1, 1).setText("stationary")
    ed.commit_table()
    assert win.viewer.viz.view("Orbit").tour.keyframes[1].transition == "stationary"
    ed.table.selectRow(0)
    win.viewer.duplicate_keyframes([0], "end_of_tour", last_delay=2.0, view="Orbit")
    with pytest.raises(ValueError):
        win.viewer.duplicate_keyframes([0], "end_of_tour", last_delay=0.0, view="Orbit")
    ed.reload()
    assert ed.table.rowCount() == 3
    ed.remove()
    ed.reload()
    assert ed.table.rowCount() == 2


def test_skybox_dialog_validates_file_count(win):
    d = dialogs.SkyboxDialog(win.viewer, win)
    d.kind.setCurrentText("image360")
    with pytest.raises(ValueError):
        win.viewer.set_skybox(**d.values())          # needs one image
    d.kind.setCurrentText("none")
    win.viewer.set_skybox(**d.values())


def test_context_menu_actions_and_delete_key(win):
    from pyfds.gui.results import parity
    g = "root/FDS Results/3D Slices/TEMPERATURE"
    win.viewer.activate("root/FDS Results/3D Slices/TEMPERATURE/T_3D/Mesh 1")
    win.viewer.add_data3d_point(g, (0.5, 1.0, 1.0))
    win.sync(True)
    leaf = next(l for l in win.viewer.tree.leaves() if l.kind == "data3d_point")
    parity._delete_node(win, leaf.id)
    win.sync(True)
    assert not win.viewer.viz.data3d_points
    win.viewer.add_dimension((0, 0, 0), (1, 0, 0))
    win.sync(True)
    parity._delete_node(win, "dimension/0")
    assert not win.viewer.viz.dimensions
    assert win.viewer.cache_frames([SL]) > 3


def test_status_bar_follows_playback(win):
    win._seek(3)
    assert win.status_time.text() != "0:00.0" and win.status_state.text() in ("Paused", "Stopped", "Playing")
    win.speed.setValue(2.0)
    assert win.status_speed.text() == "x2"


def test_time_plot_types_and_save(win, tmp_path):
    from pyfds.gui.results.plots import TimePlotDialog
    win.viewer.load_csv(str(win.viewer.run.directory / "rroom_hrr.csv"))
    d = TimePlotDialog(win.viewer, win)
    for i in range(d.list.count()):
        if d.list.item(i).text().endswith("HRR"):
            d.list.item(i).setCheckState(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Checked)
    for kind in ("Line", "Stem", "Step"):
        d.kind.setCurrentText(kind)
    out = d.save_image(str(tmp_path / "p.png"))
    assert Path(out).stat().st_size > 1000


def test_rendering_dialog_presets(win, monkeypatch):
    from PySide6.QtWidgets import QDialog, QPushButton
    seen = {}

    def fake_exec(self):
        seen["buttons"] = [b.text() for b in self.findChildren(QPushButton)]
        next(b for b in self.findChildren(QPushButton) if b.text() == "Max Compatibility").click()
        return 0
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    win.rendering_prefs()
    assert "Max Quality" in seen["buttons"] and win.viewer.viz.rendering.antialiasing == "disabled"
