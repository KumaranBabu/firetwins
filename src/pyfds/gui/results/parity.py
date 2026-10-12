"""The rest of the PyroSim-Results surface: shortcuts, Edit / Analysis / Help menus, unit and time-display submenus,
views-and-tours and floor items, main toolbar, tree right-click actions, status-bar fields and "follow running case".

``install_parity(win)`` is called once by :class:`ResultsWindow`. Every action calls ``api.viewer`` through
``win._try`` so errors show in a box. Which inventory row (``V-nn`` in docs/active_docs/SMV_RESULTS_VIEWER_PLAN.md) each
item closes is noted beside it and checked by ``tests/unit/test_viewer_parity.py``.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QInputDialog, QLabel, QMenu, QMessageBox, QToolBar, QToolButton, QWidget)

from pyfds.api.viz import model as vm
from pyfds.api.viz import timelines as tml

from . import dialogs as dlg
from .forms import SettingsDialog


def find_action(menu: QMenu, text: str) -> Optional[QAction]:
    for a in menu.actions():
        if a.text().replace("&", "").startswith(text):
            return a
    return None


def top_menu(win, title: str) -> Optional[QMenu]:
    for a in win.menuBar().actions():
        if a.menu() is not None and a.text().replace("&", "") == title:
            return a.menu()
    return None


def install_parity(win) -> None:
    v = win.viewer
    mb = win.menuBar()

    def shortcut(menu_title: str, text: str, keys: str) -> None:
        m = top_menu(win, menu_title)
        a = find_action(m, text) if m else None
        if a is not None:
            a.setShortcut(QKeySequence(keys))

    # -- shortcuts on existing items (V-01, V-04, V-21, V-146) ---------------------------------------------------
    shortcut("File", "New Results Visualization", "Ctrl+N")
    shortcut("File", "Load Results", "Ctrl+Shift+L")
    shortcut("View", "Reset Camera", "Ctrl+R")

    file_menu = top_menu(win, "File")
    file_menu.addSeparator()
    win._act(file_menu, "Follow Running Case (auto refresh)", lambda: _follow(win), checkable=True)
    win._act(file_menu, "E&xit", win.close, "Ctrl+Q")                                     # V-14

    # -- Edit (V-15) --------------------------------------------------------------------------------------------
    edit = QMenu("&Edit", win)
    mb.insertMenu(top_menu(win, "View").menuAction(), edit)
    win._act(edit, "&Clear Selection", lambda: win.tree.clearSelection(), "Esc")
    win._act(edit, "&Delete Selected", lambda: _delete_selected(win), "Del")

    # -- View additions ------------------------------------------------------------------------------------------------
    vw = top_menu(win, "View")
    first = vw.actions()[0]
    dock = next(d for d in win.findChildren(QWidget) if d.windowTitle() == "Navigation View")
    toggle = dock.toggleViewAction()
    toggle.setText("Show &Navigation View")                                               # V-20
    vw.insertAction(first, toggle)
    vw.insertSeparator(first)

    td = vw.addMenu("Time &Display")                                                      # V-22
    g = QActionGroup(win)
    for mode, label in (("date_time", "Date/Time"), ("time", "Time"), ("none", "None")):
        a = win._act(td, label, lambda m=mode: (v.set_time_display(m), win.sync()), checkable=True, checked=v.viz.time_display == mode)
        g.addAction(a)
    for title, field, items in (("&Temperature Unit", "temperature", (("Default (C)", "C"), ("Fahrenheit", "F"), ("Kelvin", "K"))),
                                ("&Concentration Unit", "concentration", (("Default (mol/mol)", "fraction"), ("PPM", "ppm"))),
                                ("&Mass Fraction Unit", "mass_fraction", (("Default (kg/kg)", "kg/kg"), ("PPM", "ppm")))):  # V-23..25
        m = vw.addMenu(title)
        grp = QActionGroup(win)
        for label, val in items:
            grp.addAction(win._act(m, label, lambda f=field, x=val: (v.set_units(**{f: x}), win.sync()), checkable=True,
                                   checked=getattr(v.viz.units, field) == val))
    vw.addSeparator()
    win._act(vw, "Floor &Settings...", win.floors)                                        # V-26, V-66
    win._act(vw, "Show &All Floors", lambda: (v.show_floors(None), win.sync()))
    win._act(vw, "Enable Motion &Blur", lambda: v.set_motion_blur(not v.viz.motion_blur), checkable=True, checked=v.viz.motion_blur)  # V-28
    win._act(vw, "Edit S&kybox...", lambda: _skybox(win))                                 # V-29
    win._act(vw, "Set 3D Window Si&ze...", lambda: _window_size(win))                     # V-30
    vt = vw.addMenu("Views and &Tours")                                                   # V-31, V-32
    win._act(vt, "New View", win.new_view)
    win._act(vt, "New tour", win.new_tour)
    win._act(vt, "Reset to Viewpoint", lambda: (v.activate_view(v.viz.active_view), win._camera_changed()))
    win._act(vt, "Save Viewpoint", lambda: (v.set_camera(win.view.adapter.read_camera(v.camera)) if win.view.interactive else None,
                                            v.save_viewpoint(), win.sync()))
    win._act(vt, "Edit tour...", lambda: _edit_tour(win))
    vt.addSeparator()
    win._act(vt, "Add section box", lambda: (v.add_section_box(), win.sync(True)))
    win._act(vt, "Edit section properties...", lambda: _section(win))
    win._act(vt, "Remove section box", lambda: (v.remove_section_box(), win.sync()))
    win._act(vt, "Enable Section Boxes", lambda: (v.enable_section_boxes(not _boxes_on(win)), win.sync()), checkable=True, checked=True)
    win._act(vt, "Duplicate View", lambda: (v.duplicate_views([v.viz.active_view]), win.sync(True)))

    # -- Analysis (V-40, V-41) ------------------------------------------------------------------------------------------------
    an = QMenu("&Analysis", win)
    mb.insertMenu(top_menu(win, "Preferences").menuAction(), an)
    win._act(an, "&Time Settings...", lambda: win._edit("Timelines", v.viz.timelines, lambda **k: v.set_timelines(**k), {
        "display_format": ("regional", "iso8601"), "view_timeline": ("automatic", "custom")}))
    win._act(an, "&FDS Preferences...", win.fds_prefs)
    win._act(an, "Cache Results for Smooth &Playback", lambda: _cache(win))

    # -- Help (V-50) -----------------------------------------------------------------------------------------------------------
    hp = mb.addMenu("&Help")
    win._act(hp, "&About PyFDS Results", lambda: QMessageBox.about(
        win, "About", "PyFDS Results\nA 3D viewer for FDS results (.smv) and saved visualizations (.pyfdsv)."))

    # -- tree right-click (V-97) and keys ------------------------------------------------------------------------------------------
    win.tree.context_requested.connect(lambda nid, pos: _tree_menu(win, nid, pos))
    win.tree.itemSelectionChanged.connect(lambda: _selection_changed(win))                # V-99 (tree side)

    # -- main toolbar (V-60..V-67) ---------------------------------------------------------------------------------------------------
    tb = QToolBar("Tools", win)
    tb.setMovable(False)
    win.addToolBar(Qt.TopToolBarArea, tb)
    grp = QActionGroup(win)
    for tool in ("orbit", "pan", "zoom", "roam"):
        a = QAction(tool.capitalize(), win)
        a.setCheckable(True)
        a.setChecked(v.camera.navigation == tool)
        a.triggered.connect(lambda _c=False, t=tool: win._try(lambda: v.set_navigation(t)))
        grp.addAction(a)
        tb.addAction(a)
    tb.addSeparator()
    for name, label in (("top", "Top"), ("front", "Front"), ("side", "Left side")):
        a = QAction(label, win)
        a.triggered.connect(lambda _c=False, n=name: win._try(lambda: (v.standard_view(n), win._camera_changed())))
        tb.addAction(a)
    proj = QAction("Orthogonal", win)
    proj.setCheckable(True)
    proj.toggled.connect(lambda on: win._try(lambda: (v.set_projection("orthogonal" if on else "perspective"), win._camera_changed())))
    tb.addAction(proj)
    tb.addSeparator()
    mode = QComboBox()
    for m in vm.RENDER_MODES:
        mode.addItem(m.replace("_", " ").capitalize(), m)
    mode.setCurrentIndex(vm.RENDER_MODES.index(v.viz.rendering_mode))
    mode.currentIndexChanged.connect(lambda i: win._try(lambda: (v.set_rendering_mode(mode.itemData(i)), win.sync())))
    tb.addWidget(mode)
    for label, fn in (("Dimension", win.add_dimension), ("Label", win.add_label), ("Floors", win.floors),
                      ("Skybox", lambda: _skybox(win))):
        a = QAction(label, win)
        a.triggered.connect(lambda _c=False, f=fn: win._try(f))
        tb.addAction(a)

    # -- extra time controls (V-70) -------------------------------------------------------------------------------------------------
    bar = next(b for b in win.findChildren(QToolBar) if b.windowTitle() == "Time")
    for text, fn in (("|<", lambda: win._seek(0)), (">|", lambda: win._seek(win.slider.maximum())),
                     ("÷2", lambda: win.speed.setValue(max(win.speed.value() / 2, 0.1))),
                     ("×2", lambda: win.speed.setValue(min(win.speed.value() * 2, 100.0)))):
        b = QToolButton()
        b.setText(text)
        b.clicked.connect(lambda _c=False, f=fn: f())
        bar.addWidget(b)

    # -- status bar (V-147) ------------------------------------------------------------------------------------------------------------
    win.status_state = QLabel("Stopped")
    win.status_time = QLabel("0:00.0")
    win.status_speed = QLabel("x1")
    win.status_fps = QLabel("")
    for w in (win.status_state, win.status_time, win.status_speed, win.status_fps):
        win.statusBar().addPermanentWidget(w)
    win._status_hook = lambda: _status(win)


# -- helpers ---------------------------------------------------------------------------------------------------------------------
def _status(win) -> None:
    pb = win.viewer.playback
    win.status_state.setText("Playing" if pb is not None and pb.playing else ("Paused" if pb is not None and pb.index else "Stopped"))
    win.status_time.setText(tml.format_elapsed(win.viewer.time))
    win.status_speed.setText(f"x{win.viewer.viz.playback_speed:g}")


def _follow(win) -> None:
    """File > Follow Running Case: refresh every 2 s so frames of a running FDS case appear as they are written."""
    t = getattr(win, "_follow_timer", None)
    if t is None:
        t = win._follow_timer = QTimer(win)
        t.setInterval(2000)
        t.timeout.connect(lambda: win._try(win.refresh) if win.viewer.run is not None else None)
    t.stop() if t.isActive() else t.start()


def _boxes_on(win) -> bool:
    from pyfds.api.viz import views as vw
    b = vw.active_section(win.viewer.viz)
    return bool(b and b.enabled)


def _section(win) -> None:
    d = dlg.SectionBoxDialog(win.viewer, win)
    if d.exec():
        d.apply()
        win.sync(True)


def _edit_tour(win) -> None:
    from pyfds.api.viz import views as vw
    name = win.viewer.viz.active_view
    if name is None or vw.active_tour(win.viewer.viz) is None:
        raise ValueError("select a tour in the Views group (or create one with New tour) first")
    dlg.TourEditor(win.viewer, name, win).exec()
    win.sync(True)


def _skybox(win) -> None:
    d = dlg.SkyboxDialog(win.viewer, win)
    if d.exec():
        win.viewer.set_skybox(**d.values())
        win.sync()


def _window_size(win) -> None:
    d = dlg.WindowSizeDialog(win.view.width(), win.view.height(), win)
    if d.exec():
        w, h = d.w.value(), d.h.value()
        if d.mode.currentText() == "Match Aspect Ratio":
            w = int(round(win.view.height() * w / h))
            h = win.view.height()
        win.resize(win.width() + (w - win.view.width()), win.height() + (h - win.view.height()))


def _cache(win) -> None:
    n = win.viewer.cache_frames()
    win.statusBar().showMessage(f"Cached {n} frame(s) for smooth playback")


def _delete_selected(win) -> None:
    """Delete key: removes selected Data3D objects, views, dimensions, labels and CSV series."""
    for it in win.tree.selectedItems():
        _delete_node(win, it.data(0, Qt.UserRole))
    win.sync(True)


def _delete_node(win, nid: str) -> None:
    v = win.viewer
    node = v.tree.find(nid)
    if node is None:
        return
    if node.kind.startswith("data3d_"):
        v.remove_data3d(node.data["obj_id"])
    elif node.kind == "view" and node.label != "Default":
        v.delete_view(node.label)
    elif node.kind == "dimension":
        v.remove_annotation("dimension", int(node.data["index"]))
    elif node.kind == "label":
        v.remove_annotation("label", int(node.data["index"]))
    elif node.kind == "csv":
        v.remove_csv(str(node.data["path"]))


def _selection_changed(win) -> None:
    sel = win.tree.selectedItems()
    if sel:
        win.statusBar().showMessage(sel[0].text(0).lstrip("●◐ "))


def _tree_menu(win, nid: str, pos) -> None:
    v = win.viewer
    node = v.node(nid)
    m = QMenu(win)
    leaf = node.is_leaf and node.kind != "group"
    if leaf:
        on = v.node_state(nid) != "none"
        m.addAction("Hide" if on else "Show", lambda: win._toggle(nid))
    if node.kind in ("smoke3d",) or node.label == "3D Smoke":
        m.addAction("Properties...", lambda: win._edit("3D Smoke", v.viz.smoke3d, v.set_smoke3d,
                                                       {"preset": vm.SMOKE_PRESETS, "fire_rendering": ("radiant", "volumetric")}))
    if node.kind == "slice_vectors":
        m.addAction("Properties...", lambda: _vector_props(win, nid))
    if node.kind == "particles":
        m.addAction("Properties...", lambda: _particle_props(win, node))
    if any(c.kind in ("slice3d", "plot3d") for c in node.leaves()) and node.kind == "group" and node.label != "Data3D":
        m.addAction("Add point...", lambda: win._try(lambda: _add_point(win, nid)))
        m.addAction("Add slice...", lambda: win._try(lambda: _add_slice(win, nid)))
        m.addAction("Add isosurface...", lambda: win._try(lambda: _add_iso(win, nid)))
        m.addAction("Data3D Properties...", lambda: win._try(lambda: _data3d_props(win, nid)))
    if node.kind == "data3d_point":
        m.addAction("Show Plot", lambda: win.time_plot())
    if node.kind.startswith("data3d_"):
        m.addAction("Delete", lambda: win._try(lambda: (_delete_node(win, nid), win.sync(True))))
    if leaf and node.kind not in ("view", "geometry"):
        m.addAction("Cache results for smooth playback", lambda: win._try(lambda: (v.cache_frames([nid]), None)))
    if node.kind == "view":
        m.addAction("Show viewpoint", lambda: win._try(lambda: (v.activate_view(None if node.label == "Default" else node.label),
                                                                win._camera_changed())))
        m.addAction("Save viewpoint", lambda: win._try(lambda: (v.activate_view(node.label), v.save_viewpoint(node.label))))
        m.addAction("Edit tour...", lambda: win._try(lambda: (v.activate_view(node.label), _edit_tour(win))))
        m.addAction("Duplicate view", lambda: win._try(lambda: (v.duplicate_views([node.label]), win.sync(True))))
        if node.label != "Default":
            m.addAction("Delete", lambda: win._try(lambda: (v.delete_view(node.label), win.sync(True))))
    if not m.isEmpty():
        m.exec(pos)


def _vector_props(win, nid: str) -> None:
    node = win.viewer.node(nid)
    p = win.viewer.viz.slice_vectors.get(node.quantity + "|" + node.label, vm.SliceVectorProps())
    win._edit("Slice Vector Properties", p, lambda **k: win.viewer.set_slice_vectors(nid, **k))


def _particle_props(win, node) -> None:
    cls = str(node.data.get("class", node.label))
    p = win.viewer.viz.particles.get(cls, vm.ParticleProps())
    win._edit(f"Particle Properties - {cls}", p, lambda **k: win.viewer.set_particles(cls, **k))


def _data3d_props(win, nid: str) -> None:
    cur = win.viewer.viz.data3d.get(nid, vm.Data3DProps())
    win._edit("Data3D Properties", cur, lambda sample_factor: win.viewer.set_data3d_properties(nid, sample_factor))


def _nums(text: str, n: int) -> list:
    vals = [float(s) for s in text.replace(",", " ").split()]
    if len(vals) != n:
        raise ValueError(f"give {n} numbers, got {len(vals)}")
    return vals


def _add_point(win, nid: str) -> None:
    text, ok = QInputDialog.getText(win, "Add Point", "Location  x, y, z (m)")
    if ok:
        win.viewer.add_data3d_point(nid, _nums(text, 3))
        win.sync(True)


def _add_slice(win, nid: str) -> None:
    text, ok = QInputDialog.getText(win, "Add Slice", "Plane  origin x y z  normal x y z")
    if ok:
        n = _nums(text, 6)
        win.viewer.add_data3d_slice(nid, n[:3], n[3:])
        win.sync(True)


def _add_iso(win, nid: str) -> None:
    val, ok = QInputDialog.getDouble(win, "Add Isosurface", "Value", 100.0, -1e9, 1e9, 3)
    if ok:
        win.viewer.add_data3d_isosurface(nid, val)
        win.sync(True)
