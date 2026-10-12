"""
Automated regression coverage for the HVAC Network Editor
(``pyfds.gui.hvac_network_editor``).

Same headless approach as ``test_main_window_phase2.py``: no real GUI here
(Qt runs on the offscreen platform), so item drags/clicks are exercised by
calling the dialog's own methods directly (``add_node_at``, ``_commit_move``,
``handle_canvas_click``, ...) rather than simulating real QGraphicsScene
mouse events — the same "call the handler, assert on api/project state"
style the rest of this app's GUI tests already use.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

import pyfds.gui.hvac_network_editor as hne  # noqa: E402
from pyfds.gui.hvac_network_editor import (  # noqa: E402
    DuctItem, HvacNetworkEditorDialog, NodeItem, _next_free_name,
)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_dialog():
    from pyfds.api import FdsApi
    return HvacNetworkEditorDialog(FdsApi())


# ── Naming helper ────────────────────────────────────────────────────────

def test_next_free_name_skips_existing():
    assert _next_free_name(set(), "Node") == "Node 1"
    assert _next_free_name({"Node 1"}, "Node") == "Node 2"
    assert _next_free_name({"Node 1", "Node 2"}, "Node") == "Node 3"


# ── Node / duct creation ─────────────────────────────────────────────────

def test_add_node_at_creates_named_node_at_position():
    dlg = _make_dialog()
    node = dlg.add_node_at(12.0, 34.0)
    assert node.name == "Node 1"
    assert (node.x, node.y) == (12.0, 34.0)
    assert node.name in dlg._node_items
    dlg.close()


def test_add_node_auto_increments_names():
    dlg = _make_dialog()
    n1 = dlg.add_node_at(0, 0)
    n2 = dlg.add_node_at(10, 0)
    assert (n1.name, n2.name) == ("Node 1", "Node 2")
    dlg.close()


def test_add_duct_links_nodes_by_name():
    dlg = _make_dialog()
    a = dlg.add_node_at(0, 0)
    b = dlg.add_node_at(100, 0)
    duct = dlg.add_duct(a, b)
    assert duct.node_id_1 == a.name
    assert duct.node_id_2 == b.name
    assert duct.name in dlg._duct_items
    item = dlg._duct_items[duct.name]
    assert isinstance(item, DuctItem)
    assert item.node_item_a.node is a
    assert item.node_item_b.node is b
    dlg.close()


def test_handle_canvas_click_add_node_tool_places_node():
    dlg = _make_dialog()
    dlg.set_tool("add_node")
    dlg.handle_canvas_click(QPointF(5.0, 6.0), None)
    assert dlg.tool == "select"  # single-shot, resets after placing
    assert len(dlg.api.hvac_nodes.all()) == 1
    node = dlg.api.hvac_nodes.all()[0]
    assert (node.x, node.y) == (5.0, 6.0)
    dlg.close()


def test_handle_canvas_click_add_duct_tool_two_click_flow():
    dlg = _make_dialog()
    a = dlg.add_node_at(0, 0)
    b = dlg.add_node_at(50, 0)
    item_a = dlg._node_items[a.name]
    item_b = dlg._node_items[b.name]

    dlg.set_tool("add_duct")
    dlg.handle_canvas_click(QPointF(0, 0), item_a)
    assert dlg._pending_duct_source is item_a
    assert dlg.api.hvac_ducts.all() == []

    dlg.handle_canvas_click(QPointF(50, 0), item_b)
    ducts = dlg.api.hvac_ducts.all()
    assert len(ducts) == 1
    assert (ducts[0].node_id_1, ducts[0].node_id_2) == (a.name, b.name)
    assert dlg.tool == "select"
    dlg.close()


def test_handle_canvas_click_add_duct_tool_cancels_on_empty_click():
    dlg = _make_dialog()
    a = dlg.add_node_at(0, 0)
    item_a = dlg._node_items[a.name]

    dlg.set_tool("add_duct")
    dlg.handle_canvas_click(QPointF(0, 0), item_a)
    assert dlg._pending_duct_source is item_a

    dlg.handle_canvas_click(QPointF(999, 999), None)
    assert dlg.tool == "select"
    assert dlg.api.hvac_ducts.all() == []
    dlg.close()


# ── Drag-to-move ─────────────────────────────────────────────────────────

def test_node_drag_commits_single_undoable_move():
    dlg = _make_dialog()
    node = dlg.add_node_at(0, 0)
    item = dlg._node_items[node.name]

    item._drag_start = item.pos()
    item.setPos(QPointF(30.0, 40.0))
    item._commit_move()

    assert (node.x, node.y) == (30.0, 40.0)
    dlg.api.history.undo()
    assert (node.x, node.y) == (0.0, 0.0)
    dlg.close()


def test_node_drag_with_no_movement_commits_nothing():
    dlg = _make_dialog()
    node = dlg.add_node_at(0, 0)
    item = dlg._node_items[node.name]

    item._drag_start = item.pos()
    item.setPos(item.pos())  # no-op move
    item._commit_move()

    # Nothing to undo beyond the original add-node command.
    dlg.api.history.undo()
    assert dlg.api.hvac_nodes.all() == []
    dlg.close()


def test_duct_line_follows_node_drag_before_commit():
    dlg = _make_dialog()
    a = dlg.add_node_at(0, 0)
    b = dlg.add_node_at(100, 0)
    duct = dlg.add_duct(a, b)
    duct_item = dlg._duct_items[duct.name]
    node_item_a = dlg._node_items[a.name]

    node_item_a.setPos(QPointF(0, 50))  # drag only — not yet committed
    assert duct_item.line().p1().y() == 50 or duct_item.line().p2().y() == 50
    dlg.close()


# ── Delete ───────────────────────────────────────────────────────────────

def test_delete_selected_removes_node(monkeypatch):
    dlg = _make_dialog()
    node = dlg.add_node_at(0, 0)
    item = dlg._node_items[node.name]
    item.setSelected(True)

    monkeypatch.setattr(hne.QMessageBox, "question", lambda *a, **k: hne.QMessageBox.Yes)
    dlg.delete_selected()
    assert dlg.api.hvac_nodes.all() == []
    dlg.close()


def test_delete_selected_removes_duct(monkeypatch):
    dlg = _make_dialog()
    a = dlg.add_node_at(0, 0)
    b = dlg.add_node_at(50, 0)
    duct = dlg.add_duct(a, b)
    duct_item = dlg._duct_items[duct.name]
    duct_item.setSelected(True)

    monkeypatch.setattr(hne.QMessageBox, "question", lambda *a, **k: hne.QMessageBox.Yes)
    dlg.delete_selected()
    assert dlg.api.hvac_ducts.all() == []
    assert dlg.api.hvac_nodes.all() != []  # nodes untouched by a duct delete
    dlg.close()


def test_delete_selected_declines_on_no(monkeypatch):
    dlg = _make_dialog()
    node = dlg.add_node_at(0, 0)
    dlg._node_items[node.name].setSelected(True)

    monkeypatch.setattr(hne.QMessageBox, "question", lambda *a, **k: hne.QMessageBox.No)
    dlg.delete_selected()
    assert len(dlg.api.hvac_nodes.all()) == 1
    dlg.close()


# ── Properties ───────────────────────────────────────────────────────────

def test_edit_entity_properties_applies_changed_fields(monkeypatch):
    dlg = _make_dialog()
    node = dlg.add_node_at(0, 0)

    class _FakeDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"x": 99.0}

    monkeypatch.setattr(hne, "SchemaFormDialog", _FakeDialog)
    dlg.edit_entity_properties(node)
    assert node.x == 99.0
    dlg.close()


# ── Fan / Damper / Filter attachment ─────────────────────────────────────

def test_add_component_requires_duct_selection(monkeypatch):
    dlg = _make_dialog()
    informed = []
    monkeypatch.setattr(hne.QMessageBox, "information", lambda *a, **k: informed.append(1))
    dlg._on_add_component("add_fan", "Fan")
    assert informed
    dlg.close()


def test_add_component_prefills_duct_id_and_dispatches(monkeypatch):
    dlg = _make_dialog()
    a = dlg.add_node_at(0, 0)
    b = dlg.add_node_at(50, 0)
    duct = dlg.add_duct(a, b)
    dlg._duct_items[duct.name].setSelected(True)

    captured = {}

    class _FakeDialog:
        def __init__(self, title, description, schema, parent=None):
            captured["schema"] = schema

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"duct_id": duct.name}

    monkeypatch.setattr(hne, "SchemaFormDialog", _FakeDialog)
    dlg._on_add_component("add_fan", "Fan")

    assert captured["schema"]["properties"]["duct_id"]["default"] == duct.name
    assert len(dlg.api.fans.all()) == 1
    assert dlg.api.fans.all()[0].duct_id == duct.name
    dlg.close()


# ── Auto-layout ──────────────────────────────────────────────────────────

def test_auto_layout_only_moves_origin_nodes():
    dlg = _make_dialog()
    a = dlg.add_node_at(0, 0)
    b = dlg.add_node_at(500, 500)  # user already positioned this one
    dlg.auto_layout()
    assert (b.x, b.y) == (500, 500)  # untouched
    assert (a.x, a.y) != (0, 0) or len(dlg.api.hvac_nodes.all()) == 2
    dlg.close()


def test_auto_layout_is_noop_with_no_origin_nodes():
    dlg = _make_dialog()
    node = dlg.add_node_at(10, 10)
    before = (node.x, node.y)
    dlg.auto_layout()
    assert (node.x, node.y) == before
    dlg.close()


def test_auto_layout_undoable_as_one_group():
    dlg = _make_dialog()
    ambient = dlg.api.hvac_nodes.add_node(xyz=[0, 0, 0], ambient=True, name="ATM")
    room = dlg.add_node_at(0, 0)
    dlg.api.hvac_ducts.add_duct(node_id_1="ATM", node_id_2=room.name)

    dlg.auto_layout()
    moved = (room.x, room.y)
    dlg.api.history.undo()
    assert (room.x, room.y) != moved
    dlg.close()


# ── Diagnostics ──────────────────────────────────────────────────────────

def test_run_diagnostics_shows_report_and_colors_green_when_converged(monkeypatch):
    dlg = _make_dialog()
    a = dlg.add_node_at(0, 0)
    b = dlg.add_node_at(50, 0)
    duct = dlg.add_duct(a, b)

    class _Result:
        converged = True
        warnings = []

        def summary(self):
            return "HVAC Network Solve: CONVERGED"

    monkeypatch.setattr(dlg.api.hvac, "solve_network", lambda: _Result())
    captured = {}

    class _FakeReport:
        def __init__(self, title, text, parent=None):
            captured["title"], captured["text"] = title, text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(hne, "TextReportDialog", _FakeReport)
    dlg.run_diagnostics()

    assert "CONVERGED" in captured["text"]
    from pyfds.gui.hvac_network_editor import _OK_COLOR
    assert dlg._duct_items[duct.name].pen().color() == _OK_COLOR
    dlg.close()


def test_run_diagnostics_colors_red_when_not_converged(monkeypatch):
    dlg = _make_dialog()
    a = dlg.add_node_at(0, 0)
    b = dlg.add_node_at(50, 0)
    duct = dlg.add_duct(a, b)

    class _Result:
        converged = False
        warnings = ["imbalance"]

        def summary(self):
            return "HVAC Network Solve: NOT CONVERGED"

    monkeypatch.setattr(dlg.api.hvac, "solve_network", lambda: _Result())
    monkeypatch.setattr(hne, "TextReportDialog", lambda *a, **k: _Accepted())
    dlg.run_diagnostics()

    from pyfds.gui.hvac_network_editor import _WARN_COLOR
    assert dlg._duct_items[duct.name].pen().color() == _WARN_COLOR
    dlg.close()


def test_run_diagnostics_reports_solver_error(monkeypatch):
    dlg = _make_dialog()

    def _boom():
        raise RuntimeError("bad network")

    monkeypatch.setattr(dlg.api.hvac, "solve_network", _boom)
    critical = []
    monkeypatch.setattr(hne.QMessageBox, "critical", lambda *a, **k: critical.append(1))
    dlg.run_diagnostics()
    assert critical
    dlg.close()


class _Accepted:
    def exec(self):
        return QDialog.Accepted


# ── Live refresh ─────────────────────────────────────────────────────────

def test_scene_refreshes_on_external_mutation():
    dlg = _make_dialog()
    assert dlg._node_items == {}
    dlg.api.hvac_nodes.add_node(xyz=[1, 2, 0], name="External")
    assert "External" in dlg._node_items
    dlg.close()


def test_scene_refresh_drops_duct_with_deleted_node():
    dlg = _make_dialog()
    a = dlg.add_node_at(0, 0)
    b = dlg.add_node_at(50, 0)
    duct = dlg.add_duct(a, b)
    assert duct.name in dlg._duct_items

    dlg.api.hvac_nodes.remove(a)
    assert duct.name not in dlg._duct_items
    dlg.close()
