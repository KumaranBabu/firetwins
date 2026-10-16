"""F1: split views, Print, and Hardware & Graphics Settings (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.graphics_dialog import AA_MODES, SETTING_KEY, HardwareSettingsDialog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def w(monkeypatch):
    from pyfds.gui.main_window import MainWindow
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    win = MainWindow(FdsApi())
    win.api.meshes.add_mesh([10, 10, 10], [0, 4, 0, 3, 0, 3], name="M")
    win.api.obstructions.add_obstruction([1, 2, 1, 2, 0, 1], name="TABLE")
    yield win
    win.close()


def _menu(w, title):
    return next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == title)


# -- no placeholders left ---------------------------------------------------------------------------------------------------
def test_there_is_no_coming_soon_entry_anywhere(w):
    from pyfds.gui.main_window.placeholders import PLACEHOLDERS
    assert PLACEHOLDERS == {}
    seen = []

    def walk(menu):
        for a in menu.actions():
            if a.menu() is not None:
                walk(a.menu())
            elif a.text():
                seen.append(a)
    for top in w.menuBar().actions():
        walk(top.menu())
    assert len(seen) > 150
    assert not [a.text() for a in seen if "coming soon" in a.text().lower()]


# -- split views ----------------------------------------------------------------------------------------------------------------
def test_split_starts_single_with_the_3d_view_in_a_fixed_place(w):
    assert w.split_mode == "single" and w.split_panes() == []
    assert w.model_top.widget(0) is w.viewport_widget and w.model_split.widget(0) is w.model_top
    assert w._split_actions["single"].isChecked()


def test_horizontal_and_vertical_add_one_plan_beside_or_below(w):
    w.set_split_mode("horizontal")
    assert len(w.split_panes()) == 1 and w.model_top.orientation() == Qt.Horizontal and w.model_top.count() == 2
    plan = w.split_panes()[0]
    assert any(s.kind == "obstruction" for s in plan.view._shapes)               # it shows the model
    w.set_split_mode("vertical")
    assert len(w.split_panes()) == 1 and w.model_top.orientation() == Qt.Vertical and w.model_top.count() == 2
    assert w.split_panes()[0] is not plan                                        # the old pane was replaced, not stacked
    assert w.model_top.widget(0) is w.viewport_widget                            # the 3D view never moved


def test_four_way_has_two_plans_a_record_view_and_the_3d_view(w):
    w.set_split_mode("four")
    kinds = [type(p).__name__ for p in w.split_panes()]
    assert sorted(kinds) == ["PlanPanel", "PlanPanel", "RecordView"]
    assert w.model_split.count() == 2 and w.model_top.count() == 2
    plans = [p for p in w.split_panes() if type(p).__name__ == "PlanPanel"]
    w.api.floors.define_floor("L2", 3.0, 6.0)
    plans[1].set_floor("L2")                                                     # each plan has its own level
    assert plans[0].view.level == 0.0 and plans[1].view.level == 3.0


def test_the_3d_view_gets_the_larger_share_of_the_room(w):
    w.resize(2600, 1100)                                  # wide enough that the docks leave room for a 60/40 split
    w.show()
    QApplication.processEvents()
    w.set_split_mode("horizontal")
    QApplication.processEvents()
    a, b = w.model_top.sizes()
    assert a > b and a / (a + b) == pytest.approx(0.6, abs=0.05)
    w.set_split_mode("four")
    QApplication.processEvents()
    top, bottom = w.model_split.sizes()
    assert top > bottom and w.model_top.sizes()[0] > w.model_top.sizes()[1] and w._split_bottom.sizes()[0] > w._split_bottom.sizes()[1]


def test_a_plan_beside_the_3d_view_does_not_force_the_window_wide(w):
    w.resize(1500, 900)
    w.show()
    QApplication.processEvents()
    before = w.width()
    w.set_split_mode("horizontal")
    for _ in range(3):
        QApplication.processEvents()
    assert w.width() <= before + 50                                                # it fits; the plan's controls are compact
    assert w.split_panes()[0].minimumSizeHint().width() < 500


def test_going_back_to_single_removes_every_extra_pane_and_stops_their_updates(w):
    w.set_split_mode("four")
    panes = w.split_panes()
    w.set_split_mode("single")
    assert w.split_panes() == [] and w.model_top.count() == 1 and w.model_split.count() == 1
    assert all(p.parent() is None for p in panes)
    w.api.obstructions.add_obstruction([2, 3, 2, 3, 0, 1], name="LATER")          # a model change must not reach dead panes


def test_split_menu_stays_in_step_and_rejects_nonsense(w):
    split = next(a.menu() for a in _menu(w, "View").actions() if a.menu() is not None and a.text().replace("&", "") == "Split")
    labels = [a.text() for a in split.actions()]
    assert labels[0] == "Single View" and len(labels) == 4
    split.actions()[3].trigger()
    assert w.split_mode == "four" and w._split_actions["four"].isChecked() and not w._split_actions["single"].isChecked()
    split.actions()[0].trigger()
    assert w.split_mode == "single"
    with pytest.raises(ValueError):
        w.set_split_mode("diagonal")
    assert w.set_split_mode("single") == "single"                                 # no change is a no-op


def test_selection_in_the_tree_reaches_the_plans_in_the_split(w):
    w.set_split_mode("horizontal")
    table = w.api.obstructions.get("TABLE")
    w.explorer.select_entity("obstructions", table)
    assert id(table) in w.split_panes()[0].view._selected
    w.split_panes()[0].view.click_at((1.5, 1.5))                                  # and a click in the plan reaches the tree
    assert w.explorer.selected()[1] is table


def test_closing_the_window_with_a_split_open_is_clean(monkeypatch):
    from pyfds.gui.main_window import MainWindow
    win = MainWindow(FdsApi())
    win.set_split_mode("four")
    win.close()


# -- print ------------------------------------------------------------------------------------------------------------------------
def test_print_to_pdf_for_each_kind_of_tab(w, tmp_path):
    # no 3D view here, so the model tab prints the FDS input as text
    kind, payload, title = w._print_content()
    assert kind == "text" and "&MESH" in payload and title.endswith("Model")
    f = tmp_path / "model.pdf"
    w.print_to_pdf(str(f))
    assert f.exists() and f.read_bytes()[:5] == b"%PDF-" and f.stat().st_size > 1000
    rec = w.show_record_tab()
    assert w._print_content()[0] == "text" and "TABLE" in w._print_content()[1] and w._print_content()[2].endswith("Record")
    plan = w.show_plan_tab()
    plan.view.fit()
    kind, img, title = w._print_content()
    assert kind == "image" and isinstance(img, QImage) and not img.isNull() and title.endswith("2D")
    g = tmp_path / "plan.pdf"
    w.print_to_pdf(str(g))
    assert g.exists() and g.stat().st_size > 1000
    assert rec is not None


def test_print_menu_entry_opens_a_preview(w, monkeypatch):
    from PySide6.QtPrintSupport import QPrintPreviewDialog
    opened = []
    monkeypatch.setattr(QPrintPreviewDialog, "exec", lambda self: opened.append(self) or 0)
    w.action_registry.action("file.print").trigger()
    assert len(opened) == 1 and "Coming" not in w.action_registry.action("file.print").text()


# -- hardware and graphics -----------------------------------------------------------------------------------------------------------
class FakeSettings:
    def __init__(self):
        self.data = {}

    def value(self, key, default=None):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.data[key] = value


class FakeViewport:
    def __init__(self):
        self.aa = None

    def opengl_info(self):
        return {"vendor": "Acme", "renderer": "Acme GPU 9000", "version": "4.6"}

    def set_antialiasing(self, mode):
        self.aa = mode


@pytest.fixture
def hw_api():
    from pyfds.core.config import get_config
    api = FdsApi()
    keep = get_config().get("default_mpi_processes")
    yield api
    if keep is not None:
        api.preferences.set("default_mpi_processes", keep)


def test_hardware_dialog_shows_the_current_values_and_the_graphics_card(hw_api):
    vp = FakeViewport()
    d = HardwareSettingsDialog(hw_api, vp, None, FakeSettings(), cpu_count=8)
    assert d.openmp.value() == 0 and d.openmp.specialValueText() == "Automatic"
    assert "Acme GPU 9000" in d.graphics.text() and "OpenGL 4.6" in d.graphics.text()
    assert d.antialiasing() == "off" and [d.aa.itemData(i) for i in range(d.aa.count())] == [k for k, _ in AA_MODES]
    d.close()


def test_hardware_dialog_applies_threads_mpi_and_antialiasing(hw_api):
    vp, st = FakeViewport(), FakeSettings()
    d = HardwareSettingsDialog(hw_api, vp, None, st)
    d.openmp.setValue(4)
    d.mpi.setValue(6)
    d.aa.setCurrentIndex(d.aa.findData("msaa4"))
    assert d.apply() == {"openmp_threads": 4, "default_mpi_processes": 6, "antialiasing": "msaa4"}
    assert hw_api.project.misc.openmp_threads == 4 and hw_api.preferences.get("default_mpi_processes") == 6
    assert vp.aa == "msaa4" and st.data[SETTING_KEY] == "msaa4"
    hw_api.history.undo()
    assert hw_api.project.misc.openmp_threads is None                              # the thread count is an undo step
    d.openmp.setValue(3)
    assert d.apply() == {"openmp_threads": 3}
    d.openmp.setValue(0)                                                           # back to Automatic
    assert d.apply() == {"openmp_threads": None} and hw_api.project.misc.openmp_threads is None
    assert d.apply() == {}                                                         # nothing changed: nothing saved
    d.close()


def test_hardware_dialog_remembers_the_antialiasing_and_survives_a_dead_driver(hw_api):
    st = FakeSettings()
    st.setValue(SETTING_KEY, "fxaa")
    assert HardwareSettingsDialog(hw_api, FakeViewport(), None, st).antialiasing() == "fxaa"

    class Broken(FakeViewport):
        def opengl_info(self):
            raise RuntimeError("driver crashed")
    d = HardwareSettingsDialog(hw_api, Broken(), None, FakeSettings())
    assert "could not be read" in d.graphics.text()
    assert "not available" in HardwareSettingsDialog(hw_api, None, None, FakeSettings()).graphics.text()
    d.close()


def test_hardware_menu_entry_is_real(w, monkeypatch):
    opened = []
    monkeypatch.setattr(HardwareSettingsDialog, "exec", lambda self: opened.append(self) or 0)
    entry = next(a for a in _menu(w, "Analysis").actions() if "Hardware" in a.text())
    assert "Graphics" in entry.text() and "GPU" not in entry.text()
    entry.trigger()
    assert len(opened) == 1
