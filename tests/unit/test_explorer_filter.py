"""Project Explorer: the filter box, and rebuilds that keep collapsed folders (review 2026-10-29, section 3.2)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from pyfds.api.facade import FdsApi


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app, monkeypatch):
    from pyfds.gui.main_window import MainWindow
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    w = MainWindow(FdsApi())
    w.api.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1), name="ROOM_MESH")
    w.api.obstructions.add_obstruction([0, 0.5, 0, 0.5, 0, 0.2], name="SOFA")
    w.api.obstructions.add_obstruction([0.5, 1, 0, 0.5, 0, 0.2], name="TABLE")
    yield w
    w.close()


def _visible_rows(explorer):
    return sorted(r.text(0) for r in explorer._iter_rows() if not r.isHidden())


def test_filter_box_shows_only_matching_objects(win):
    win.explorer_filter.setText("sofa")
    assert _visible_rows(win.explorer) == ["SOFA"]
    win.explorer_filter.setText("type:mesh")
    assert _visible_rows(win.explorer) == ["ROOM_MESH"]
    win.explorer_filter.clear()
    assert {"SOFA", "TABLE", "ROOM_MESH"} <= set(_visible_rows(win.explorer))


def test_filter_survives_a_model_change(win):
    win.explorer_filter.setText("sofa")
    win.api.obstructions.add_obstruction([0, 1, 0.5, 1, 0, 0.2], name="SOFA_2")
    assert _visible_rows(win.explorer) == ["SOFA", "SOFA_2"]


def test_collapsed_folder_stays_collapsed_after_a_change(win):
    heading = win.explorer.category_item("obstructions")
    heading.setExpanded(False)
    win.api.obstructions.add_obstruction([0, 1, 0.5, 1, 0, 0.2], name="CHAIR")
    heading = win.explorer.category_item("obstructions")
    assert heading.text(0).endswith("(3)") and not heading.isExpanded()
    assert win.explorer.category_item("meshes").isExpanded()
