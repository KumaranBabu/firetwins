"""The 2D plan view (plan step F3): a top-down drafting view of the model at one level, with a sketch grid, pan/zoom, the
same drawing tools and snapping as the 3D view, and click-to-select.

``PlanView`` is the drawing surface (``plan_panel.PlanPanel`` adds the level / floor / slab controls above it). What is drawn and
what a click hits come from ``plan_model`` (Qt-free, tested); the tools come from ``viewport_tools`` and are shared with
the 3D view, so a box drawn here is created exactly as one drawn there.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView, QWidget

from pyfds.core.events import EventType
from pyfds.gui.viewport_tools import SELECT, Hit, ToolManager

from .plan_model import PlanShape, extent, grid_lines, grid_spacing, pick_shape, plan_shapes

_REFRESH = (EventType.COMMAND_EXECUTED, EventType.UNDO_PERFORMED, EventType.REDO_PERFORMED, EventType.HISTORY_CLEARED,
            EventType.PROJECT_LOADED, EventType.PROJECT_CREATED, EventType.VIEWPORT_CHANGED)
_CLICK_SLOP = 5
_PICK_PIXELS = 6                       # click tolerance on screen


class PlanView(QGraphicsView):
    entity_picked = Signal(str, object)
    selection_changed = Signal(list)
    cursor_moved = Signal(object)             # (x, y, level) in model metres, or None when the mouse leaves
    status_message = Signal(str)
    context_requested = Signal(object, object)   # (manager_attr, entity) under a right click or None, global position

    def __init__(self, api: Any, tools: Optional[ToolManager] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.tools = tools or ToolManager(api)
        self.level = 0.0
        self.band = 3.0
        self.show_grid = True
        self._shapes: List[PlanShape] = []
        self._selected: Set[int] = set()
        self._preview_items: List[Any] = []
        self._press: Optional[QPointF] = None
        self._pan_from: Optional[QPointF] = None
        self._fitted = False
        self._user_moved = False               # once the user zooms or pans, resizing no longer refits
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)          # hover events (no button down) reach the viewport widget
        self.setFocusPolicy(Qt.StrongFocus)
        self.setBackgroundBrush(QBrush(QColor("#202225")))
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self._subs = [api.subscribe(t, lambda _e: self.refresh()) for t in _REFRESH]
        self.tools.subscribe(self._on_tool_change)
        self.refresh()

    # -- coordinates -----------------------------------------------------------------------------------------
    @property
    def px_per_m(self) -> float:
        return abs(self.transform().m11()) or 1.0

    def to_scene(self, x: float, y: float) -> QPointF:
        return QPointF(x, -y)

    def to_model(self, p: QPointF) -> tuple:
        return (p.x(), -p.y())

    def widget_pos_of(self, x: float, y: float):
        """Pixel position (in the viewport widget) of a model point; used by tests and tooltips."""
        return self.mapFromScene(self.to_scene(x, y))

    # -- content ----------------------------------------------------------------------------------------------
    def set_level(self, level: float, band: Optional[float] = None) -> None:
        self.level = float(level)
        if band is not None:
            self.band = max(0.01, float(band))
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the drawing from the model (the view's zoom and pan stay)."""
        self._shapes = plan_shapes(self.api, self.level, self.band)
        scene = self.scene()
        scene.clear()
        self._preview_items = []
        highlight = QColor(*self.api.viewport.state.highlight_color)
        for z, s in enumerate(self._shapes):
            self._add_shape(scene, s, z, highlight)
        ext = extent(self._shapes)
        if ext is not None:
            pad = max(ext[2] - ext[0], ext[3] - ext[1], 1.0)          # room to pan well past the model
            scene.setSceneRect(QRectF(QPointF(ext[0] - pad, -ext[3] - pad), QPointF(ext[2] + pad, -ext[1] + pad)))
            if not self._fitted:
                self.fit()
        else:
            scene.setSceneRect(QRectF(-10, -10, 20, 20))
        self._draw_preview()
        self.viewport().update()

    def _add_shape(self, scene: QGraphicsScene, s: PlanShape, z: int, highlight: QColor) -> None:
        picked = id(s.entity) in self._selected
        base = QColor(s.color)
        pen = QPen(highlight if picked else base.darker(160), 3 if picked else 1.2)
        pen.setCosmetic(True)
        if s.kind == "device":
            r = 5
            item = scene.addEllipse(-r, -r, 2 * r, 2 * r, pen, QBrush(base))
            item.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            item.setPos(self.to_scene(s.x0, s.y0))
            item.setZValue(z)
            return
        rect = QRectF(self.to_scene(s.x0, s.y1), self.to_scene(s.x1, s.y0))
        if s.kind == "mesh":
            pen = QPen(highlight if picked else base, 3 if picked else 1.5)
            pen.setCosmetic(True)
            item = scene.addRect(rect, pen)
            self._add_mesh_cells(scene, s, base, z)
        elif s.kind == "hole":
            pen.setStyle(Qt.DashLine)
            item = scene.addRect(rect, pen)
        else:
            fill = QColor(base)
            fill.setAlpha(60 if s.below else {"vent": 150, "init": 70}.get(s.kind, 210))
            item = scene.addRect(rect, pen, QBrush(fill))
        item.setZValue(z)

    def _add_mesh_cells(self, scene: QGraphicsScene, s: PlanShape, color: QColor, z: int) -> None:
        nx, ny = s.cells
        if nx < 1 or ny < 1:
            return
        path = QPainterPath()
        sx, sy = max(1, -(-nx // 150)), max(1, -(-ny // 150))        # at most ~150 lines per direction
        for i in range(0, nx + 1, sx):
            x = s.x0 + (s.x1 - s.x0) * i / nx
            path.moveTo(self.to_scene(x, s.y0))
            path.lineTo(self.to_scene(x, s.y1))
        for j in range(0, ny + 1, sy):
            y = s.y0 + (s.y1 - s.y0) * j / ny
            path.moveTo(self.to_scene(s.x0, y))
            path.lineTo(self.to_scene(s.x1, y))
        faint = QColor(color)
        faint.setAlpha(70)
        pen = QPen(faint, 1)
        pen.setCosmetic(True)
        scene.addPath(path, pen).setZValue(z - 0.5)

    # -- camera -----------------------------------------------------------------------------------------------
    def fit(self) -> None:
        ext = extent(self._shapes)
        if ext is None:
            return
        pad = max(ext[2] - ext[0], ext[3] - ext[1], 1.0) * 0.08
        self.fitInView(QRectF(self.to_scene(ext[0] - pad, ext[3] + pad), self.to_scene(ext[2] + pad, ext[1] - pad)),
                       Qt.KeepAspectRatio)
        self._fitted = True
        self._user_moved = False

    def showEvent(self, event) -> None:                                      # noqa: N802 (Qt API)
        super().showEvent(event)
        if not self._user_moved:
            self.fit()                                  # the first fit ran before the widget had a size

    def resizeEvent(self, event) -> None:                                    # noqa: N802 (Qt API)
        super().resizeEvent(event)
        if not self._user_moved:
            self.fit()

    def zoom(self, factor: float) -> None:
        self.scale(factor, factor)
        self._user_moved = True

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:       # noqa: N802 (Qt API)
        super().drawBackground(painter, rect)
        if not self.show_grid:
            return
        base = self.api.viewport.state.snap.grid_size
        step = grid_spacing(base, self.px_per_m)
        minor = QPen(QColor(255, 255, 255, 22), 1)
        minor.setCosmetic(True)
        painter.setPen(minor)
        for x in grid_lines(rect.left(), rect.right(), step):
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        for y in grid_lines(-rect.bottom(), -rect.top(), step):
            painter.drawLine(QPointF(rect.left(), -y), QPointF(rect.right(), -y))
        axis = QPen(QColor(255, 255, 255, 70), 1)
        axis.setCosmetic(True)
        painter.setPen(axis)
        painter.drawLine(QPointF(0, rect.top()), QPointF(0, rect.bottom()))
        painter.drawLine(QPointF(rect.left(), 0), QPointF(rect.right(), 0))

    # -- tool preview -----------------------------------------------------------------------------------------
    def _on_tool_change(self) -> None:
        self._draw_preview()
        for m in self.tools.take_messages() or [self.tools.preview().text]:
            if m:
                self.status_message.emit(m)

    def _draw_preview(self) -> None:
        scene = self.scene()
        for it in self._preview_items:
            scene.removeItem(it)
        self._preview_items = []
        p = self.tools.preview()
        pen = QPen(QColor("#ffd24a"), 2)
        pen.setCosmetic(True)
        fill = QColor("#ffd24a")
        fill.setAlpha(70)
        for b in p.boxes:
            rect = QRectF(self.to_scene(b[0], b[3]), self.to_scene(b[1], b[2]))
            self._preview_items.append(scene.addRect(rect, pen, QBrush(fill)))
        for line in p.polylines:
            if len(line) >= 2:
                path = QPainterPath(self.to_scene(line[0][0], line[0][1]))
                for q in line[1:]:
                    path.lineTo(self.to_scene(q[0], q[1]))
                self._preview_items.append(scene.addPath(path, pen))
        for it in self._preview_items:
            it.setZValue(1000)

    # -- selection --------------------------------------------------------------------------------------------
    def set_selection(self, entities: List[Any]) -> None:
        """Highlight these entities (the project tree's selection)."""
        self._selected = {id(e) for e in entities}
        self.refresh()

    def _hit_at(self, model_xy: tuple) -> Hit:
        tol = _PICK_PIXELS / self.px_per_m
        s = pick_shape(self._shapes, model_xy[0], model_xy[1], tol)
        return Hit((model_xy[0], model_xy[1], self.level), None, (s.attr, s.entity) if s else None)

    def _select(self, hit: Hit, ctrl: bool) -> None:
        if hit.entity is None:
            if not ctrl and self._selected:
                self._selected = set()
                self.selection_changed.emit([])
                self.refresh()
            return
        key = id(hit.entity[1])
        if ctrl:
            self._selected.symmetric_difference_update({key})
        else:
            self._selected = {key}
        chosen = [(s.attr, s.entity) for s in self._shapes if id(s.entity) in self._selected]
        self.entity_picked.emit(*hit.entity)
        self.selection_changed.emit(chosen)
        self.refresh()

    # -- mouse and keys ---------------------------------------------------------------------------------------
    def wheelEvent(self, event) -> None:                                     # noqa: N802 (Qt API)
        self.zoom(1.18 if event.angleDelta().y() > 0 else 1 / 1.18)

    def mousePressEvent(self, event) -> None:                                # noqa: N802 (Qt API)
        self.setFocus()
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_from = event.position()
            self._pan_start = event.position()
            self.viewport().setCursor(Qt.ClosedHandCursor)
        elif event.button() == Qt.LeftButton:
            self._press = event.position()

    def mouseMoveEvent(self, event) -> None:                                 # noqa: N802 (Qt API)
        if self._pan_from is not None:
            self._user_moved = True
            d = event.position() - self._pan_from
            self._pan_from = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        x, y = self.to_model(self.mapToScene(event.position().toPoint()))
        self.cursor_moved.emit((x, y, self.level))
        if self.tools.current.active():
            self.tools.move(Hit((x, y, self.level)))

    def mouseReleaseEvent(self, event) -> None:                              # noqa: N802 (Qt API)
        if event.button() in (Qt.MiddleButton, Qt.RightButton) and self._pan_from is not None:
            self._pan_from = None
            self.viewport().unsetCursor()
            d = event.position() - self._pan_start
            if event.button() == Qt.RightButton and abs(d.x()) + abs(d.y()) <= _CLICK_SLOP:      # a right click, not a pan
                hit = self._hit_at(self.to_model(self.mapToScene(event.position().toPoint())))
                self.context_requested.emit(hit.entity, event.globalPosition().toPoint())
        elif event.button() == Qt.LeftButton and self._press is not None:
            moved = abs(event.position().x() - self._press.x()) + abs(event.position().y() - self._press.y())
            self._press = None
            if moved <= _CLICK_SLOP:
                self.click_at(self.to_model(self.mapToScene(event.position().toPoint())),
                              bool(event.modifiers() & Qt.ControlModifier))

    def mouseDoubleClickEvent(self, event) -> None:                          # noqa: N802 (Qt API)
        if event.button() == Qt.LeftButton and self.tools.current.active():
            self.tools.finish()

    def leaveEvent(self, event) -> None:                                     # noqa: N802 (Qt API)
        self.cursor_moved.emit(None)
        super().leaveEvent(event)

    def click_at(self, model_xy: tuple, ctrl: bool = False) -> Any:
        """A click at a model point: selects with the Select tool, otherwise goes to the active tool."""
        hit = self._hit_at(model_xy)
        if self.tools.current.name == SELECT:
            self._select(hit, ctrl)
            return None
        return self.tools.click(hit)

    def keyPressEvent(self, event) -> None:                                  # noqa: N802 (Qt API)
        key = event.key()
        if key == Qt.Key_Escape:
            self.tools.escape()
        elif key in (Qt.Key_Return, Qt.Key_Enter) and self.tools.current.active():
            self.tools.finish()
        elif key == Qt.Key_Home:
            self.fit()
        elif key in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom(1.18)
        elif key == Qt.Key_Minus:
            self.zoom(1 / 1.18)
        else:
            super().keyPressEvent(event)

    def shutdown(self) -> None:
        for sid in self._subs:
            self.api.unsubscribe(sid)
