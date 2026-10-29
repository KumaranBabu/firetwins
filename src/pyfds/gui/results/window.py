"""The results viewer window: menus, navigation tree, 3D view, time controls, status bar.

Everything it does goes through ``api.viewer`` (the same calls scripts and the agent use); this file only
turns clicks into those calls and redraws. Errors from the API are shown in a message box, never swallowed.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import QItemSelectionModel, QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QDockWidget, QFileDialog, QMainWindow, QMessageBox, QWidget

from pyfds.api.viz import RectilinearVolume
from pyfds.api.viz import timelines as tml
from .forms import SettingsDialog
from .nav_tree import NavTree
from .viewport import ResultsViewport

from .window_files import (  # noqa: F401  (re-exported)
    ResultsWindowFilesMixin,
)
from .window_menus import (  # noqa: F401  (re-exported)
    ResultsWindowMenusMixin,
)
from .window_record import ResultsWindowRecordMixin  # noqa: F401
from .window_analysis import ResultsAnalysisMixin
from .window_timebar import (  # noqa: F401  (re-exported)
    ResultsWindowTimebarMixin,
)
from .window_tools import (  # noqa: F401  (re-exported)
    ResultsWindowToolsMixin,
)
from .window_layout import ResultsLayoutMixin
from .window_common import (  # noqa: F401  (re-exported)
    _SMV_FILTER,
    _VIZ_FILTER,
)



class ResultsWindow(ResultsLayoutMixin, ResultsAnalysisMixin, ResultsWindowRecordMixin, ResultsWindowTimebarMixin, ResultsWindowMenusMixin, ResultsWindowFilesMixin, ResultsWindowToolsMixin, QMainWindow):
    def __init__(self, api, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.viewer = api.viewer
        self.selected = None                         # the PickInfo last clicked in the 3D view
        self.setWindowTitle("PyFDS Results")
        self.resize(1280, 800)
        self.view = ResultsViewport(self)
        self.viewer.renderer = self.view.make_renderer(self.viewer)
        self.setCentralWidget(self.view)
        self.tree = NavTree(self.viewer, self)
        dock = QDockWidget("Navigation View", self)
        dock.setWidget(self.tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.tree.toggled_node.connect(self._toggle)
        self.view.on_click = self.pick_at
        QShortcut(QKeySequence("Escape"), self, activated=lambda: self.select(None))
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self._build_time_bar()
        self._build_record_controls()
        self._build_menus()
        from .parity import install_parity
        install_parity(self)
        from .tenability_dialog import install as install_tenability
        install_tenability(self)
        from pyfds.gui.menu_regroup import RESULTS_GROUPS, regroup
        regroup(self.menuBar(), RESULTS_GROUPS)
        from pyfds.gui.icons import install_icons
        install_icons(self, "results")
        self.statusBar().showMessage("No results loaded")
        self._build_layout()
        self.sync()
        self._record_ui()                            # icon installation re-enables the buttons

    # -- helpers ------------------------------------------------------------------------------------------------
    def _try(self, fn: Callable[[], Any], title: str = "Results") -> Any:
        try:
            return fn()
        except Exception as exc:
            QMessageBox.warning(self, title, f"{type(exc).__name__}: {exc}")
            return None

    def _act(self, menu, text: str, fn: Callable[[], Any], shortcut: Optional[str] = None, checkable: bool = False,
             checked: bool = False) -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        a.setChecked(checked)
        a.triggered.connect(lambda _c=False: self._try(fn, text.replace("&", "").rstrip(".")))
        menu.addAction(a)
        return a

    def sync(self, rebuild_tree: bool = False) -> None:
        """Redraw everything from the viewer's state."""
        v = self.viewer
        if rebuild_tree:
            self.view.adapter.selection = self.selected = None        # the tree is rebuilt: what was selected may be gone
            self.view.adapter.selections = []
            self.tree.rebuild()
        else:
            self.tree.refresh_states()
        pb = v.playback
        self.slider.blockSignals(True)
        self.slider.setRange(0, max((pb.n_frames - 1) if pb else 0, 0))
        self.slider.setValue(pb.index if pb else 0)
        self.slider.blockSignals(False)
        if pb:
            v.time = float(pb.time)
        self.time_label.setText(tml.format_elapsed(v.time) if pb else "-")
        self.draw()
        if getattr(self, "_status_hook", None):
            self._status_hook()
        title = Path(v.path).name if v.path else "untitled"
        self.setWindowTitle(f"PyFDS Results - {title}{' *' if v.dirty else ''}")
        if v.run is not None:
            self.statusBar().showMessage(f"{v.run.chid}: {len(v.active_leaves())} active, t = {v.time:.1f} s")

    def draw(self) -> None:
        try:
            fr = self.viewer.frame()
            self.view.adapter.draw(fr, self.viewer.viz, camera=bool(self.viewer.viz.active_view and fr.camera))
            if not self.view.interactive:
                return
            t0 = time.perf_counter()
            self.view.plotter.render()
            slow = time.perf_counter() - t0
            if slow > 0.3 and not self.view.adapter.fast_volumes and any(isinstance(p, RectilinearVolume) and p.kind in ("smoke", "fire")
                                                                          for _, p in fr.items):
                # this graphics card needs seconds per smoke frame: switch to the software volume mapper (about 15x faster here)
                self.view.adapter.fast_volumes = True
                self.statusBar().showMessage(f"Smoke took {slow:.1f} s to draw: using the compatibility smoke renderer for smooth playback")
                self.draw()
        except Exception as exc:
            self.statusBar().showMessage(f"Could not draw: {exc}")

    # -- selecting in the 3D view ------------------------------------------------------------------------------
    def pick_at(self, x: int, y: int, add: Optional[bool] = None):
        """A click at display point (x, y) in the 3D view: select what is under it (nothing: clear the selection).
        With Ctrl or Alt held (*add*), the object is added to the selection, or taken out of it when it is already there."""
        if add is None:
            add = bool(QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.AltModifier))
        info = self.view.adapter.pick(x, y)
        if info is None and add:
            return None                       # a miss with Ctrl held keeps what is selected
        self.select(info, add)
        return info

    def select(self, info, add: bool = False) -> None:
        """Highlight *info* (a ``pick.PickInfo``) in the 3D view, select its row in the tree and describe it in the status bar."""
        self.view.adapter.select(info, add)
        chosen = self.view.adapter.selections
        if info is None:
            self.tree.clearSelection()
            self.statusBar().showMessage("Nothing selected")
        else:
            self.tree.clearSelection()
            for one in chosen:
                item = self.tree.item_for(one.node_id)
                if item is None:
                    continue
                p = item.parent()
                while p is not None:
                    p.setExpanded(True)
                    p = p.parent()
                item.setSelected(True)
            last = self.tree.item_for(chosen[-1].node_id) if chosen else None
            if last is not None:
                self.tree.setCurrentItem(last, 0, QItemSelectionModel.NoUpdate)
            self.statusBar().showMessage(f"{len(chosen)} objects selected" if len(chosen) > 1 else info.text)
        self.selected = info if chosen else None
        if self.view.interactive:
            self.view.plotter.render()

    # -- tree ----------------------------------------------------------------------------------------------------
    def _toggle(self, node_id: str) -> None:
        self._try(lambda: self.viewer.toggle(node_id))
        pb = self.viewer.playback
        if pb is not None and pb.playing and not self._timer.isActive():
            self._play_ui(True)
            self._timer.start()
        self.sync()

    # -- generic -------------------------------------------------------------------------------------------------------
    def _edit(self, title: str, obj: Any, apply: Callable[..., Any], choices=None) -> None:
        dlg = SettingsDialog(title, obj, self, choices)
        if dlg.exec() and (vals := dlg.values()):
            self._try(lambda: apply(**vals), title)
            self.sync()

    def _camera_changed(self) -> None:
        self.view.adapter.apply_camera(self.viewer.camera)
        self.sync()

    def _ask_file(self, open_: bool, title: str, filt: str, default: str = "") -> Optional[str]:
        fn = QFileDialog.getOpenFileName if open_ else QFileDialog.getSaveFileName
        path, _ = fn(self, title, default, filt)
        return path or None

    def closeEvent(self, event) -> None:                  # noqa: N802
        self._timer.stop()
        self._abort_recording()
        if self.viewer.dirty and self.viewer.path:
            r = QMessageBox.question(self, "Save changes?", "Save the results visualization before closing?",
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                event.ignore()
                return
            if r == QMessageBox.Save:
                self.viewer.save()
        self.view.shutdown()
        super().closeEvent(event)
