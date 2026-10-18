"""V12 parity audit: every inventory row (V-nn) of docs/PYFDS.docx (appendix B) is either backed by something that exists
in the window / API / command line, or listed here as a known gap with the reason. Adding a feature means moving its row
from GAPS to ROWS; a row that silently appears in the plan without either fails the test."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QToolButton

from pyfds.api.facade import FdsApi
from pyfds.gui.results import dialogs
from pyfds.gui.results.window import ResultsWindow
from pyfds.results.viz import capture as cap

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"
PLAN = Path(__file__).parents[2] / "docs" / "PYFDS.docx"

# ("menu", top menu, item text start, shortcut or None) | ("api", attr of api.viewer) | ("cli", option)
# | ("tool", toolbar action text) | ("dialog", class in gui.results.dialogs) | ("node", tree group label) | ("status", attr)
ROWS = {
    "V-01": ("menu", "File", "New Results Visualization", "Ctrl+N"), "V-02": ("menu", "File", "Open Results Visualization", "Ctrl+O"),
    "V-03": ("menu", "File", "Save Results Visualization", "Ctrl+S"), "V-04": ("menu", "File", "Load Results", "Ctrl+Shift+L"),
    "V-05": ("menu", "File", "Unload FDS Results", None), "V-06": ("menu", "File", "Import Views", None),
    "V-07": ("menu", "File", "Load CSV File", None), "V-08": ("menu", "File", "Refresh Results", "F5"),
    "V-09": ("menu", "File", "Save Screenshot", "Ctrl+P"), "V-10": ("menu", "File", "Save Movie", None),
    "V-13": ("menu", "Preferences", "General", None), "V-14": ("menu", "File", "Exit", None),
    "V-15": ("menu", "Edit", "Clear Selection", "Esc"),
    "V-20": ("menu", "View", "Show Navigation View", None), "V-21": ("menu", "View", "Reset Camera", "Ctrl+R"),
    "V-22": ("menu", "View", "Time Display", None), "V-23": ("menu", "View", "Temperature Unit", None),
    "V-24": ("menu", "View", "Concentration Unit", None), "V-25": ("menu", "View", "Mass Fraction Unit", None),
    "V-26": ("menu", "View", "Floor Settings", None), "V-27": ("menu", "View", "Show Labels", None),
    "V-28": ("menu", "View", "Enable Motion Blur", None), "V-29": ("menu", "View", "Edit Skybox", None),
    "V-30": ("menu", "View", "Set 3D Window Size", None), "V-31": ("menu", "View", "Views and Tours", None),
    "V-32": ("menu", "View", "Views and Tours", None), "V-33": ("menu", "View", "Navigation Tool", None),
    "V-40": ("menu", "Analysis", "Time Settings", None), "V-41": ("menu", "Analysis", "FDS Preferences", None),
    "V-50": ("menu", "Help", "About", None),
    "V-60": ("tool", "Orbit"), "V-61": ("tool", "Top"), "V-62": ("tool", "Orthogonal"), "V-64": ("tool", "Dimension"),
    "V-65": ("tool", "Label"), "V-66": ("tool", "Floors"), "V-67": ("tool", "Skybox"), "V-70": ("tool", "Time controls"),
    "V-80": ("node", "Scene Geometry"), "V-81": ("node", "Views"), "V-82": ("node", "3D Smoke"), "V-83": ("node", "3D Slices"),
    "V-84": ("node", "Plot3D"), "V-85": ("node", "Isosurfaces"), "V-86": ("node", "2D Slices"), "V-87": ("node", "2D Slice Vectors"),
    "V-88": ("node", "Boundaries"), "V-89": ("node", "Particles"), "V-90": ("node", "Maximum Errors"),
    "V-91": ("node", "Dimensions"), "V-92": ("node", "XY Plot Data"),
    "V-93": ("api", "toggle"), "V-94": ("api", "node_state"), "V-95": ("api", "tree"), "V-96": ("api", "cache_frames"),
    "V-97": ("api", "cache_frames"), "V-98": ("api", "show_floors_for_selection"),
    "V-100": ("api", "set_smoke3d"), "V-101": ("api", "add_data3d_slice"), "V-103": ("api", "frame"), "V-104": ("api", "frame"),
    "V-105": ("api", "set_slice_vectors"), "V-106": ("api", "frame"), "V-107": ("api", "set_particles"), "V-108": ("api", "frame"),
    "V-120": ("menu", "Preferences", "Rendering", None), "V-121": ("menu", "Analysis", "FDS Preferences", None),
    "V-122": ("menu", "Analysis", "Time Settings", None), "V-123": ("menu", "Preferences", "3D Smoke", None),
    "V-124": ("api", "add_data3d_isosurface"), "V-125": ("api", "set_slice_vectors"), "V-126": ("api", "set_particles"),
    "V-127": ("dialog", "TourEditor"), "V-128": ("dialog", "SectionBoxDialog"), "V-129": ("menu", "Preferences", "Floors", None),
    "V-130": ("dialog", "SkyboxDialog"), "V-131": ("dialog", "ScreenshotDialog"), "V-132": ("dialog", "MovieDialog"),
    "V-12": ("plot", "save_image"), "V-11": ("menu", "File", "Save 360 Movie", None),
    "V-68": ("menu", "File", "Record Movie", "F9"),
    "V-133": ("api", "load_csv"), "V-134": ("menu", "Tools", "Time History Plot", None), "V-135": ("menu", "File", "Export Data", None),
    "V-136": ("menu", "Tools", "Add Dimension", None),
    "V-140": ("api", "save"), "V-141": ("api", "open_results"), "V-144": ("api", "import_views"),
    "V-145": ("cli", "-screenshot"), "V-146": ("menu", "File", "Save Results Visualization", "Ctrl+S"),
    "V-109": ("node", "Devices"), "V-147": ("status", "status_state"), "V-99": ("status", "pick_at"), "V-148": ("menu", "File", "Follow Running Case", None),
}

GAPS = {
    "V-63": "rendering mode is a toolbar drop-down (the five modes exist); no per-mode icons",
    "V-102": "Plot3D quantities are listed per quantity, not as one file entry with five quantities",
    "V-137": "PyroSim-side archive feature, already in the model application",
    "V-142": "the cache is `.pyfcache` (record index) plus in-memory frames, not `.tcframes` files",
    "V-143": "no per-user Results.props: preferences live in each .pyfdsv (a per-user file would sit under the user profile)",
    "V-42": "Pathfinder: out of scope", "V-69": "VR: out of scope",
}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    w = ResultsWindow(FdsApi())
    yield w
    w.close()


def plan_ids():
    """The ``V-nn`` ids in the first column of the handbook's tables (needs python-docx)."""
    docx = pytest.importorskip("docx")
    found = set()
    for table in docx.Document(str(PLAN)).tables:
        for row in table.rows:
            m = re.fullmatch(r"(V-\d{2,3})", row.cells[0].text.strip())
            if m:
                found.add(m.group(1))
    return found


def test_every_inventory_row_is_covered_or_a_stated_gap():
    ids = plan_ids()
    assert len(ids) > 80
    unaccounted = sorted(ids - set(ROWS) - set(GAPS))
    assert not unaccounted, f"inventory rows with neither a check nor a stated gap: {unaccounted}"
    assert not set(ROWS) & set(GAPS)


def _menu(win, title):
    for a in win.menuBar().actions():
        if a.menu() is not None and a.text().replace("&", "") == title:
            return a.menu()
    raise AssertionError(f"menu {title!r} missing")


def _walk(menu: QMenu):
    for a in menu.actions():
        yield a
        if a.menu() is not None:
            yield from _walk(a.menu())


@pytest.mark.parametrize("row", sorted(ROWS))
def test_row_exists(win, row):
    kind, *args = ROWS[row]
    if kind == "menu":
        top, text, key = args
        act = next((a for a in _walk(_menu(win, top)) if a.text().replace("&", "").startswith(text)), None)
        assert act is not None, f"{row}: {top} > {text} missing"
        if key:
            assert act.shortcut().toString().replace(" ", "") == key.replace(" ", ""), f"{row}: shortcut {key}"
    elif kind == "api":
        assert hasattr(win.viewer, args[0]), f"{row}: api.viewer.{args[0]} missing"
    elif kind == "cli":
        assert cap.parse_cli([args[0], "x.pyfdsv"]).screenshot
    elif kind == "tool":
        if args[0] == "Time controls":
            texts = {b.text() for b in win.findChildren(QToolButton)}
            assert {"|<", ">|", "÷2", "×2"} <= texts and win.loop.text() == "Loop" and win.slider is not None
        else:
            assert any(a.text() == args[0] for a in win.findChildren(QAction)), f"{row}: toolbar {args[0]} missing"
    elif kind == "dialog":
        assert hasattr(dialogs, args[0])
    elif kind == "node":
        win.viewer.open_results(str(FIX / "rroom.smv"))
        labels = {n.label for n in win.viewer.tree.walk()}
        assert args[0] in labels, f"{row}: tree group {args[0]} missing"
    elif kind == "plot":
        from pyfds.gui.results.plots import TimePlotDialog
        assert hasattr(TimePlotDialog, args[0])
    elif kind == "status":
        assert hasattr(win, args[0])
