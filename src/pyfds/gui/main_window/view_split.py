"""Split views (View > Split): the Model tab shows the 3D view alone, beside a 2D plan, above one, or in four panes.

The 3D widget is created once inside ``model_top`` (a splitter inside ``model_split``) and never re-parented -- moving a GL
widget between parents can lose its context. Splitting only adds and removes the *other* panes around it:

    single:      [ 3D ]
    horizontal:  [ 3D | plan ]
    vertical:    [ 3D ]
                 [plan]
    four:        [ 3D | plan A ]
                 [Record | plan B]

Each extra plan has its own floor and level, so two storeys can be shown at once.
"""
from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QSplitter

SPLIT_MODES = ("single", "horizontal", "vertical", "four")


class _FirstLayout(QObject):
    """Calls *apply* on a splitter's resize / layout events until it reports success (real sizes exist)."""

    def __init__(self, apply, parent=None) -> None:
        super().__init__(parent)
        self._apply = apply

    def eventFilter(self, _obj, event):                                   # noqa: N802 (Qt API)
        if event.type() in (QEvent.Resize, QEvent.LayoutRequest, QEvent.Show):
            self._apply()
        return False


class ViewSplitMixin:
    def _build_model_split(self) -> QSplitter:
        """The container the Model tab holds; the 3D widget sits in it from the start."""
        self.model_top = QSplitter(Qt.Horizontal, self)
        self.model_top.addWidget(self.viewport_widget)
        self.model_top.setChildrenCollapsible(False)
        self.model_split = QSplitter(Qt.Vertical, self)
        self.model_split.addWidget(self.model_top)
        self.model_split.setChildrenCollapsible(False)
        self._split_mode = "single"
        self._split_panes: List[Any] = []                 # the extra widgets currently shown (plans, record view)
        self._split_bottom: Optional[QSplitter] = None
        self._split_pending = False                       # proportions still to be applied once the layout has sizes
        self._split_filter = _FirstLayout(self._apportion_split, self)
        for splitter in (self.model_top, self.model_split):
            splitter.installEventFilter(self._split_filter)
        return self.model_split

    @property
    def split_mode(self) -> str:
        return self._split_mode

    # -- the extra panes -----------------------------------------------------------------------------------------
    def _make_plan_panel(self) -> Any:
        """A plan view wired to the window like the 2D tab's (selection, status bar, cursor readout)."""
        from pyfds.gui.plan import PlanPanel
        plan = PlanPanel(self.api, self.tool_manager, self)
        plan.entity_picked.connect(self.explorer.select_entity)
        plan.selection_changed.connect(self.explorer.select_entities)
        plan.status_message.connect(lambda m: self.statusBar().showMessage(m, 8000))
        plan.cursor_moved.connect(self._update_cursor_label)
        self.connect_context_menu(plan)
        return plan

    def _make_record_pane(self) -> Any:
        from pyfds.gui.record_view import RecordView
        view = RecordView(self.api, on_select=self.explorer.select_entity, parent=self)
        view.refresh()
        return view

    def _clear_split_panes(self) -> None:
        for pane in self._split_panes:
            if hasattr(pane, "shutdown"):
                pane.shutdown()
            pane.setParent(None)
            pane.deleteLater()
        self._split_panes = []
        if self._split_bottom is not None:
            self._split_bottom.setParent(None)
            self._split_bottom.deleteLater()
            self._split_bottom = None

    def split_panes(self) -> List[Any]:
        return list(self._split_panes)

    # -- changing the layout -----------------------------------------------------------------------------------------
    def set_split_mode(self, mode: str) -> str:
        """Show the Model tab as one of ``single`` / ``horizontal`` / ``vertical`` / ``four`` (the 3D view stays put)."""
        if mode not in SPLIT_MODES:
            raise ValueError(f"split mode must be one of {', '.join(SPLIT_MODES)}")
        if mode == self._split_mode:
            return mode
        self._clear_split_panes()
        self.model_top.setOrientation(Qt.Vertical if mode == "vertical" else Qt.Horizontal)
        if mode != "single":
            plan = self._make_plan_panel()
            self.model_top.addWidget(plan)
            self._split_panes.append(plan)
        if mode == "four":
            self._split_bottom = QSplitter(Qt.Horizontal, self)
            self._split_bottom.setChildrenCollapsible(False)
            self._split_bottom.installEventFilter(self._split_filter)
            record, plan_b = self._make_record_pane(), self._make_plan_panel()
            self._split_bottom.addWidget(record)
            self._split_bottom.addWidget(plan_b)
            self._split_panes += [record, plan_b]
            self.model_split.addWidget(self._split_bottom)
        self._split_mode = mode
        self._split_pending = True
        self._apportion_split()
        QTimer.singleShot(0, self._apportion_split)       # and again from the layout events below
        self._sync_plan_selection()
        self._sync_split_actions()
        return mode

    #: share of the room the 3D view / the first row get (the rest goes to the plans / the second row)
    _MAIN_SHARE = 0.6

    def _apportion_split(self) -> None:
        """Give the 3D view the larger share and keep that proportion when the window is resized. Runs until every
        splitter involved has a real size (the first layout pass after a change re-equalises them)."""
        if not self._split_pending:
            return
        done = True
        for splitter, share in ((self.model_top, self._MAIN_SHARE), (self._split_bottom, self._MAIN_SHARE),
                                (self.model_split, 0.62)):
            if splitter is None or splitter.count() < 2:
                continue
            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 2)
            total = splitter.height() if splitter.orientation() == Qt.Vertical else splitter.width()
            if total > 50:
                first = int(total * share)
                splitter.setSizes([first, total - first])
            else:
                done = False
        if done:
            self._split_pending = False

    def _sync_split_actions(self) -> None:
        for mode, action in getattr(self, "_split_actions", {}).items():
            action.blockSignals(True)
            action.setChecked(mode == self._split_mode)
            action.blockSignals(False)

    def _build_split_menu_actions(self, submenu: Any) -> None:
        """Fill View > Split with Single / Horizontal / Vertical / Four-Way (one is always checked)."""
        group = QActionGroup(self)
        group.setExclusive(True)
        self._split_actions = {}
        for mode, label in (("single", "Single View"), ("horizontal", "Horizontal (3D | 2D)"),
                            ("vertical", "Vertical (3D over 2D)"), ("four", "Four-Way")):
            action = submenu.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode == "single")
            action.triggered.connect(lambda _c=False, m=mode: self.set_split_mode(m))
            group.addAction(action)
            self._split_actions[mode] = action
