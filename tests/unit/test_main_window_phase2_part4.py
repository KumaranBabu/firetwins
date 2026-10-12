"""Automated regression coverage for the Phase 2 menu handlers (both wiring (part 4 of 4)."""


from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from tests.mw_proxy import main_window_mod as mw  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app

def _make_window():
    from pyfds.gui.main_window import MainWindow
    from pyfds.api import FdsApi
    return MainWindow(FdsApi())

class _FakeDialog:
    """Generic SchemaFormDialog stand-in — records the schema it was built
    with (so tests can assert on pre-filled defaults) and returns a fixed
    values() dict on exec()."""

    last_schema = None

    def __init__(self, title, description, schema, parent=None):
        self.title = title
        self.schema = schema
        _FakeDialog.last_schema = schema

    def exec(self):
        return QDialog.Accepted

    def values(self):
        return self._values

    _values: dict = {}

def _fake_dialog_returning(values: dict):
    class _D(_FakeDialog):
        _values = values
    return _D


def test_boolean_union_requires_exactly_two_geoms(monkeypatch):
    window = _make_window()
    from pyfds.domain.geometry_tools import GeometryTools
    a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="a")
    window.api.project.add_entity(a)
    window.explorer.refresh()
    window.explorer.select_entities([("geom", a)])

    informed = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_boolean_union()
    assert informed
    assert len(window.api.geom.all()) == 1  # no result added
    window.close()

def test_boolean_union_adds_new_geom_keeping_sources(monkeypatch):
    window = _make_window()
    from pyfds.domain.geometry_tools import GeometryTools
    a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="a")
    b = GeometryTools.box_geom([1, 3, 1, 3, 1, 3], name="b")
    window.api.project.add_entity(a)
    window.api.project.add_entity(b)
    window.explorer.refresh()
    window.explorer.select_entities([("geom", a), ("geom", b)])

    window._on_boolean_union()

    all_geoms = window.api.geom.all()
    assert len(all_geoms) == 3  # a, b, and the new union — sources kept
    assert a in all_geoms and b in all_geoms
    window.close()

def test_boolean_difference_and_intersection_also_add_new_geom(monkeypatch):
    window = _make_window()
    from pyfds.domain.geometry_tools import GeometryTools
    a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="a")
    b = GeometryTools.box_geom([1, 3, 1, 3, 1, 3], name="b")
    window.api.project.add_entity(a)
    window.api.project.add_entity(b)
    window.explorer.refresh()

    window.explorer.select_entities([("geom", a), ("geom", b)])
    window._on_boolean_difference()
    assert len(window.api.geom.all()) == 3

    window.explorer.select_entities([("geom", a), ("geom", b)])
    window._on_boolean_intersection()
    assert len(window.api.geom.all()) == 4
    window.close()

def test_boolean_union_shows_error_for_non_manifold_geom(monkeypatch):
    window = _make_window()
    from pyfds.domain.geometry_tools import GeometryTools
    a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="open_a")
    a.faces = a.faces[:-2]
    b = GeometryTools.box_geom([1, 3, 1, 3, 1, 3], name="b")
    window.api.project.add_entity(a)
    window.api.project.add_entity(b)
    window.explorer.refresh()
    window.explorer.select_entities([("geom", a), ("geom", b)])

    critical = []
    monkeypatch.setattr(mw.QMessageBox, "critical", lambda *a, **k: critical.append(1))
    window._on_boolean_union()
    assert critical
    assert len(window.api.geom.all()) == 2  # no result added
    window.close()

def test_group_selection_transforms_as_one_rigid_unit(monkeypatch):
    # Selecting only one grouped entity must expand to the whole group —
    # this is what makes Group/Ungroup useful for transforms, not just an
    # Explorer-tree decoration.
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 2, 0, 2, 0, 1], name="a")
    b = window.api.obstructions.add_obstruction(xb=[4, 6, 0, 2, 0, 1], name="b")
    window.api.groups.create("G1")
    window.api.groups.assign(a, "G1")
    window.api.groups.assign(b, "G1")
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", a)])  # only 'a' selected

    monkeypatch.setattr(
        mw, "SchemaFormDialog", _fake_dialog_returning({"dx": 10.0, "dy": 0.0, "dz": 0.0})
    )
    window._on_move_selected()

    assert a.x_min == pytest.approx(10.0)
    assert b.x_min == pytest.approx(14.0)  # 'b' moved too, via group expansion
    window.close()
