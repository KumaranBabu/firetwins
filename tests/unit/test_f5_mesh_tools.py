"""F5: mesh division readout and mesh tools in the Edit Meshes dialog (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.editors.collection_editor import EntityCollectionEditor  # noqa: E402
from pyfds.gui.editors.mesh_tools import MeshToolsMixin, poisson_counts  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh([20, 10, 10], [0, 4, 0, 2, 0, 2], name="A")
    return a


@pytest.fixture
def ed(api, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    e = EntityCollectionEditor(api, "meshes", "Edit Meshes")
    yield e
    e.close()


def test_partition_backend_makes_equal_slabs_and_one_undo(api):
    pieces = api.meshes.partition("A", 4)
    assert [m.cell_count[0] for m in pieces] == [5, 5, 5, 5]
    assert pieces[-1].x_max == pytest.approx(4.0) and len(api.meshes.all()) == 4
    assert all(v == "Passed" for v in api.meshes.alignment_test().values())
    api.history.undo()
    assert len(api.meshes.all()) == 1 and api.meshes.get("A").cell_count == (20, 10, 10)


def test_partition_refuses_too_many_parts(api):
    with pytest.raises(ValueError):
        api.meshes.partition("A", 30, "Y")


def test_poisson_counts_round_up():
    assert poisson_counts([1.0, 1.0, 1.0], 0.1) == (10, 10, 10)
    assert poisson_counts([1.4, 1.0, 1.0], 0.1) == (15, 10, 10)
    assert poisson_counts([1.3, 1.0, 1.0], 0.1)[0] == 15            # 13 -> 15
    with pytest.raises(ValueError):
        poisson_counts([1, 1, 1], 0)


def test_division_readout_is_live_and_flags_poisson(ed):
    assert "cell size: 0.2 x 0.2 x 0.2 m" in ed.division_label.text()
    assert "Poisson-friendly" in ed.division_label.text()
    ed.field_widget("cell_count").set_value((21, 10, 10))
    assert "! Poisson" in ed.division_label.text() and "X=21 (use 24)" in ed.division_label.text()
    ed.field_widget("x_max").set_value(8.0)
    assert "0.381" in ed.division_label.text().splitlines()[0]


def test_set_cell_size_and_poisson_button_edit_the_form_only(ed, api):
    assert ed.set_cell_size(0.15) == (27, 15, 15)                 # 26.7 -> 27, 13.3 -> 14 -> 15
    assert ed.field_widget("cell_count").value() == (27, 15, 15)
    assert api.meshes.get("A").cell_count == (20, 10, 10)        # not applied yet
    ed.field_widget("cell_count").set_value((21, 13, 10))
    assert ed.use_poisson_counts() == (24, 15, 10)
    ed.apply()
    assert api.meshes.get("A").cell_count == (24, 15, 10)


def test_units_in_the_readout_and_split_position(api, monkeypatch):
    api.units.set_system("EN")
    e = EntityCollectionEditor(api, "meshes", "Edit Meshes")
    assert " ft" in e.division_label.text()
    new = e.do_split("X", 6.56168)                                  # 2 m typed in feet
    assert new.x_min == pytest.approx(2.0, rel=1e-4)
    e.close()


def test_split_button_flow_selects_and_lists_the_new_mesh(ed, api, monkeypatch):
    monkeypatch.setattr(MeshToolsMixin, "_ask", lambda self, t, f: {"axis": "X", "at": ""})
    new = ed.ask_split()
    assert new is not None and set(ed.names()) == {"A", "A_2"}
    assert api.meshes.get("A").x_max == pytest.approx(2.0)


def test_pending_edits_are_saved_before_a_tool_runs(ed, api):
    ed.field_widget("x_max").set_value(8.0)
    ed.do_refine(2)
    m = api.meshes.get("A")
    assert m.x_max == 8.0 and m.cell_count == (40, 20, 20)


def test_merge_transform_stretch_zone_and_open_boundaries(ed, api):
    ed.do_split("X")
    ed.do_merge(["A", "A_2"])
    assert ed.names() == ["A"] and api.meshes.get("A").cell_count == (20, 10, 10)
    ed.select("A")
    ed.do_transform("move", dx=1.0)
    assert api.meshes.get("A").x_min == pytest.approx(1.0)
    ed.do_transform("mirror", axis="X", at=0.0, copy=True)
    assert len(ed.names()) == 2
    ed.select("A")
    assert len(ed.do_stretching("X", [(2.0, 0.8)])) == 1
    assert "non-uniform spacing on X" in ed.division_label.text()
    assert len(ed.do_open_boundaries()) > 0
    assert ed.do_open_boundaries() == []                            # idempotent


def test_refusals_come_back_as_errors_not_crashes(ed):
    with pytest.raises(ValueError):
        ed.do_split("X", 99.0)
    with pytest.raises(ValueError):
        ed.do_transform("rotate", angle=45)
    assert ed.names() == ["A"]


def test_tools_are_only_on_the_mesh_editor(api):
    s = EntityCollectionEditor(api, "surfaces", "Edit Surfaces")
    assert s.tools_box.isHidden() and s.division_box.isHidden()
    s.close()
