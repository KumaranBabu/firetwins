"""UI-30: right-click menus in the plan and the 3D view's input filter, driven with real Qt events (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.main_window import MainWindow  # noqa: E402
from pyfds.gui.plan import PlanView  # noqa: E402
from pyfds.gui.viewport_input import install_input  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh([20, 20, 10], [0, 10, 0, 10, 0, 3], name="M")
    a.obstructions.add_obstruction([2, 4, 2, 4, 0, 2], name="box")
    return a


@pytest.fixture
def view(api):
    v = PlanView(api)
    v.resize(800, 600)
    v.show()
    v.fit()
    got = []
    v.context_requested.connect(lambda e, p: got.append(e))
    v.got = got
    yield v
    v.shutdown()
    v.close()


def right_click(view, x, y):
    QTest.mouseClick(view.viewport(), Qt.RightButton, Qt.NoModifier, view.widget_pos_of(x, y))


def test_plan_right_click_reports_the_object_under_the_cursor(view):
    right_click(view, 3, 3)
    right_click(view, 8, 8)
    assert view.got[0][0] == "obstructions" and view.got[0][1].name == "box"
    assert view.got[1] is None or view.got[1][0] == "meshes"          # nothing but the mesh floor out there


def test_plan_right_drag_still_pans_and_opens_no_menu(view):
    p0 = view.widget_pos_of(5, 5)
    QTest.mousePress(view.viewport(), Qt.RightButton, Qt.NoModifier, p0)
    QTest.mouseMove(view.viewport(), p0 + QPoint(40, 30))
    QTest.mouseRelease(view.viewport(), Qt.RightButton, Qt.NoModifier, p0 + QPoint(40, 30))
    assert view.got == []


def test_input_filter_calls_back_for_a_right_click_only_when_it_did_not_drag():
    class Iren(QWidget):
        pass

    class Plotter:
        interactor = Iren()

    calls = []
    keep = install_input(Plotter, lambda *a: None, lambda *a: None, lambda *a: False,
                         on_context=lambda x, y, gp: calls.append((x, y)))
    w = Plotter.interactor
    w.resize(200, 100)
    w.show()
    QTest.mouseClick(w, Qt.RightButton, Qt.NoModifier, QPoint(20, 30))
    assert len(calls) == 1 and calls[0][0] == 20
    QTest.mousePress(w, Qt.RightButton, Qt.NoModifier, QPoint(20, 30))
    QTest.mouseRelease(w, Qt.RightButton, Qt.NoModifier, QPoint(90, 60))
    assert len(calls) == 1
    assert isinstance(keep, QObject)


def texts(menu):
    return [a.text().replace("&", "") for a in menu.actions() if not a.isSeparator()]


def test_menu_for_an_object_is_the_navigation_tree_menu_and_selects_it(api):
    win = MainWindow(api)
    box = api.obstructions.all()[0]
    menu = win._build_view_context_menu(("obstructions", box))
    assert "Properties..." in texts(menu) and "Delete" in texts(menu)
    assert win.explorer.selected()[1] is box                           # the right-clicked object became the selection


def test_menu_for_empty_space_has_view_commands_and_for_a_drawing_has_finish_cancel(api):
    win = MainWindow(api)
    assert texts(win._build_view_context_menu(None)) == ["Select All", "Show All", "Paste", "Reset View"]
    win.tool_manager.activate("obstruction")
    assert "Select Tool" in texts(win._build_view_context_menu(None))
    win.tool_manager.click(__import__("pyfds.gui.viewport_tools", fromlist=["Hit"]).Hit((1, 1, 0)))
    assert win.tool_manager.current.active()
    assert texts(win._build_view_context_menu(None)) == ["Finish", "Cancel Drawing"]
    next(a for a in win._build_view_context_menu(None).actions() if "Cancel" in a.text()).trigger()
    assert not win.tool_manager.current.active()


def test_the_window_listens_to_the_plan_it_creates(api, monkeypatch):
    win = MainWindow(api)
    shown = []

    class Stub:
        def exec(self, pos):
            shown.append(pos)

    built = []
    monkeypatch.setattr(win, "_build_view_context_menu", lambda e: built.append(e) or Stub())
    plan = win.show_plan_tab()
    plan.context_requested.emit(None, QPoint(5, 6))
    assert built == [None] and shown == [QPoint(5, 6)]
