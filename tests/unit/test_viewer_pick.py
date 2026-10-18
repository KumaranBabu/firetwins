"""Click-picking in the 3D view: what is under the pointer is described, highlighted, and selected in the tree."""
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
import vtk
from PySide6.QtWidgets import QApplication, QMessageBox

from pyfds.api.facade import FdsApi
from pyfds.api.viz import pick
from pyfds.api.viz import GeometryBoxes, GridSurface, RectilinearVolume, TriMesh
from pyfds.gui.results.window import ResultsWindow

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"
SL = "root/FDS Results/2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1"
BURNER = (1.35, 1.5, 0.15)                       # the centre of the top of the BURNER block in the fixture


def test_describe_box_prefers_the_smallest_box_and_names_it():
    g = GeometryBoxes("Obstructions", [(0, 4, 0, 4, 0, 0.2), (1, 2, 1, 2, 0.2, 0.5)], ["FLOOR", "BURNER"], kind="obstruction")
    on_burner = pick.describe("geometry/x", "Obstructions", g, (1.5, 1.5, 0.5))
    assert on_burner.label == "BURNER" and on_burner.box == (1, 2, 1, 2, 0.2, 0.5) and "BURNER" in on_burner.text
    on_floor = pick.describe("geometry/x", "Obstructions", g, (3, 3, 0.2))
    assert on_floor.label == "FLOOR"
    miss = pick.describe("geometry/x", "Obstructions", g, (9, 9, 9))
    assert miss.box is None and miss.kind == "obstruction"


def test_describe_values_on_slice_volume_and_isosurface():
    x = np.array([[0.0, 1.0], [0.0, 1.0]])
    y = np.zeros((2, 2))
    z = np.array([[0.0, 0.0], [1.0, 1.0]])
    s = pick.describe("n", "slice", GridSurface("s", "TEMPERATURE", "C", x, y, z, np.array([[10.0, 20.0], [30.0, 40.0]])), (0.9, 0, 0.9))
    assert s.value == 40.0 and s.units == "C" and "TEMPERATURE = 40" in s.text
    ax = np.array([0.0, 1.0])
    vol = RectilinearVolume("v", "TEMPERATURE", "C", ax, ax, ax, np.fromfunction(lambda i, j, k: 100.0 * i, (2, 2, 2)))
    assert pick.describe("n", "v", vol, (0.25, 0.5, 0.5)).value == pytest.approx(25.0)
    assert pick.describe("n", "v", vol, (5, 5, 5)).value is None
    tri = TriMesh("i", "TEMPERATURE", "C", np.zeros((3, 3)), np.array([[0, 1, 2]]), None, 300.0)
    assert pick.describe("n", "i", tri, (0, 0, 0)).value == 300.0


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app, tmp_path, monkeypatch):
    shutil.copytree(FIX, tmp_path / "r")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    w = ResultsWindow(FdsApi())
    w.viewer.open_results(str(tmp_path / "r" / "rroom.smv"))
    w.viewer.activate("geometry/fds_actual")
    w.sync(True)
    w.view.plotter.render()
    w.view.plotter.screenshot(return_img=True)       # a real render, so the picker has a depth buffer
    yield w
    w.close()


def display(win, pt):
    c = vtk.vtkCoordinate()
    c.SetCoordinateSystemToWorld()
    c.SetValue(*pt)
    return [int(v) for v in c.GetComputedDoubleDisplayValue(win.view.plotter.renderer)[:2]]


def test_click_selects_the_object_highlights_it_and_selects_the_tree_row(win):
    info = win.pick_at(*display(win, BURNER))
    assert info is not None and info.label == "BURNER" and info.kind == "obstruction"
    assert win.selected is info and "BURNER" in win.statusBar().currentMessage()
    assert "pick_highlight" in win.view.plotter.renderer.actors
    assert win.tree.currentItem() is win.tree.item_for("geometry/fds_actual")
    win.sync()                                        # a redraw keeps the highlight
    assert "pick_highlight" in win.view.plotter.renderer.actors


def test_click_on_empty_space_and_escape_clear_the_selection(win):
    win.pick_at(*display(win, BURNER))
    assert win.pick_at(2, 2) is None
    assert win.selected is None and "pick_highlight" not in win.view.plotter.renderer.actors
    win.pick_at(*display(win, BURNER))
    win.select(None)
    assert win.selected is None and win.statusBar().currentMessage() == "Nothing selected"


def test_open_boundary_faces_do_not_steal_clicks_and_a_slice_reports_its_value(win):
    win.viewer.activate(SL)
    win.sync()
    win.view.plotter.render()
    win.view.plotter.screenshot(return_img=True)
    hits = {win.pick_at(x, y) and win.selected.kind for x in range(40, 760, 40) for y in range(20, 480, 40)}
    assert "open_vent" not in hits and "mesh" not in hits
    assert "slice" in hits or "obstruction" in hits
    sl = [i for i in (win.pick_at(x, y) for x in range(40, 760, 20) for y in range(20, 480, 20)) if i and i.kind == "slice"]
    assert sl and sl[0].value is not None and "TEMPERATURE" in sl[0].text


def test_a_rebuilt_tree_forgets_the_selection(win):
    win.pick_at(*display(win, BURNER))
    win.sync(True)
    assert win.selected is None and win.view.adapter.selection is None


def test_ctrl_click_adds_to_the_selection_and_ctrl_click_again_removes_it(win):
    first = win.pick_at(*display(win, BURNER))
    other = pick.PickInfo("geometry/fds_actual", "obstruction", "WALL", (0, 0, 0), "WALL", box=(0, 0.2, 0, 0.2, 0, 0.2))
    win.select(other, add=True)
    assert win.view.adapter.selections == [first, other]
    actors = win.view.plotter.renderer.actors
    assert "pick_highlight" in actors and "pick_highlight_1" in actors
    assert "2 objects selected" in win.statusBar().currentMessage()
    win.select(other, add=True)                      # the same object again: out of the selection
    assert win.view.adapter.selections == [first]
    assert "pick_highlight_1" not in win.view.plotter.renderer.actors
    win.select(None)
    assert win.view.adapter.selections == [] and "pick_highlight" not in win.view.plotter.renderer.actors


def test_a_plain_click_replaces_the_selection_and_a_ctrl_miss_keeps_it(win):
    first = win.pick_at(*display(win, BURNER))
    assert win.pick_at(2, 2, add=True) is None and win.view.adapter.selections == [first]
    win.select(pick.PickInfo("geometry/fds_actual", "obstruction", "X", (0, 0, 0), "X", box=(0, 1, 0, 1, 0, 1)), add=True)
    again = win.pick_at(*display(win, BURNER), add=False)
    assert win.view.adapter.selections == [again]
