"""Navigation View: the tree of everything that can be shown, with check boxes."""
from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem, QWidget

from pyfds.api.viz import RESULT_KINDS
from pyfds.gui.icons import icon_for_node

TOGGLE_KINDS = set(RESULT_KINDS) | {"geometry", "view"}

_ID = Qt.UserRole


class NavTree(QTreeWidget):
    #: node id, whether the box was ticked
    toggled_node = Signal(str)
    context_requested = Signal(str, object)           # node id, global position

    def __init__(self, viewer, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.viewer = viewer
        self.setHeaderHidden(True)
        self._items: Dict[str, QTreeWidgetItem] = {}
        self._busy = False
        self.itemClicked.connect(self._clicked)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context)

    def rebuild(self) -> None:
        self._busy = True
        expanded = {k for k, it in self._items.items() if it.isExpanded()}
        self.clear()
        self._items.clear()

        def add(node, parent):
            it = QTreeWidgetItem(parent if parent is not None else self.invisibleRootItem(), [node.label])
            it.setData(0, _ID, node.id)
            it.setIcon(0, icon_for_node(node.kind, node.label))
            self._items[node.id] = it
            for c in node.children:
                add(c, it)
            return it

        for top in self.viewer.tree.children:
            add(top, None)
        for k in expanded:
            if k in self._items:
                self._items[k].setExpanded(True)
        if not expanded:
            for top in range(self.topLevelItemCount()):
                self.topLevelItem(top).setExpanded(True)
        self._busy = False
        self.refresh_states()

    def refresh_states(self) -> None:
        """Bold = active leaf; partly bold groups show a ● marker."""
        for nid, it in self._items.items():
            node = self.viewer.tree.find(nid)
            st = self.viewer.node_state(nid) if node is not None else "none"
            f = QFont(it.font(0))
            f.setBold(st != "none")
            it.setFont(0, f)
            mark = {"all": "● ", "some": "◐ ", "none": ""}[st] if node is not None and node.is_leaf and node.kind in TOGGLE_KINDS else ""
            it.setText(0, mark + (node.label if node else it.text(0)))

    def _clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        if self._busy:
            return
        nid = item.data(0, _ID)
        node = self.viewer.tree.find(nid)
        if node is not None and node.is_leaf and node.kind in TOGGLE_KINDS:
            self.toggled_node.emit(nid)

    def _context(self, pos) -> None:
        it = self.itemAt(pos)
        if it is not None:
            self.context_requested.emit(it.data(0, _ID), self.viewport().mapToGlobal(pos))

    def item_for(self, node_id: str) -> Optional[QTreeWidgetItem]:
        return self._items.get(node_id)
