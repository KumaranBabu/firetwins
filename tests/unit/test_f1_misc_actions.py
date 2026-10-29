"""F1: menu entries that used to be "Coming soon" - Add Control/Prop/Species, grid/axes/label toggles, Geometry Repair,
Export Geometry, Examples (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.core.viewport import VisibilityFlags  # noqa: E402
from pyfds.gui.editors.activation_controls import ActivationControlsDialog  # noqa: E402
from pyfds.gui.editors.collection_editor import EntityCollectionEditor  # noqa: E402
from pyfds.gui.examples_dialog import ExamplesDialog  # noqa: E402
from pyfds.gui.repair_dialog import GeometryRepairDialog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def w(monkeypatch):
    from pyfds.gui.main_window import MainWindow
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    win = MainWindow(FdsApi())
    yield win
    win.close()


def _menu(w, title):
    return next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == title)


def _texts(menu):
    return [a.text().replace("&", "") for a in menu.actions()]


def test_no_coming_soon_left_for_these_entries(w):
    from pyfds.gui.main_window.placeholders import PLACEHOLDERS
    gone = {"add_control", "add_prop", "add_species", "geometry_repair", "tools_geometry_repair", "toggle_grid",
            "toggle_axes", "device_labels", "export_stl", "examples"}
    assert not any(f"_on_placeholder_{g}" in PLACEHOLDERS for g in gone)


# -- Add Control / Prop / Species --------------------------------------------------------------------------------------
def test_add_species_prop_and_control_open_their_editors_with_a_new_object(w, monkeypatch):
    monkeypatch.setattr(EntityCollectionEditor, "exec", lambda self: 0)
    monkeypatch.setattr(ActivationControlsDialog, "exec", lambda self: 0)
    sp = w._on_add_species()
    assert sp.attr == "species" and len(w.api.species.all()) == 1 and sp.list.currentItem().text() == w.api.species.all()[0].name
    pr = w._on_add_prop()
    assert pr.attr == "props" and len(w.api.props.all()) == 1
    ct = w._on_add_control()
    assert len(w.api.controls.all()) == 1 and ct.list.currentItem().text() == w.api.controls.all()[0].name


def test_the_model_menu_entries_are_wired_to_them(w, monkeypatch):
    called = []
    monkeypatch.setattr(EntityCollectionEditor, "exec", lambda self: called.append(self.attr) or 0)
    monkeypatch.setattr(ActivationControlsDialog, "exec", lambda self: called.append("controls") or 0)
    model = _menu(w, "Model")
    for label in ("Add Control Element...", "Add Property / Prop...", "Add Species..."):
        next(a for a in model.actions() if a.text().replace("&", "") == label).trigger()
    assert called == ["controls", "props", "species"]


# -- toggles -----------------------------------------------------------------------------------------------------------
def test_grid_axes_and_label_toggles_drive_the_viewport_flags_and_follow_it(w):
    st = w.api.viewport.state
    assert st.is_visible(VisibilityFlags.AXES) and not st.is_visible(VisibilityFlags.GRID) \
        and not st.is_visible(VisibilityFlags.LABELS)                      # axes start on, grid and labels off
    assert w._axes_action.isChecked() and not w._grid_action.isChecked() and not w._device_labels_action.isChecked()
    w._grid_action.trigger()
    w._device_labels_action.trigger()
    w._axes_action.trigger()
    assert st.is_visible(VisibilityFlags.GRID) and st.is_visible(VisibilityFlags.LABELS) \
        and not st.is_visible(VisibilityFlags.AXES)
    w.api.viewport.set_visibility(VisibilityFlags.GRID, False)             # changed by a script or the agent
    assert not w._grid_action.isChecked()


# -- geometry repair -------------------------------------------------------------------------------------------------------
def _broken_shape(api):
    # two triangles sharing an edge plus a duplicate vertex position and one degenerate triangle
    from pyfds.domain.model import Geom
    g = Geom(name="bad", verts=[(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 0, 0), (2, 2, 2)],
             faces=[(0, 1, 2), (3, 1, 2), (4, 4, 4)])
    api.add_entity(g)
    return g


def test_repair_dialog_checks_repairs_and_undoes(w):
    g = _broken_shape(w.api)
    d = GeometryRepairDialog(w.api, w, "bad")
    assert d.current() == "bad" and d.report.toPlainText().strip()
    before = len(g.faces)
    report = d.run_repair()
    assert report is not None and len(g.faces) < before and "repaired" in d.status.text()
    assert "after repair" in d.report.toPlainText()
    w.api.history.undo()
    assert len(g.faces) == before
    d.close()


def test_repair_dialog_with_nothing_to_repair(w):
    d = GeometryRepairDialog(w.api, w)
    assert d.current() is None and not d.repair_button.isEnabled() and d.run_repair() is None
    assert "no imported" in d.report.toPlainText()
    d.close()


def test_geometry_repair_menu_entries_open_the_dialog_on_the_selected_shape(w, monkeypatch):
    seen = []
    monkeypatch.setattr(GeometryRepairDialog, "exec", lambda self: seen.append(self.current()) or 0)
    g = _broken_shape(w.api)
    w.explorer.select_entity("geom", g)
    next(a for a in _menu(w, "Tools").actions() if a.text().replace("&", "") == "Geometry Repair...").trigger()
    assert seen == ["bad"]
    assert not [a for a in _menu(w, "Model").actions() if a.text().replace("&", "") == "Geometry Repair..."]   # once, in Tools


# -- export ---------------------------------------------------------------------------------------------------------------
def test_export_geometry_writes_stl_and_obj_and_refuses_when_empty(w, tmp_path):
    assert w._on_export_geometry(str(tmp_path / "x.stl")) == 0                 # nothing to export: a message, no file
    assert not (tmp_path / "x.stl").exists()
    w.api.geom.box([0, 1, 0, 1, 0, 1])
    w.api.obstructions.add_obstruction([2, 3, 0, 1, 0, 1])
    n = w._on_export_geometry(str(tmp_path / "a.stl"), include_obstructions=False)
    m = w._on_export_geometry(str(tmp_path / "b.obj"), include_obstructions=True)
    assert n == 12 and m == 24 and (tmp_path / "a.stl").exists() and (tmp_path / "b.obj").exists()
    assert w._on_export_geometry(str(tmp_path / "c.txt"), include_obstructions=False) == 0      # unknown format: refused


def test_file_export_menu_entry_is_real(w):
    action = w.action_registry.action("file.export.stl")
    assert "Coming" not in action.text() and action.isEnabled()


# -- examples -------------------------------------------------------------------------------------------------------------
def test_examples_dialog_lists_and_opens_one_replacing_the_project(w, monkeypatch):
    w.api.meshes.add_mesh([5, 5, 5], [0, 1, 0, 1, 0, 1], name="mine")
    d = ExamplesDialog(w.api, w)
    assert d.list.count() >= 3 and d.about.text()
    answers = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: answers.append(a[1]) or QMessageBox.No)
    assert d.open_selected() is None and answers and w.api.meshes.get("mine") is not None      # said no: untouched
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    info = d.open_selected()
    assert info["title"] and w.api.meshes.get("mine") is None and len(w.api.meshes.all()) >= 1
    assert w.api.history.can_undo() is False                                    # the example is the starting point
    d.close()


def test_examples_help_entry_sets_status_and_clears_the_path(w, monkeypatch):
    monkeypatch.setattr(ExamplesDialog, "exec", lambda self: self.open_selected(confirm=False) and 1 or 0)
    w._current_project_path = "old.pyfds"
    w._on_examples()
    assert w._current_project_path is None and "Opened example" in w.statusBar().currentMessage()
