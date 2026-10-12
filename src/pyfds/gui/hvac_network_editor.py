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

from PySide6.QtCore import QLineF, QPointF, QTimer
from PySide6.QtGui import QActionGroup, QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog, QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem,
    QGraphicsScene, QGraphicsTextItem, QGraphicsView, QMenu, QMessageBox,
    QToolBar, QVBoxLayout,
)

from pyfds.agent import AgentToolDispatcher
from pyfds.agent.registry import get_tool
from pyfds.automation.commands import GroupCommand, MoveHvacNodeCommand
from pyfds.core.events import EventType
from pyfds.gui.entity_dialogs import SchemaFormDialog
from pyfds.gui.property_schema import apply_edits, build_edit_schema
from pyfds.gui.report_dialog import TextReportDialog

# Same set ProjectExplorer subscribes to (main_window.py) — duplicated
# locally rather than imported, matching viewport_3d.py's own local copy,
# to avoid a gui-module-to-gui-module circular import.
_REFRESH_EVENTS = (
    EventType.COMMAND_EXECUTED,
    EventType.UNDO_PERFORMED,
    EventType.REDO_PERFORMED,
    EventType.HISTORY_CLEARED,
    EventType.PROJECT_LOADED,
    EventType.PROJECT_CREATED,
)

_LAYER_SPACING = 160.0
_ROW_SPACING = 80.0

_AMBIENT_BRUSH = QBrush(QColor("#70ad47"))
_ROOM_BRUSH = QBrush(QColor("#5b9bd5"))
_NORMAL_PEN_COLOR = QColor("#333333")
_OK_COLOR = QColor("#2e7d32")
_WARN_COLOR = QColor("#c62828")


def _next_free_name(existing: set, prefix: str) -> str:
    n = 1
    while f"{prefix} {n}" in existing:
        n += 1
    return f"{prefix} {n}"


class NodeItem(QGraphicsEllipseItem):
    """One HVAC node — draggable; commits to the model (undoably) only on
    mouse release, not per-frame, so a full scene refresh mid-drag never
    fights the drag itself."""

    RADIUS = 14

    def __init__(self, node: Any, dialog: "HvacNetworkEditorDialog") -> None:
        super().__init__(-self.RADIUS, -self.RADIUS, 2 * self.RADIUS, 2 * self.RADIUS)
        self.node = node
        self.dialog = dialog
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setBrush(_AMBIENT_BRUSH if node.ambient else _ROOM_BRUSH)
        self.setPen(QPen(_NORMAL_PEN_COLOR, 1.5))
        self.setZValue(1)
        label = QGraphicsTextItem(node.name, self)
        label.setPos(-self.RADIUS, self.RADIUS + 2)
        self._drag_start = self.pos()

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.dialog.update_ducts_for_node(self.node.name)
        return result

    def mousePressEvent(self, event) -> None:
        self._drag_start = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        # Deferred: committing fires COMMAND_EXECUTED -> refresh() rebuilds
        # the whole scene (same rebuild-from-scratch pattern as
        # ProjectExplorer), which would delete this very item out from
        # under its own still-executing mouseReleaseEvent call stack.
        QTimer.singleShot(0, self._commit_move)

    def mouseDoubleClickEvent(self, event) -> None:
        super().mouseDoubleClickEvent(event)
        self.dialog.edit_entity_properties(self.node)

    def contextMenuEvent(self, event) -> None:
        self.dialog.show_node_context_menu(self, event.screenPos())

    def _commit_move(self) -> None:
        dx = self.pos().x() - self._drag_start.x()
        dy = self.pos().y() - self._drag_start.y()
        if dx == 0 and dy == 0:
            return
        self.dialog.api.history.execute(MoveHvacNodeCommand(self.node, dx, dy))


class DuctItem(QGraphicsLineItem):
    """One HVAC duct, drawn between its two nodes' live scene positions —
    updated on every node move (see ``NodeItem.itemChange``), even before
    that move is committed to the model."""

    def __init__(
        self, duct: Any, node_item_a: NodeItem, node_item_b: NodeItem,
        dialog: "HvacNetworkEditorDialog",
        fan: Any = None, damper: Any = None, hvac_filter: Any = None,
    ) -> None:
        super().__init__()
        self.duct = duct
        self.node_item_a = node_item_a
        self.node_item_b = node_item_b
        self.dialog = dialog
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setPen(QPen(QColor("#888888"), 2))
        self.setZValue(0)

        bits = [duct.name]
        if fan is not None:
            bits.append("[Fan]")
        if damper is not None:
            bits.append("[Damper]")
        if hvac_filter is not None:
            bits.append("[Filter]")
        self._label = QGraphicsTextItem(" ".join(bits), self)
        self.update_line()

    def update_line(self) -> None:
        a = self.node_item_a.scenePos()
        b = self.node_item_b.scenePos()
        self.setLine(QLineF(a, b))
        self._label.setPos((a + b) / 2)

    def mouseDoubleClickEvent(self, event) -> None:
        super().mouseDoubleClickEvent(event)
        self.dialog.edit_entity_properties(self.duct)

    def contextMenuEvent(self, event) -> None:
        self.dialog.show_duct_context_menu(self, event.screenPos())


class _NetworkScene(QGraphicsScene):
    """Only intercepts clicks while a placement tool (Add Node / Add Duct)
    is active; ordinary selection/drag is left to Qt's default scene
    handling in "select" mode."""

    def __init__(self, dialog: "HvacNetworkEditorDialog") -> None:
        super().__init__(dialog)
        self.dialog = dialog

    def mousePressEvent(self, event) -> None:
        if self.dialog.tool == "select":
            super().mousePressEvent(event)
            return
        item = self.itemAt(event.scenePos(), self.dialog.view.transform())
        self.dialog.handle_canvas_click(event.scenePos(), item)


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
        commands = []
        for n in movable:
            d = depth.get(n.name, 0)
            row = layer_counts.get(d, 0)
            layer_counts[d] = row + 1
            dx = d * _LAYER_SPACING - n.x
            dy = row * _ROW_SPACING - n.y
            if dx or dy:
                commands.append(MoveHvacNodeCommand(n, dx, dy))
        if commands:
            self.api.history.execute(GroupCommand(commands, label="Auto-Layout HVAC Network"))

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
