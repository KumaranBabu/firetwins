"""Task-based icons: every glyph renders, every menu entry and tree row of both applications has one."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QByteArray, Qt                      # noqa: E402
from PySide6.QtGui import QImage, QPainter                     # noqa: E402
from PySide6.QtSvg import QSvgRenderer                         # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QToolBar  # noqa: E402

from pyfds.api import FdsApi                                   # noqa: E402
from pyfds.gui import icons                                    # noqa: E402
from pyfds.gui.icon_glyphs import GLYPHS, TASK_COLORS          # noqa: E402

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _opaque_pixels(svg: str) -> int:
    r = QSvgRenderer(QByteArray(svg.encode()))
    assert r.isValid()
    img = QImage(48, 48, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    r.render(p)
    p.end()
    return sum(1 for y in range(48) for x in range(48) if img.pixelColor(x, y).alpha() > 40)


def test_every_glyph_is_valid_svg_and_draws_something():
    for key in GLYPHS:
        n = _opaque_pixels(icons.svg_text(key))
        assert n > 60, f"glyph {key!r} is nearly empty ({n} pixels)"


def test_glyphs_are_multi_coloured_and_every_task_is_used():
    for key, (task, body) in GLYPHS.items():
        assert task in TASK_COLORS, key
        assert any(t in body for t in ("@c", "@d", "@l")) or "#" in body, key      # drawn in the task colour
    assert {t for t, _ in GLYPHS.values()} == set(TASK_COLORS)
    multi = [k for k, (_, b) in GLYPHS.items() if sum(t in b for t in ("@c", "@d", "@l", "#")) >= 2]
    assert len(multi) > len(GLYPHS) * 0.8                      # almost all glyphs use more than one colour


def test_every_name_in_the_rules_is_a_real_glyph():
    used = {k for _, k in icons.TEXT_RULES} | set(icons.ENTITY_GLYPHS.values()) | set(icons.NODE_KIND_GLYPHS.values())
    used |= {k for _, k in icons.NODE_LABEL_RULES} | {g for _, g in icons._DEVICE_QUANTITIES}
    assert not used - set(GLYPHS)


def test_wording_picks_the_right_icon():
    g = icons.glyph_for_text
    assert g("&Save As...") == "saveas" and g("Save &Movie...") == "movie" and g("&Undo") == "undo"
    assert g("Add &Heat Flux Sensor...") == "heatflux" and g("Add &Smoke Detector...") == "smokedet"
    assert g("Draw &Cylinder...") == "cylinder" and g("&Validate Project") == "validate" and g("&Run Simulation...") == "run"
    assert g("Data&3D: Add Isosurface...") == "iso" and g("&Time History Plot...") == "chart"
    assert g("Something nobody planned for") is None
    assert not icons.icon_for_text("Something nobody planned for", menu="Draw").isNull()   # falls back to a dot in the menu's colour


def test_icon_variants_and_cache():
    a, b = icons.icon("flame"), icons.icon("flame")
    assert a is b and not a.isNull()
    assert not icons.icon("flame", gray=True).isNull() and icons.icon("dot", task="fire") is not icons.icon("dot", task="geometry")
    assert icons.icon("no-such-glyph").cacheKey() == icons.icon("dot").cacheKey()


def test_main_window_every_menu_entry_and_toolbar_button_has_an_icon():
    from pyfds.gui.main_window import MainWindow
    w = MainWindow(FdsApi())

    def walk(menu, out):
        for a in menu.actions():
            if a.isSeparator():
                continue
            out.append(a)
            if a.menu():
                walk(a.menu(), out)
        return out

    acts = []
    for top in w.menuBar().actions():
        walk(top.menu(), acts)
    assert len(acts) > 100
    missing = [a.text() for a in acts if a.icon().isNull()]
    assert not missing, missing
    bar = w.findChildren(QToolBar)[0]
    assert all(not a.icon().isNull() for a in bar.actions() if not a.isSeparator())
    assert not w.windowIcon().isNull()
    w.close()


def test_project_explorer_rows_have_icons_and_disabled_ones_are_grey():
    from pyfds.gui.main_window import MainWindow
    w = MainWindow(FdsApi())
    w.api.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1), name="M")
    w.api.devices.add_device(name="TC", quantity="TEMPERATURE", xyz=(0.5, 0.5, 0.5)) if hasattr(w.api.devices, "add_device") else None
    top = [w.explorer.topLevelItem(i) for i in range(w.explorer.topLevelItemCount())]
    assert top and all(not t.icon(0).isNull() for t in top)
    rows, stack = [], list(top)
    while stack:
        item = stack.pop()
        rows.append(item)
        stack.extend(item.child(i) for i in range(item.childCount()))
    assert rows and all(not r.icon(0).isNull() for r in rows)
    assert icons.icon_for_entity("devices", type("D", (), {"quantity": "LINK TEMPERATURE"})()).cacheKey() == icons.icon("heatdet").cacheKey()
    assert icons.icon_for_entity("devices", type("D", (), {"quantity": "TEMPERATURE"})()).cacheKey() == icons.icon("thermometer").cacheKey()
    w.close()


def test_results_window_menus_tree_and_play_button(monkeypatch, tmp_path):
    from pyfds.gui.results.window import ResultsWindow
    shutil.copytree(FIX, tmp_path / "r")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    w = ResultsWindow(FdsApi())
    w.viewer.open_results(str(tmp_path / "r" / "rroom.smv"))
    w.sync(True)
    acts = []

    def walk(menu):
        for a in menu.actions():
            if not a.isSeparator():
                acts.append(a)
                if a.menu():
                    walk(a.menu())
    for top in w.menuBar().actions():
        walk(top.menu())
    assert len(acts) > 60 and not [a.text() for a in acts if a.icon().isNull()]
    items = list(w.tree._items.values())
    assert items and all(not it.icon(0).isNull() for it in items)
    before = w.play_btn.icon().cacheKey()
    w._play_ui(True)
    assert w.play_btn.text() == "Pause" and w.play_btn.icon().cacheKey() != before
    w._play_ui(False)
    assert w.play_btn.text() == "Play" and w.play_btn.icon().cacheKey() == before
    assert not w.windowIcon().isNull()
    w.close()
