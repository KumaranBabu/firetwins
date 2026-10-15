"""HVAC network editor: node and duct graphics items, scene."""
from __future__ import annotations

from typing import TYPE_CHECKING

from typing import Any

from PySide6.QtCore import QLineF, QTimer
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsTextItem,
)


from .hvac_network_editor_common import (
    _AMBIENT_BRUSH,
    _NORMAL_PEN_COLOR,
    _ROOM_BRUSH,
)

if TYPE_CHECKING:
    from .hvac_network_editor import HvacNetworkEditorDialog


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
        self.dialog.api.hvac.move_nodes([(self.node, dx, dy)], label="Move HVAC node")


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
