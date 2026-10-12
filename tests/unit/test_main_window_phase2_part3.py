"""Automated regression coverage for the Phase 2 menu handlers (both wiring (part 3 of 4)."""


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

def _build_simple_hvac_network(window):
    window.api.hvac_nodes.add_node(xyz=[0, 0, 0], ambient=True, name="ATM")
    window.api.hvac_nodes.add_node(xyz=[5, 0, 0], name="ROOM")
    window.api.hvac_ducts.add_duct(node_id_1="ATM", node_id_2="ROOM", diameter=0.3, length=5.0)


def test_fds_preview_shows_generated_fds_text(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(
        "pyfds.io.fds_writer.FdsWriter.to_string",
        lambda self, project: "&HEAD CHID='test' /",
    )
    captured = {}

    class _FakeDialog5:
        def __init__(self, title, text, parent=None):
            captured["title"], captured["text"] = title, text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeDialog5)
    window._on_fds_preview()
    assert "FDS Preview" in captured["title"]
    assert "&HEAD" in captured["text"]
    window.close()

def test_hvac_solver_setup_runs_solver_with_chosen_params(monkeypatch):
    window = _make_window()
    _build_simple_hvac_network(window)

    monkeypatch.setattr(
        mw, "SchemaFormDialog",
        _fake_dialog_returning({"rho": 1.0, "max_iter": 50, "tol": 1e-4}),
    )
    called = {}
    real_solve = window.api.hvac.solve_network

    def _spy_solve(rho=1.2, max_iter=200, tol=1e-5):
        called.update(rho=rho, max_iter=max_iter, tol=tol)
        return real_solve(rho=rho, max_iter=max_iter, tol=tol)

    monkeypatch.setattr(window.api.hvac, "solve_network", _spy_solve)

    captured = {}

    class _FakeReport:
        def __init__(self, title, text, parent=None):
            captured["title"], captured["text"] = title, text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeReport)
    window._on_hvac_solver_setup()
    assert called == {"rho": 1.0, "max_iter": 50, "tol": 1e-4}
    assert "HVAC" in captured["title"]
    assert "HVAC Network Solve" in captured["text"]
    window.close()

def test_hvac_diagnostics_runs_solver_with_defaults(monkeypatch):
    window = _make_window()
    _build_simple_hvac_network(window)

    captured = {}

    class _FakeReport:
        def __init__(self, title, text, parent=None):
            captured["title"], captured["text"] = title, text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeReport)
    window._on_hvac_diagnostics()
    assert captured["title"] == "HVAC Diagnostics"
    assert "HVAC Network Solve" in captured["text"]
    window.close()

def test_hvac_diagnostics_reports_solver_failure(monkeypatch):
    window = _make_window()

    def _boom():
        raise RuntimeError("bad network")

    monkeypatch.setattr(window.api.hvac, "solve_network", _boom)
    critical = []
    monkeypatch.setattr(mw.QMessageBox, "critical", lambda *a, **k: critical.append(1))
    window._on_hvac_diagnostics()
    assert critical
    window.close()

def test_show_panels_submenu_toggles_dock_visibility():
    window = _make_window()
    window.show()
    assert window.explorer_dock.isVisible()
    window.explorer_dock.toggleViewAction().trigger()
    assert not window.explorer_dock.isVisible()
    window.close()

def test_workspace_then_layouts_round_trips_saved_state(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(window, "saveState", lambda: b"fake-state-bytes")
    monkeypatch.setattr(mw.QInputDialog, "getText", lambda *a, **k: ("my-layout", True))
    window._on_workspace()
    assert "my-layout" in window._window_layout_names()

    monkeypatch.setattr(mw.QInputDialog, "getItem", lambda *a, **k: ("my-layout", True))
    restored = []
    monkeypatch.setattr(window, "restoreState", lambda state: restored.append(state))
    window._on_layouts()
    assert restored == [b"fake-state-bytes"]
    window.close()

def test_layouts_with_none_saved_shows_info_not_picker(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(
        mw.QInputDialog, "getItem",
        lambda *a, **k: pytest.fail("must not prompt with no saved layouts"),
    )
    informed = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_layouts()
    assert informed
    window.close()

def test_reset_window_layout_restores_startup_state(monkeypatch):
    window = _make_window()
    restored = []
    monkeypatch.setattr(window, "restoreState", lambda state: restored.append(state))
    window._on_reset_window_layout()
    assert restored == [window._default_window_state]
    window.close()

def test_hvac_network_editor_opens_singleton_instance():
    window = _make_window()
    assert window._hvac_editor is None
    window._on_hvac_network_editor()
    first = window._hvac_editor
    assert first is not None
    window._on_hvac_network_editor()
    assert window._hvac_editor is first
    window.close()

def test_group_selected_creates_group_and_assigns(monkeypatch):
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    b = window.api.obstructions.add_obstruction(xb=[2, 3, 0, 1, 0, 1], name="b")
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", a), ("obstructions", b)])

    monkeypatch.setattr(mw.QInputDialog, "getText", lambda *a, **k: ("MyGroup", True))
    window._on_group_selected()

    assert window.api.groups.group_of(a) == "MyGroup"
    assert window.api.groups.group_of(b) == "MyGroup"
    window.close()

def test_group_selected_declines_without_name(monkeypatch):
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", a)])

    monkeypatch.setattr(mw.QInputDialog, "getText", lambda *a, **k: ("", False))
    window._on_group_selected()

    assert window.api.groups.group_of(a) is None
    window.close()

def test_group_selected_with_nothing_selected_shows_info(monkeypatch):
    window = _make_window()
    informed = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_group_selected()
    assert informed
    window.close()

def test_ungroup_selected_clears_membership(monkeypatch):
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    window.api.groups.create("G1")
    window.api.groups.assign(a, "G1")
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", a)])

    window._on_ungroup_selected()

    assert window.api.groups.group_of(a) is None
    window.close()

def test_ungroup_selecting_group_row_ungroups_all_members(monkeypatch):
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    b = window.api.obstructions.add_obstruction(xb=[2, 3, 0, 1, 0, 1], name="b")
    g = window.api.groups.create("G1")
    window.api.groups.assign(a, "G1")
    window.api.groups.assign(b, "G1")
    window.explorer.refresh()
    window.explorer.select_entities([("groups", g)])

    window._on_ungroup_selected()

    assert window.api.groups.group_of(a) is None
    assert window.api.groups.group_of(b) is None
    assert window.api.groups.get("G1") is None
    window.close()

def test_select_group_members_selects_all_in_tree(monkeypatch):
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    b = window.api.obstructions.add_obstruction(xb=[2, 3, 0, 1, 0, 1], name="b")
    window.api.groups.create("G1")
    window.api.groups.assign(a, "G1")
    window.api.groups.assign(b, "G1")
    window.explorer.refresh()

    window._on_select_group_members("G1")

    pairs = window.explorer.selected_entities()
    assert {e.name for _, e in pairs} == {"a", "b"}
    window.close()

def test_select_group_members_empty_group_shows_info(monkeypatch):
    window = _make_window()
    window.api.groups.create("Empty")
    informed = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_select_group_members("Empty")
    assert informed
    window.close()

def test_move_selected_translates_all_entity_kinds(monkeypatch):
    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 2, 0, 2, 0, 2], name="obst")
    from pyfds.domain.geometry_tools import GeometryTools
    geom = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="geom")
    window.api.project.add_entity(geom)
    device = window.api.devices.add_device(xyz=[5, 5, 5], quantity="TEMPERATURE", name="dev")
    window.explorer.refresh()
    window.explorer.select_entities([
        ("obstructions", obst), ("geom", geom), ("devices", device),
    ])

    monkeypatch.setattr(
        mw, "SchemaFormDialog", _fake_dialog_returning({"dx": 1.0, "dy": 2.0, "dz": 0.0})
    )
    window._on_move_selected()

    assert (obst.x_min, obst.y_min) == (1.0, 2.0)
    assert geom.verts[0] == (1.0, 2.0, 0.0)
    assert device.xyz == (6.0, 7.0, 5.0)

    window.api.history.undo()
    assert (obst.x_min, obst.y_min) == (0.0, 0.0)
    assert geom.verts[0] == (0.0, 0.0, 0.0)
    assert device.xyz == (5.0, 5.0, 5.0)
    window.close()

def test_move_selected_with_nothing_selected_shows_info(monkeypatch):
    window = _make_window()
    informed = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_move_selected()
    assert informed
    window.close()

def test_rotate_selected_uses_shared_pivot_not_per_entity_centroid(monkeypatch):
    # Two identical-size boxes side by side; rotating 180° about their
    # COMBINED centroid should swap their positions, not spin each one in
    # place about its own centroid (which would leave both unchanged).
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 2, 0, 2, 0, 1], name="a")
    b = window.api.obstructions.add_obstruction(xb=[4, 6, 0, 2, 0, 1], name="b")
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", a), ("obstructions", b)])

    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning({"degrees": 180.0}))
    window._on_rotate_selected()

    assert (a.x_min, a.x_max) == pytest.approx((4.0, 6.0))
    assert (b.x_min, b.x_max) == pytest.approx((0.0, 2.0))
    window.close()

def test_rotate_selected_skips_xb_entity_on_non_90_multiple(monkeypatch):
    # XB entities (RotateCommand) only accept multiples of 90; a Geom in
    # the same batch has no such restriction — the XB entity is skipped,
    # not a hard failure for the whole selection.
    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 2, 0, 2, 0, 1], name="obst")
    from pyfds.domain.geometry_tools import GeometryTools
    geom = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="geom")
    window.api.project.add_entity(geom)
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", obst), ("geom", geom)])

    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning({"degrees": 17.5}))
    window._on_rotate_selected()

    assert (obst.x_min, obst.x_max) == (0.0, 2.0)  # untouched — skipped
    assert geom.verts[0] != (0.0, 0.0, 0.0)  # Geom did rotate
    window.close()

def test_scale_selected_scales_about_shared_centroid(monkeypatch):
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 2, 0, 2, 0, 1], name="a")
    b = window.api.obstructions.add_obstruction(xb=[4, 6, 0, 2, 0, 1], name="b")
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", a), ("obstructions", b)])

    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning({"factor": 2.0}))
    window._on_scale_selected()

    # Combined centroid is x=3.0 — doubling extents about that shared
    # point spreads the two boxes apart, not just each growing in place.
    assert a.x_min == pytest.approx(-3.0)
    assert b.x_max == pytest.approx(9.0)
    window.close()

def test_mirror_selected_reflects_across_shared_plane(monkeypatch):
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 2, 0, 2, 0, 1], name="a")
    b = window.api.obstructions.add_obstruction(xb=[4, 6, 0, 2, 0, 1], name="b")
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", a), ("obstructions", b)])

    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning({"axis": "X"}))
    window._on_mirror_selected()

    assert (a.x_min, a.x_max) == pytest.approx((4.0, 6.0))
    assert (b.x_min, b.x_max) == pytest.approx((0.0, 2.0))
    window.close()
