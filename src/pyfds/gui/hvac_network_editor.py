"""
HVAC Network Editor.

A 2D schematic diagram for the project's HVAC duct network — nodes and
ducts placed as an abstract graph, independent of the building's real 3D
geometry (the same approach PyroSim's HVAC editor takes; unlike a 3D
viewport, ducts/nodes are never occluded or too small to click).

``HvacNode.x``/``.y`` double as the schematic canvas coordinates — no new
layout-only fields — so a diagram layout persists for free through the
existing project save/load path. ``z`` is left untouched.

Entity creation/removal/property-editing all go through the same
``FdsApi``/``CommandPipeline`` path every other GUI surface in this app
uses (undo/redo, AI-agent visibility, and the Project Explorer tree all
stay in sync automatically) — this module adds no new backend logic beyond
``MoveHvacNodeCommand`` (automation/commands.py), which is the 2D-canvas
counterpart of the existing ``MoveObstCommand``.
"""
from __future__ import annotations

import copy
from collections import deque
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QPointF
from PySide6.QtGui import QActionGroup, QPainter
from PySide6.QtWidgets import QDialog, QGraphicsItem, QGraphicsView, QMenu, QMessageBox, QToolBar, QVBoxLayout

from pyfds.agent import AgentToolDispatcher
from pyfds.agent.registry import get_tool
from pyfds.gui.entity_dialogs import SchemaFormDialog
from pyfds.gui.property_schema import apply_edits, build_edit_schema
from pyfds.gui.report_dialog import TextReportDialog

from .hvac_network_editor_items import (  # noqa: F401  (re-exported)
    DuctItem,
    NodeItem,
    _NetworkScene,
)
from .hvac_network_editor_common import (  # noqa: F401  (re-exported)
    _AMBIENT_BRUSH,
    _LAYER_SPACING,
    _NORMAL_PEN_COLOR,
    _OK_COLOR,
    _REFRESH_EVENTS,
    _ROOM_BRUSH,
    _ROW_SPACING,
    _WARN_COLOR,
    _next_free_name,
)



class HvacNetworkEditorDialog(QDialog):
    """Modeless — stays open (hidden, not destroyed, on close) while the
    user keeps working elsewhere, reopened via MainWindow's singleton
    ``self._hvac_editor``."""

    def __init__(self, api: Any, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("HVAC Network Editor")
        self.resize(900, 600)
        self.setModal(False)

        self.api = api
        self.dispatcher = AgentToolDispatcher(api)
        self.tool = "select"
        self._pending_duct_source: Optional[NodeItem] = None
        self._node_items: Dict[str, NodeItem] = {}
        self._duct_items: Dict[str, DuctItem] = {}

        self.scene = _NetworkScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.Antialiasing)

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_toolbar())
        layout.addWidget(self.view)

        self._sub_ids = [api.subscribe(t, self._on_event) for t in _REFRESH_EVENTS]

        self.refresh()
        if all(n.x == 0.0 and n.y == 0.0 for n in api.hvac_nodes.all()):
            self.auto_layout()

    # ── Toolbar ──────────────────────────────────────────────────────────

    def _build_toolbar(self) -> QToolBar:
        bar = QToolBar(self)
        tool_group = QActionGroup(self)
        tool_group.setExclusive(True)

        select_action = bar.addAction("Select")
        select_action.setCheckable(True)
        select_action.setChecked(True)
        select_action.triggered.connect(lambda: self.set_tool("select"))
        tool_group.addAction(select_action)

        add_node_action = bar.addAction("Add Node")
        add_node_action.setCheckable(True)
        add_node_action.triggered.connect(lambda: self.set_tool("add_node"))
        tool_group.addAction(add_node_action)

        add_duct_action = bar.addAction("Add Duct")
        add_duct_action.setCheckable(True)
        add_duct_action.triggered.connect(lambda: self.set_tool("add_duct"))
        tool_group.addAction(add_duct_action)

        bar.addSeparator()
        bar.addAction("Add Fan on Selected Duct...", lambda: self._on_add_component("add_fan", "Fan"))
        bar.addAction("Add Damper on Selected Duct...", lambda: self._on_add_component("add_damper", "Damper"))
        bar.addAction("Add Filter on Selected Duct...", lambda: self._on_add_component("add_hvac_filter", "Filter"))
        bar.addSeparator()
        bar.addAction("Delete Selected", self.delete_selected)
        bar.addSeparator()
        bar.addAction("Auto-Layout", self.auto_layout)
        bar.addAction("Run Diagnostics", self.run_diagnostics)
        return bar

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self._pending_duct_source = None

    # ── Scene rebuild / live sync ───────────────────────────────────────

    def _on_event(self, event) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.scene.clear()
        self._node_items = {}
        self._duct_items = {}

        for node in self.api.hvac_nodes.all():
            item = NodeItem(node, self)
            item.setPos(node.x, node.y)
            self.scene.addItem(item)
            self._node_items[node.name] = item

        fans = {f.duct_id: f for f in self.api.fans.all()}
        dampers = {d.duct_id: d for d in self.api.dampers.all()}
        filters = {f.duct_id: f for f in self.api.hvac_filters.all()}

        for duct in self.api.hvac_ducts.all():
            node_a = self._node_items.get(duct.node_id_1)
            node_b = self._node_items.get(duct.node_id_2)
            if node_a is None or node_b is None:
                continue  # dangling reference to a since-deleted node
            item = DuctItem(
                duct, node_a, node_b, self,
                fan=fans.get(duct.name), damper=dampers.get(duct.name),
                hvac_filter=filters.get(duct.name),
            )
            self.scene.addItem(item)
            self._duct_items[duct.name] = item

    def update_ducts_for_node(self, node_name: str) -> None:
        for duct_item in self._duct_items.values():
            if node_name in (duct_item.duct.node_id_1, duct_item.duct.node_id_2):
                duct_item.update_line()

    # ── Placement tools ──────────────────────────────────────────────────

    def handle_canvas_click(self, pos: QPointF, item: Optional[QGraphicsItem]) -> None:
        if self.tool == "add_node":
            self.add_node_at(pos.x(), pos.y())
            self.set_tool("select")
        elif self.tool == "add_duct":
            node_item = item if isinstance(item, NodeItem) else None
            if node_item is None:
                self.set_tool("select")
                return
            if self._pending_duct_source is None:
                self._pending_duct_source = node_item
                return
            if node_item is not self._pending_duct_source:
                self.add_duct(self._pending_duct_source.node, node_item.node)
            self.set_tool("select")

    def add_node_at(self, x: float, y: float) -> Any:
        existing = {n.name for n in self.api.hvac_nodes.all()}
        name = _next_free_name(existing, "Node")
        return self.api.hvac_nodes.add_node(xyz=[x, y, 0.0], name=name)

    def add_duct(self, node_a: Any, node_b: Any) -> Any:
        existing = {d.name for d in self.api.hvac_ducts.all()}
        name = _next_free_name(existing, "Duct")
        return self.api.hvac_ducts.add_duct(node_id_1=node_a.name, node_id_2=node_b.name, name=name)

    # ── Fan / Damper / Filter ────────────────────────────────────────────

    def selected_duct(self) -> Optional[Any]:
        for item in self.scene.selectedItems():
            if isinstance(item, DuctItem):
                return item.duct
        return None

    def _on_add_component(self, tool_name: str, label: str) -> None:
        duct = self.selected_duct()
        if duct is None:
            QMessageBox.information(self, "No duct selected", f"Select a duct first to add a {label}.")
            return
        tool = get_tool(tool_name)
        schema = copy.deepcopy(tool.input_schema)
        if "duct_id" in schema.get("properties", {}):
            schema["properties"]["duct_id"]["default"] = duct.name
        dialog = SchemaFormDialog(tool.name, tool.description, schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.dispatcher.call(tool.name, dialog.values())
        except Exception as exc:
            QMessageBox.critical(self, f"Could not add {label}", str(exc))

    # ── Properties / delete ──────────────────────────────────────────────

    def edit_entity_properties(self, entity: Any) -> None:
        schema = build_edit_schema(entity)
        dialog = SchemaFormDialog(f"Edit {entity.name}", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            apply_edits(self.api, entity, dialog.values())
        except Exception as exc:
            QMessageBox.critical(self, "Could not update properties", str(exc))

    def _delete_entity(self, manager: Any, entity: Any) -> None:
        name = getattr(entity, "name", repr(entity))
        if QMessageBox.question(self, "Delete", f"Remove {name!r}?") != QMessageBox.Yes:
            return
        try:
            manager.remove(entity)
        except Exception as exc:
            QMessageBox.critical(self, "Could not remove entity", str(exc))

    def delete_selected(self) -> None:
        for item in list(self.scene.selectedItems()):
            if isinstance(item, NodeItem):
                self._delete_entity(self.api.hvac_nodes, item.node)
            elif isinstance(item, DuctItem):
                self._delete_entity(self.api.hvac_ducts, item.duct)

    def show_node_context_menu(self, node_item: NodeItem, screen_pos) -> None:
        menu = QMenu(self)
        menu.addAction("&Properties...", lambda: self.edit_entity_properties(node_item.node))
        menu.addAction("&Delete", lambda: self._delete_entity(self.api.hvac_nodes, node_item.node))
        menu.exec(screen_pos)

    def show_duct_context_menu(self, duct_item: DuctItem, screen_pos) -> None:
        menu = QMenu(self)
        menu.addAction("&Properties...", lambda: self.edit_entity_properties(duct_item.duct))
        menu.addAction("&Delete", lambda: self._delete_entity(self.api.hvac_ducts, duct_item.duct))
        menu.exec(screen_pos)

    # ── Auto-layout ──────────────────────────────────────────────────────

    def auto_layout(self) -> None:
        nodes = self.api.hvac_nodes.all()
        ducts = self.api.hvac_ducts.all()
        movable = [n for n in nodes if n.x == 0.0 and n.y == 0.0]
        if not movable:
            return

        adjacency: Dict[str, List[str]] = {n.name: [] for n in nodes}
        for duct in ducts:
            adjacency.setdefault(duct.node_id_1, []).append(duct.node_id_2)
            adjacency.setdefault(duct.node_id_2, []).append(duct.node_id_1)

        depth: Dict[str, int] = {}
        queue: deque = deque()
        for n in nodes:
            if n.ambient:
                depth[n.name] = 0
                queue.append(n.name)
        if not queue and nodes:
            depth[nodes[0].name] = 0
            queue.append(nodes[0].name)
        while queue:
            cur = queue.popleft()
            for nxt in adjacency.get(cur, []):
                if nxt not in depth:
                    depth[nxt] = depth[cur] + 1
                    queue.append(nxt)

        layer_counts: Dict[int, int] = {}
        moves = []
        for n in movable:
            d = depth.get(n.name, 0)
            row = layer_counts.get(d, 0)
            layer_counts[d] = row + 1
            dx = d * _LAYER_SPACING - n.x
            dy = row * _ROW_SPACING - n.y
            moves.append((n, dx, dy))
        self.api.hvac.move_nodes(moves, label="Auto-Layout HVAC Network")

    # ── Diagnostics ──────────────────────────────────────────────────────

    def run_diagnostics(self) -> None:
        try:
            result = self.api.hvac.solve_network()
        except Exception as exc:
            QMessageBox.critical(self, "Could not run diagnostics", str(exc))
            return
        self._apply_diagnostics_coloring(result)
        TextReportDialog("HVAC Network Diagnostics", result.summary(), self).exec()

    def _apply_diagnostics_coloring(self, result: Any) -> None:
        ok = bool(result.converged) and not result.warnings
        color = _OK_COLOR if ok else _WARN_COLOR
        for item in self._duct_items.values():
            pen = item.pen()
            pen.setColor(color)
            item.setPen(pen)
        for item in self._node_items.values():
            pen = item.pen()
            pen.setColor(color)
            item.setPen(pen)
