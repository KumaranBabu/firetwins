"""Menu entries and windows added after the first GUI shell: rooms/walls/stairs/roofs, typed surfaces, library
browser, run monitor and results viewer.

``install_extras(window)`` is called once by ``MainWindow``; it only uses ``window.api`` and
``window.dispatcher`` (the same tools the AI assistant calls, so everything is undoable and validated the
same way). Kept out of ``main_window.py`` so that file stays under its size limit.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QMenu, QMessageBox

from pyfds.agent.registry import get_tool

from .entity_dialogs import SchemaFormDialog
from .library_dialog import LibraryDialog
from .results_viewer import ResultsViewerDialog
from .room_dialog import RoomDialog


def _find_menu(parent: QMenu, title: str) -> Optional[QMenu]:
    for act in parent.actions():
        if act.menu() is not None and act.text().replace("&", "") == title:
            return act.menu()
    return None


def _find_action(menu: QMenu, text: str) -> Optional[QAction]:
    for act in menu.actions():
        if act.text().replace("&", "") == text:
            return act
    return None


def _rewire(act: Optional[QAction], handler: Callable) -> None:
    if act is None:
        return
    try:
        act.triggered.disconnect()
    except (RuntimeError, TypeError):
        pass
    act.triggered.connect(lambda _checked=False: handler())


def install_extras(w) -> None:
    api = w.api
    bar = w.menuBar()
    top = {a.text().replace("&", ""): a.menu() for a in bar.actions() if a.menu() is not None}

    # -- helpers ---------------------------------------------------------------
    def tool_dialog(tool_name: str, title: Optional[str] = None) -> None:
        tool = get_tool(tool_name)
        dlg = SchemaFormDialog(title or tool.name, tool.description, tool.input_schema, w)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            w.dispatcher.call(tool.name, dlg.values())
        except Exception as exc:
            QMessageBox.critical(w, "Could not complete", str(exc))

    def draw_room() -> None:
        dlg = RoomDialog([s.name for s in api.surfaces.all()], w)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            w.dispatcher.call("add_room", dlg.values())
        except Exception as exc:
            QMessageBox.critical(w, "Could not draw the room", str(exc))

    def library(category: Optional[str] = None) -> None:
        dlg = LibraryDialog(api, w, category)
        w._library_dialog = dlg
        dlg.exec()

    def open_boundaries() -> None:
        try:
            w.dispatcher.call("open_mesh_boundaries", {})
        except Exception as exc:
            QMessageBox.critical(w, "Could not open the boundaries", str(exc))

    def results_viewer(folder: Optional[str] = None) -> None:
        dlg = ResultsViewerDialog(api, w, folder)
        w._results_viewer = dlg                       # keep it alive (non-modal)
        dlg.show()

    def monitor(output_dir: Optional[str] = None) -> None:
        out = output_dir or getattr(w, "_last_run_dir", None)
        if not out:
            QMessageBox.information(w, "Monitor Simulation", "Start a run first (Analysis > Run Simulation).")
            return
        w.run_panel.watch(out, api.project.chid, api.project.params.t_end,
                          lambda: results_window(str(Path(out) / f"{api.project.chid}.smv")))
        w._show_messages(w.run_panel)

    # -- Draw -------------------------------------------------------------------
    draw = top.get("Draw")
    if draw is not None:
        draw.addSeparator()
        draw.addAction("Draw &Room (walls, door, window)...", draw_room)
        draw.addAction("Draw &Wall by Coordinates...", lambda: tool_dialog("add_wall", "Draw Wall by Coordinates"))
        draw.addAction("Draw Ro&of...", lambda: tool_dialog("add_roof", "Draw Roof"))

    # -- Model ------------------------------------------------------------------
    model = top.get("Model")
    if model is not None:
        model.addSeparator()
        model.addAction("&Library...", library)
        model.addAction("Add &Typed Surface (burner, supply, exhaust...)...",
                        lambda: tool_dialog("add_typed_surface", "Add Surface"))
        model.addAction("Add Complex &Stoichiometry Reaction...",
                        lambda: tool_dialog("add_complex_reaction", "Add Reaction"))
        model.addAction("Add &Liquid Fuel...", lambda: tool_dialog("add_liquid_fuel", "Add Liquid Fuel"))
        model.addAction("&Open Mesh Boundaries", open_boundaries)

    # -- File > Import > Import from Library ---------------------------------------
    file_menu = top.get("File")
    imp = _find_menu(file_menu, "Import") if file_menu else None
    if imp is not None:
        _rewire(_find_action(imp, "Import from Library..."), library)

    # -- Run > Monitor Simulation -----------------------------------------------------
    run = top.get("Run")
    if run is not None:
        _rewire(_find_action(run, "Monitor Simulation..."), monitor)

    # -- Results > Results Viewer -----------------------------------------------------
    results = top.get("Results")
    if results is not None:
        first = results.actions()[0] if results.actions() else None
        act = QAction("Results &Viewer...", results)
        act.triggered.connect(lambda _c=False: results_viewer())
        if first is not None:
            results.insertAction(first, act)
            results.insertSeparator(first)
        else:
            results.addAction(act)

    def results_window(smv: Optional[str] = None) -> None:
        w.open_in_results(smv)                # PyFDS Results is its own program (see results/launcher.py)

    if results is not None:
        act3d = QAction("Open PyFDS &Results", results)
        act3d.triggered.connect(lambda _c=False: results_window())
        anchor = results.actions()[0] if results.actions() else None
        if anchor is not None:
            results.insertAction(anchor, act3d)
        else:
            results.addAction(act3d)

    w._show_results_window = results_window
    w._show_run_monitor = monitor                    # used by Run > Run Simulation to open the monitor
    w._show_results_viewer = results_viewer
