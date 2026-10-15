"""F1: PyroSim-style navigation tree, menu bar, units / scenario / floor selectors, themes, view actions."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui import theme  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win():
    from pyfds.gui.main_window import MainWindow
    w = MainWindow(FdsApi())
    yield w
    w.close()


def _tops(w):
    return [w.explorer.topLevelItem(i).text(0) for i in range(w.explorer.topLevelItemCount())]


def _all_items(w):
    out, stack = [], [w.explorer.topLevelItem(i) for i in range(w.explorer.topLevelItemCount())]
    while stack:
        it = stack.pop()
        out.append(it)
        stack.extend(it.child(i) for i in range(it.childCount()))
    return out


# -- navigation tree ---------------------------------------------------------------------------
def test_tree_follows_pyrosim_node_order(win):
    names = [t.split(" (")[0] for t in _tops(win)]
    assert names[:15] == ["Views", "Tags", "Meshes", "Zones", "Species", "Reactions", "Particles", "Materials",
                          "Surfaces", "Devices", "Controls", "Results", "HVAC", "Model", "Model Checks"]


def test_folders_hold_their_collections_and_total_their_counts(win):
    win.api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="o1")
    win.api.vents.add_vent([0, 1, 0, 0, 0, 1])
    model = next(win.explorer.topLevelItem(i) for i in range(win.explorer.topLevelItemCount())
                 if win.explorer.topLevelItem(i).text(0).startswith("Model ("))
    assert model.text(0) == "Model (2)"
    assert [model.child(i).text(0).split(" (")[0] for i in range(model.childCount())] == [
        "Obstructions", "Vents", "Holes", "Geoms", "Init Regions", "Groups"]
    assert win.explorer.category_item("obstructions").text(0) == "Obstructions (1)"
    assert win.explorer.category_item("nonsense") is None
    assert win.explorer.category_item("obstructions").parent() is model


def test_groups_are_real_folders_and_selection_counts_each_object_once(win):
    a = win.api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="a")
    b = win.api.obstructions.add_obstruction([3, 4, 0, 1, 0, 1], name="b")
    win.api.groups.create("pair")
    win.api.groups.assign(a, "pair")
    win.api.groups.assign(b, "pair")
    group_row = win.explorer.category_item("groups").child(0)
    assert group_row.text(0) == "pair" and [group_row.child(i).text(0) for i in range(group_row.childCount())] == ["a", "b"]
    win.explorer.select_entity("obstructions", a)         # selects the row in Obstructions AND the one in the group
    assert len(win.explorer.selectedItems()) == 2
    assert [e.name for _a, e in win.explorer.selected_entities()] == ["a"]
    win._on_select_all()
    assert {e.name for _a, e in win.explorer.selected_entities()} >= {"a", "b", "pair"}


def test_information_nodes(win):
    o = win.api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="o", tags=["office", "wall"])
    win.api.views.save_viewpoint("Plan")
    texts = [i.text(0) for i in _all_items(win)]
    assert "Plan (active)" in texts and "office (1)" in texts and "wall (1)" in texts
    assert any(t.startswith("MeshPresence") for t in texts)
    win.api.validation.set_enabled("MeshPresence", False)
    assert "MeshPresence (off)" in [i.text(0) for i in _all_items(win)]
    win.explorer.select_entity("obstructions", o)
    assert win.explorer.selected()[1] is o


def test_find_works_through_nested_rows(win):
    win.api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="Desk")
    row = win.explorer.find_entity_by_name("des")
    assert row is not None and row.text(0) == "Desk"
    assert win.explorer.find_entity_by_name("") is None


# -- menu bar ----------------------------------------------------------------------------------
def test_menu_bar_is_pyrosims_nine_plus_tools(win):
    tops = [a.text().replace("&", "") for a in win.menuBar().actions()]
    assert tops == ["File", "Edit", "Model", "Devices", "Output", "Analysis", "Results", "View", "Tools", "Help"]
    model = next(a.menu() for a in win.menuBar().actions() if a.text() == "&Model")
    subs = [a.text().replace("&", "") for a in model.actions() if a.menu() is not None]
    assert {"Draw", "HVAC", "Scenarios", "Floors"} <= set(subs)
    view = next(a.menu() for a in win.menuBar().actions() if a.text() == "&View")
    assert "Window" in [a.text().replace("&", "") for a in view.actions()]


def test_edit_menu_has_the_view_and_visibility_actions_with_pyrosim_keys(win):
    reg = win.action_registry
    keys = {i: reg.action(i).shortcut().toString() for i in
            ("edit.hide", "edit.show", "edit.filter", "edit.show_all", "edit.undo_view", "edit.redo_view")}
    assert keys == {"edit.hide": "Alt+Shift+H", "edit.show": "Alt+Shift+S", "edit.filter": "Alt+Shift+F",
                    "edit.show_all": "Alt+Shift+A", "edit.undo_view": "Ctrl+Shift+Z", "edit.redo_view": "Ctrl+Shift+Y"}
    assert not {"edit.replace", "edit.select_all", "edit.filter"} & set(reg.placeholders())


# -- toolbar selectors ----------------------------------------------------------------------------
def test_units_combo_drives_and_follows_the_project(win):
    assert win.units_combo.currentData() == "SI"
    win._on_units_chosen(win.units_combo.findData("EN"))
    assert win.api.units.system == "EN"
    win.api.units.set_system("SI")
    win._sync_shell_bars()
    assert win.units_combo.currentData() == "SI"
    win._on_units_imperial()
    assert win.api.units.system == "EN"
    win._on_units_metric()
    assert win.api.units.system == "SI"


def test_scenario_combo_lists_applies_and_resets(win):
    win.api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="box")
    win.api.scenarios.create("Door open")
    win._sync_shell_bars()
    assert [win.scenario_combo.itemText(i) for i in range(win.scenario_combo.count())] == ["Base model", "Door open"]
    win._on_scenario_chosen(1)
    assert win.api.scenarios.active == "Door open" and win.scenario_combo.currentText() == "Door open"
    win._on_scenario_chosen(0)
    assert win.api.scenarios.active is None and win.scenario_combo.currentText() == "Base model"


def test_floor_selector_isolates_one_floor_and_shows_all(win):
    low = win.api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="low")
    high = win.api.obstructions.add_obstruction([0, 1, 0, 1, 4, 5], name="high")
    win.api.floors.define_floor("Ground", 0, 3)
    win.api.floors.define_floor("First", 3, 6)
    win.api.floors.assign(low, "Ground")
    win.api.floors.assign(high, "First")
    win._sync_shell_bars()
    assert [win.floor_combo.itemText(i) for i in range(win.floor_combo.count())] == ["All floors", "Ground", "First"]
    win._on_floor_chosen(win.floor_combo.findData("First"))
    assert high.uid not in win.api.project.editor.hidden and low.uid in win.api.project.editor.hidden
    win._on_floor_chosen(0)
    assert not win.api.project.editor.hidden


# -- view and selection actions ----------------------------------------------------------------------
def _select(win, *objs):
    win.explorer.select_entities([("obstructions", o) for o in objs])


def test_hide_show_filter_show_all_from_the_selection(win):
    a = win.api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="a")
    b = win.api.obstructions.add_obstruction([3, 4, 0, 1, 0, 1], name="b")
    _select(win, a)
    win._on_hide_selected()
    assert win.api.project.editor.hidden == {a.uid}
    win._on_show_selected()
    assert not win.api.project.editor.hidden
    win._on_isolate_selected()
    assert win.api.project.editor.hidden == {b.uid} | {o.uid for o in []}
    win._on_show_all()
    assert not win.api.project.editor.hidden
    win.explorer.clearSelection()
    win._on_hide_selected()                            # nothing selected: a message, not an error
    assert not win.api.project.editor.hidden


def test_replace_previews_confirms_and_renames(win, monkeypatch):
    win.api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="Desk_1")
    answers = iter([("Desk", True), ("Table", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: next(answers))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    win._on_replace()
    assert win.api.obstructions.all()[0].name == "Table_1"
    answers2 = iter([("Table", True), ("Desk", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: next(answers2))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    win._on_replace()                                  # declined: nothing changes
    assert win.api.obstructions.all()[0].name == "Table_1"
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    win._on_replace()                                  # cancelled


def test_section_box_and_view_history_actions(win):
    a = win.api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="a")
    _select(win, a)
    win._on_section_box_around_selection()
    box = win.api.views.section_box()
    assert (box.x_min, box.x_max) == (-0.5, 1.5)
    win._on_undo_view()
    assert win.api.views.section_box() is None
    win._on_redo_view()
    assert win.api.views.section_box() is not None
    win._on_reset_section_box()
    assert win.api.views.section_box() is None
    win.explorer.clearSelection()
    win._on_section_box_around_selection()             # nothing selected: a message


# -- themes ---------------------------------------------------------------------------------------
def test_dark_theme_darkens_the_palette_and_light_restores_it():
    app = QApplication.instance()
    original = app.palette()
    try:
        theme.apply_theme("dark", app, remember=False)
        assert app.palette().color(QPalette.Window).lightness() < 80
        theme.apply_theme("light", app, remember=False)
        assert app.palette().color(QPalette.Window).lightness() > 150
    finally:
        app.setPalette(original)
    with pytest.raises(ValueError):
        theme.palette("sepia")


def test_theme_handler_applies_and_remembers(win, monkeypatch):
    seen = []
    monkeypatch.setattr("pyfds.gui.main_window.actions_shell.apply_theme", lambda name, *a, **k: seen.append(name))
    win._on_theme_chosen("dark")
    assert seen == ["dark"]


# -- context menu ---------------------------------------------------------------------------------------
def test_context_menu_copies_records_and_selects_referencing_objects(win, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    from pyfds.domain.model import Surface
    win.api.project.add_entity(Surface(name="PAINT"))
    paint = win.api.surfaces.get("PAINT")
    o1 = win.api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], "PAINT", name="o1")
    win.api.obstructions.add_obstruction([3, 4, 0, 1, 0, 1], "INERT", name="o2")
    labels = [a.text().replace("&", "") for a in win._build_entity_context_menu("obstructions", o1).actions()]
    assert {"Copy FDS Records", "Select Referencing Objects", "Hide", "Show Only Selection"} <= set(labels)
    win.explorer.select_entity("obstructions", o1)
    win._on_copy_fds_records()
    text = QApplication.clipboard().text()
    assert "&OBST" in text and "PAINT" in text
    win._on_select_referencing(paint)
    assert [e.name for _a, e in win.explorer.selected_entities()] == ["o1"]
    win._on_select_referencing(o1)                 # nothing refers to an obstruction: a message, selection unchanged
    assert [e.name for _a, e in win.explorer.selected_entities()] == ["o1"]
    win.explorer.clearSelection()
    win._on_copy_fds_records()                      # nothing selected: only a message


def test_copy_with_nothing_selected_says_so(win, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    win.explorer.clearSelection()
    win._on_copy_fds_records()
    assert shown and "nothing" in shown[0].lower()
