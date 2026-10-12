"""The results viewer window: menus, navigation tree, 3D view, time controls, status bar.

Everything it does goes through ``api.viewer`` (the same calls scripts and the agent use); this file only
turns clicks into those calls and redraws. Errors from the API are shown in a message box, never swallowed.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDockWidget, QDoubleSpinBox, QFileDialog, QHBoxLayout,
                               QInputDialog, QLabel, QMainWindow, QMessageBox, QPushButton, QSlider, QToolBar, QVBoxLayout,
                               QWidget)

from pyfds.api.viz import RectilinearVolume
from pyfds.api.viz import capture as cap
from pyfds.api.viz import model as vm
from pyfds.api.viz import timelines as tml

from .forms import SettingsDialog
from .nav_tree import NavTree
from .viewport import ResultsViewport

_SMV_FILTER = "Smokeview files (*.smv)"
_VIZ_FILTER = "PyFDS results visualization (*.pyfdsv)"


class ResultsWindow(QMainWindow):
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
        self._build_menus()
        from .parity import install_parity
        install_parity(self)
        from pyfds.gui.icons import install_icons
        install_icons(self, "results")
        self.statusBar().showMessage("No results loaded")
        self.sync()

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

    # -- time controls ------------------------------------------------------------------------------------------
    def _build_time_bar(self) -> None:
        bar = QToolBar("Time", self)
        bar.setMovable(False)
        self.addToolBar(Qt.BottomToolBarArea, bar)
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self._play_pause)
        step_b, step_f = QPushButton("<"), QPushButton(">")
        from pyfds.gui.icons import icon
        self._play_ui(False)
        step_b.setIcon(icon("stepback"))
        step_f.setIcon(icon("stepfwd"))
        step_b.clicked.connect(lambda: self._step(-1))
        step_f.clicked.connect(lambda: self._step(1))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimumWidth(320)
        self.slider.valueChanged.connect(self._seek)
        self.time_label = QLabel("-")
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.1, 100.0)
        self.speed.setValue(self.viewer.viz.playback_speed)
        self.speed.setPrefix("x")
        self.speed.valueChanged.connect(lambda x: self._try(lambda: (self.viewer.set_speed(x), self._status_hook() if getattr(self, "_status_hook", None) else None)))
        self.loop = QCheckBox("Loop")
        self.loop.toggled.connect(self.viewer.set_loop)
        for w in (step_b, self.play_btn, step_f, self.slider, self.time_label, self.speed, self.loop):
            bar.addWidget(w)

    def _play_ui(self, playing: bool) -> None:
        from pyfds.gui.icons import icon
        self.play_btn.setText("Pause" if playing else "Play")
        self.play_btn.setIcon(icon("pause" if playing else "play"))

    def _play_pause(self) -> None:
        pb = self.viewer.playback
        if pb is None:
            return
        playing = pb.toggle()
        self._play_ui(playing)
        self._last_tick = None
        if playing:
            self.viewer.prefetch_async()
        (self._timer.start if playing else self._timer.stop)()

    def _tick(self) -> None:
        now = time.perf_counter()
        last, self._last_tick = getattr(self, "_last_tick", None), now
        if last and hasattr(self, "status_fps"):
            self.status_fps.setText(f"{1.0 / max(now - last, 1e-6):.0f} fps")
        pb = self.viewer.playback
        if pb is None:
            self._timer.stop()
            return
        pb.tick(min(max(now - last, self._timer.interval() / 1000.0), 0.5) if last else self._timer.interval() / 1000.0)   # real time: slow frames are skipped, not stretched
        if not pb.playing:
            self._timer.stop()
            self._play_ui(False)
        self.viewer.time = float(pb.time)
        self.sync()

    def _step(self, n: int) -> None:
        pb = self.viewer.playback
        if pb is not None:
            pb.step(n) if hasattr(pb, "step") else pb.seek_index(max(0, min(pb.index + n, pb.n_frames - 1)))
            self.viewer.time = float(pb.time)
            self.sync()

    def _seek(self, i: int) -> None:
        pb = self.viewer.playback
        if pb is not None:
            pb.seek_index(i)
            self.viewer.time = float(pb.time)
            self.sync()

    # -- selecting in the 3D view ------------------------------------------------------------------------------
    def pick_at(self, x: int, y: int):
        """A click at display point (x, y) in the 3D view: select what is under it (nothing: clear the selection)."""
        info = self.view.adapter.pick(x, y)
        self.select(info)
        return info

    def select(self, info) -> None:
        """Highlight *info* (a ``pick.PickInfo``) in the 3D view, select its row in the tree and describe it in the status bar."""
        self.view.adapter.select(info)
        if info is None:
            self.tree.clearSelection()
            self.statusBar().showMessage("Nothing selected")
        else:
            item = self.tree.item_for(info.node_id)
            if item is not None:
                p = item.parent()
                while p is not None:
                    p.setExpanded(True)
                    p = p.parent()
                self.tree.setCurrentItem(item)
            self.statusBar().showMessage(info.text)
        self.selected = info
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

    # -- menus ------------------------------------------------------------------------------------------------------
    def _build_menus(self) -> None:
        mb = self.menuBar()
        v = self.viewer
        f = mb.addMenu("&File")
        self._act(f, "&New Results Visualization", lambda: (v.new(), self.sync(True)))
        self._act(f, "&Open Results Visualization...", self.open_visualization, "Ctrl+O")
        self._act(f, "Open &Results (.smv)...", self.open_results)
        self._act(f, "&Save Results Visualization", self.save, "Ctrl+S")
        self._act(f, "Save &As...", self.save_as)
        f.addSeparator()
        self._act(f, "&Load Results...", self.load_results)
        self._act(f, "&Unload FDS Results", lambda: (v.unload_results(), self.sync(True)))
        self._act(f, "Re&fresh Results", self.refresh, "F5")
        self._act(f, "Load &CSV File...", self.load_csv)
        f.addSeparator()
        self._act(f, "&Import Views...", self.import_views)
        self._act(f, "&Export Views...", self.export_views)
        self._act(f, "Export &Data (CSV)...", self.export_data)
        f.addSeparator()
        self._act(f, "Save &Screenshot...", self.screenshot, "Ctrl+P")
        self._act(f, "Save &Movie...", self.movie)
        self._act(f, "Save &360 Movie...", self.movie360)
        f.addSeparator()
        self._act(f, "&Close", self.close)

        vw = mb.addMenu("&View")
        for name, label in (("top", "&Top"), ("front", "&Front"), ("side", "&Side"), ("isometric", "&Reset Camera")):
            self._act(vw, label, lambda n=name: (v.standard_view(n), self._camera_changed()))
        vw.addSeparator()
        grp = QActionGroup(self)
        for proj in ("perspective", "orthogonal"):
            a = self._act(vw, proj.capitalize(), lambda p=proj: (v.set_projection(p), self._camera_changed()),
                          checkable=True, checked=v.camera.projection == proj)
            grp.addAction(a)
        nav = vw.addMenu("&Navigation Tool")
        g2 = QActionGroup(self)
        for tool in ("orbit", "pan", "zoom", "roam", "smokeview"):
            g2.addAction(self._act(nav, tool.capitalize(), lambda t=tool: v.set_navigation(t), checkable=True,
                                   checked=v.camera.navigation == tool))
        rm = vw.addMenu("Rendering &Mode")
        for m in vm.RENDER_MODES:
            self._act(rm, m.replace("_", " ").capitalize(), lambda x=m: (v.set_rendering_mode(x), self.sync()))
        gs = vw.addMenu("&Geometry Set")
        for g in vm.GEOMETRY_SETS:
            self._act(gs, g.replace("_", " ").upper() if g == "ge1" else g.replace("_", " ").title(),
                      lambda x=g: (v.set_geometry_set(x), self.sync(True)))
        vw.addSeparator()
        self._act(vw, "New &View...", self.new_view)
        self._act(vw, "New T&our...", self.new_tour)
        self._act(vw, "&Default View", lambda: (v.activate_view(None), self.sync(True)))
        self._act(vw, "Add &Section Box", lambda: (v.add_section_box(), self.sync(True)))
        self._act(vw, "Remove Section Box", lambda: (v.remove_section_box(), self.sync()))
        self._act(vw, "Set Section &Plane...", self.section_plane)
        vw.addSeparator()
        self._act(vw, "Show &Dimensions", lambda: (v.show_annotations(dimensions=not v.viz.show_dimensions), self.sync()),
                  checkable=True, checked=v.viz.show_dimensions)
        self._act(vw, "Show &Labels", lambda: (v.show_annotations(labels=not v.viz.show_labels), self.sync()),
                  checkable=True, checked=v.viz.show_labels)

        tl = mb.addMenu("&Tools")
        self._act(tl, "Add &Dimension...", self.add_dimension)
        self._act(tl, "Add &Label...", self.add_label)
        self._act(tl, "Add Tour &Keyframe at Current Time", lambda: (v.add_keyframe(), self.sync()))
        tl.addSeparator()
        self._act(tl, "&Time History Plot...", self.time_plot)
        self._act(tl, "Data&3D: Add Isosurface...", self.add_iso)

        pf = mb.addMenu("&Preferences")
        self._act(pf, "&FDS Preferences...", self.fds_prefs)
        self._act(pf, "&Colorbar...", self.colorbar_prefs)
        self._act(pf, "3D S&moke...", lambda: self._edit("3D Smoke", v.viz.smoke3d, v.set_smoke3d,
                                                          {"preset": vm.SMOKE_PRESETS, "fire_rendering": ("radiant", "volumetric")}))
        self._act(pf, "&Units...", lambda: self._edit("Units", v.viz.units, v.set_units, {
            "temperature": ("C", "F", "K"), "concentration": ("ppm", "fraction", "percent"), "mass_fraction": ("kg/kg", "g/kg")}))
        self._act(pf, "T&imelines...", lambda: self._edit("Timelines", v.viz.timelines, lambda **k: v.set_timelines(**k), {
            "display_format": ("regional", "iso8601"), "view_timeline": ("automatic", "custom")}))
        self._act(pf, "&General...", lambda: self._edit("General", v.viz.general, lambda **k: v.set_general(**k)))
        self._act(pf, "&Rendering...", self.rendering_prefs)
        self._act(pf, "Fl&oors...", self.floors)
        self._act(pf, "&Time Display...", self.time_display)

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

    # -- file ------------------------------------------------------------------------------------------------------------
    def open_visualization(self) -> None:
        if p := self._ask_file(True, "Open Results Visualization", _VIZ_FILTER):
            self.viewer.open_visualization(p)
            self.sync(True)

    def open_results(self, smv: Optional[str] = None) -> None:
        if smv or (smv := self._ask_file(True, "Open Results", _SMV_FILTER)):
            self.viewer.open_results(smv)
            self.sync(True)

    def load_results(self) -> None:
        if p := self._ask_file(True, "Load Results", _SMV_FILTER):
            self.viewer.load_results(p)
            self.sync(True)

    def save(self) -> None:
        if not self.viewer.path:
            return self.save_as()
        self.viewer.save()
        self.sync()

    def save_as(self) -> None:
        if p := self._ask_file(False, "Save Results Visualization", _VIZ_FILTER, self.viewer.path or ""):
            self.viewer.save(p)
            self.sync()

    def refresh(self) -> None:
        info = self.viewer.refresh()
        self.sync(info["reloaded"])
        self.statusBar().showMessage(f"Refreshed: {info['records']} new frame record(s)")

    def load_csv(self) -> None:
        if p := self._ask_file(True, "Load CSV File", "CSV files (*.csv);;All files (*)"):
            try:
                self.viewer.load_csv(p)
            except ValueError as exc:                       # unknown layout: ask for the header rows
                dlg = SettingsDialog("CSV layout", __import__("pyfds.api.viz", fromlist=["csvload"]).csvload.guess_type(p), self,
                                     hide=("path", "csv_type"), note=f"{exc}\nDescribe the header rows (1-based; 0 = none).")
                if dlg.exec():
                    self.viewer.load_csv(p, **dlg.values())
            self.sync(True)

    def import_views(self) -> None:
        if p := self._ask_file(True, "Import Views", "Views (*.json *.pyfdsv);;All files (*)"):
            self.viewer.import_views(p)
            self.sync(True)

    def export_views(self) -> None:
        if p := self._ask_file(False, "Export Views", "Views (*.json)"):
            self.viewer.export_views(p)

    def export_data(self) -> None:
        ids = list(self.viewer.csv_series())
        if not ids:
            raise ValueError("no time series are loaded: use File > Load CSV File, or add a Data3D point")
        pick, ok = QInputDialog.getItem(self, "Export Data", "Series", ids, 0, False)
        if ok and (p := self._ask_file(False, "Export Data", "CSV (*.csv);;Tab separated (*.tsv)")):
            n = self.viewer.export_data([pick], p, tab_separated=p.lower().endswith(".tsv"))
            self.statusBar().showMessage(f"Wrote {n} rows to {p}")

    def screenshot(self) -> None:
        from .dialogs import ScreenshotDialog
        d = ScreenshotDialog(self.viewer, self, (self.view.width(), self.view.height()))
        if d.exec():
            done = self.viewer.render_screenshots(d.shots(), self.view.make_renderer(self.viewer), d.size())
            self.statusBar().showMessage(f"Saved {len(done)} image(s)")

    def movie(self) -> None:
        from .dialogs import MovieDialog
        if self.viewer.playback is None:
            raise ValueError("nothing animated is active: switch on a slice, smoke or particles first")
        d = MovieDialog(self.viewer, self, (min(self.view.width(), 1920), min(self.view.height(), 1080)))
        if d.exec():
            plan = d.plan()
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                res = self.viewer.render_movie(plan, self.view.make_renderer(self.viewer), d.view.currentText())
            finally:
                QApplication.restoreOverrideCursor()
            QMessageBox.information(self, "Movie", f"{res['frames']} frames -> {res['path']}" if res["encoded"] else
                                    f"No video encoder found; the {res['frames']} frames were kept in {res['frames_dir']}")

    def movie360(self) -> None:
        from .dialogs import MovieDialog
        from .scene_adapter import make_panorama_renderer
        if self.viewer.playback is None:
            raise ValueError("nothing animated is active: switch on a slice, smoke or particles first")
        d = MovieDialog(self.viewer, self, panorama=True)
        d.path.setText("movie360.mp4")
        if d.exec():
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                res = self.viewer.render_movie(d.plan(), make_panorama_renderer(self.viewer), d.view.currentText())
            finally:
                QApplication.restoreOverrideCursor()
            QMessageBox.information(self, "360 Movie", f"{res['frames']} frames -> {res['path']}" if res["encoded"] else
                                    f"No video encoder found; the {res['frames']} frames were kept in {res['frames_dir']}")

    # -- views / tools -----------------------------------------------------------------------------------------------
    def new_view(self) -> None:
        name, ok = QInputDialog.getText(self, "New View", "Name")
        if ok:
            if self.view.interactive:                       # record what the user is looking at
                self.viewer.set_camera(self.view.adapter.read_camera(self.viewer.camera))
            self.viewer.new_view(name or None)
            self.sync(True)

    def new_tour(self) -> None:
        name, ok = QInputDialog.getText(self, "New Tour", "Name")
        if ok:
            self.viewer.new_tour(name or None)
            self.sync(True)

    def section_plane(self) -> None:
        plane, ok = QInputDialog.getItem(self, "Section plane", "Plane", ["x_min", "x_max", "y_min", "y_max", "z_min", "z_max"], 0, False)
        if ok:
            val, ok2 = QInputDialog.getDouble(self, "Section plane", "Position (m)", 0.0, -1e6, 1e6, 3)
            if ok2:
                if not self._has_section():
                    self.viewer.add_section_box()
                self.viewer.set_section_plane(plane, val)
                self.sync(True)

    def _has_section(self) -> bool:
        from pyfds.api.viz import views as vw
        return vw.active_section(self.viewer.viz) is not None

    def add_dimension(self) -> None:
        text, ok = QInputDialog.getText(self, "Dimension", "Two points  x1,y1,z1  x2,y2,z2")
        if ok:
            nums = [float(s) for s in text.replace(",", " ").split()]
            if len(nums) != 6:
                raise ValueError("give six numbers: x1 y1 z1 x2 y2 z2")
            self.viewer.add_dimension(nums[:3], nums[3:])
            self.sync()

    def add_label(self) -> None:
        text, ok = QInputDialog.getText(self, "Label", "Text")
        if ok and text:
            pt, ok2 = QInputDialog.getText(self, "Label", "Anchor point  x,y,z")
            if ok2:
                nums = [float(s) for s in pt.replace(",", " ").split()]
                self.viewer.add_label(text, nums)
                self.sync()

    def add_iso(self) -> None:
        groups = [n for n in self.viewer.tree.walk() if any(c.kind in ("slice3d", "plot3d") for c in n.leaves()) and n.kind == "group"
                  and n.children and any(ch.kind == "group" and ch.label in ("Points", "Slices", "Isosurfaces") for ch in n.children)]
        if not groups:
            raise ValueError("this run has no 3D Slices or Plot3D quantities")
        pick, ok = QInputDialog.getItem(self, "Data3D", "Quantity", [g.id for g in groups], 0, False)
        if ok:
            val, ok2 = QInputDialog.getDouble(self, "Data3D", "Isosurface value", 100.0, -1e9, 1e9, 3)
            if ok2:
                self.viewer.add_data3d_isosurface(pick, val)
                self.sync(True)

    def time_plot(self) -> None:
        from .plots import TimePlotDialog
        dlg = TimePlotDialog(self.viewer, self)
        self._plot = dlg
        dlg.show()

    # -- preferences -------------------------------------------------------------------------------------------------
    def fds_prefs(self) -> None:
        self._edit("FDS Preferences", self.viewer.viz.fds, lambda **k: self.viewer.set_fds_preferences(**k),
                   hide=("colorbars", "obscure_types"))

    def colorbar_prefs(self) -> None:
        qs = [q for q, _, _ in self.viewer.colorbars()] or list({l.quantity for l in self.viewer.tree.leaves() if l.quantity})
        if not qs:
            raise ValueError("no quantities to set a colorbar for: load results first")
        q, ok = QInputDialog.getItem(self, "Colorbar", "Quantity", qs, 0, False)
        if ok:
            from matplotlib import colormaps
            self._edit(f"Colorbar - {q}", self.viewer.viz.fds.colorbar(q), lambda **k: self.viewer.set_colorbar(q, **k),
                       {"colormap": sorted(colormaps)[:60] if False else ("turbo", "viridis", "jet", "rainbow", "hot", "coolwarm",
                                                                         "gray", "plasma", "inferno"),
                        "color_source": ("colormap", "constant"),
                        "opacity_source": ("constant", "gradient", "feather_below", "feather_above")})

    def rendering_prefs(self) -> None:
        """Preferences > Rendering: every option, the two presets, and a note on which options take effect."""
        from .quality import NOTE
        choices = {"antialiasing": ("disabled", "smaa_1x", "smaa_2tx", "msaa_2", "msaa_4", "msaa_8", "msaa_16"),
                   "slice_renderer": ("hardware", "compatibility"),
                   "data3d_slice_renderer": ("hardware", "compatibility", "disabled"),
                   "smoke_renderer": ("hardware", "compatibility", "smokeview"),
                   "data3d_renderer": ("hardware", "compatibility", "disabled")}
        dlg = SettingsDialog("Rendering", self.viewer.viz.rendering, self, choices, note=NOTE)
        row = QHBoxLayout()
        for label, preset in (("Max Quality", "max_quality"), ("Max Compatibility", "max_compatibility")):
            b = QPushButton(label)
            b.clicked.connect(lambda _c=False, p=preset: (self._try(lambda: self.viewer.set_rendering(preset=p)), dlg.reject(), self.sync()))
            row.addWidget(b)
        dlg.layout().insertLayout(1, row)
        if dlg.exec() and (vals := dlg.values()):
            self._try(lambda: self.viewer.set_rendering(**vals), "Rendering")
            self.sync()

    def floors(self) -> None:
        text, ok = QInputDialog.getText(self, "Floors", "Z of each floor, metres (comma separated)",
                                        text=", ".join(str(z) for z in self.viewer.viz.floors.floors))
        if ok:
            levels = [float(s) for s in text.replace(",", " ").split()]
            self.viewer.set_floors(levels)
            self._edit("Floor layout", self.viewer.viz.floors, lambda **k: self.viewer.set_floor_layout(**k),
                       {"layout": ("vertical", "horizontal")}, hide=("floors", "visible"))

    def time_display(self) -> None:
        mode, ok = QInputDialog.getItem(self, "Time display", "Show", ["none", "time", "date_time"],
                                        ["none", "time", "date_time"].index(self.viewer.viz.time_display), False)
        if ok:
            self.viewer.set_time_display(mode)
            self.sync()

    def closeEvent(self, event) -> None:                  # noqa: N802
        self._timer.stop()
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
