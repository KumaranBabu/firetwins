"""F5: the generic collection editor dialog (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFormLayout, QInputDialog, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.editors.collection_editor import EntityCollectionEditor, changed_tokens  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="A")
    a.meshes.add_mesh([10, 10, 10], [1, 2, 0, 1, 0, 1], name="B")
    return a


@pytest.fixture
def editor(api, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    ed = EntityCollectionEditor(api, "meshes", "Edit Meshes")
    yield ed
    ed.close()


def _tab_names(ed):
    return [ed.tabs.tabText(i) for i in range(ed.tabs.count())]


def test_lists_objects_and_builds_category_tabs(editor):
    assert editor.names() == ["A", "B"] and editor.list.currentItem().text() == "A"
    tabs = _tab_names(editor)
    assert "Geometry" in tabs and "Mesh" in tabs and tabs[-1] == "Advanced"
    assert editor.field_widget("x_max").value() == 1.0
    assert editor.field_widget("cell_count").value() == (10, 10, 10)
    assert "cell size" in editor.info.text() and "alignment test: Passed" in editor.info.text()


def test_start_on_a_named_object(api):
    ed = EntityCollectionEditor(api, "meshes", "Edit Meshes", select="B")
    assert ed.list.currentItem().text() == "B" and ed.field_widget("x_min").value() == 1.0
    ed.close()


def test_editing_updates_the_preview_and_highlights_the_change(editor):
    assert editor.preview_text().startswith("&MESH") and not editor.is_dirty()
    editor.field_widget("cell_count").widget.findChildren(type(editor.field_widget("name").widget))[0].setText("20")
    assert editor.is_dirty()
    assert "IJK=20,10,10" in editor.preview_text().replace(" ", "")
    marked = [editor.preview_text()[s.cursor.selectionStart():s.cursor.selectionEnd()]
              for s in editor.preview.extraSelections()]
    assert any("IJK" in m for m in marked)


def test_apply_is_one_undo_step(editor, api):
    editor.field_widget("x_max").set_value(3.0)
    editor.field_widget("cylindrical").set_value(True)
    changed = editor.apply()
    assert changed == {"x_max": 3.0, "cylindrical": True}
    mesh = api.meshes.get("A")
    assert mesh.x_max == 3.0 and mesh.cylindrical
    assert not editor.is_dirty()
    api.history.undo()
    assert mesh.x_max == 1.0 and not mesh.cylindrical


def test_switching_objects_applies_pending_edits(editor, api):
    editor.field_widget("x_max").set_value(1.5)
    editor.select("B")
    assert api.meshes.get("A").x_max == 1.5 and editor.list.currentItem().text() == "B"
    assert editor.field_widget("name").value() == "B"


def test_invalid_pending_edit_keeps_you_on_the_object(editor, api):
    editor.field_widget("x_max").set_value(None)          # a required number left blank
    editor.select("B")
    assert editor.list.currentItem().text() == "A" and api.meshes.get("A").x_max == 1.0
    with pytest.raises(ValueError, match="needs a value"):
        editor.apply()


def test_rename_through_the_form_updates_the_list(editor, api):
    editor.field_widget("name").set_value("Renamed")
    editor.apply()
    assert editor.names() == ["Renamed", "B"] and editor.list.currentItem().text() == "Renamed"


def test_new_clone_rename_delete_buttons(editor, api, monkeypatch):
    new = editor.new_object()
    assert new.name == "Mesh" and "Mesh" in editor.names() and editor.list.currentItem().text() == "Mesh"
    clone = editor.clone_object()
    assert clone.name == "Mesh_copy"
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Fine", True))
    editor.rename_object()
    assert "Fine" in editor.names()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    editor.delete_object()
    assert "Fine" in editor.names()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    editor.delete_object()
    assert "Fine" not in editor.names() and api.meshes.get("Fine") is None


def test_advanced_tab_edits_raw_fds_keywords(editor, api):
    editor._add_extra_row("periodic_x", ".TRUE.")
    editor.apply()
    assert api.meshes.get("A").fds_extra == {"PERIODIC_X": ".TRUE."}
    assert "PERIODIC_X" in editor.preview_text()
    editor.extras_table.selectRow(0)
    editor._remove_extra_rows()
    editor.apply()
    assert not api.meshes.get("A").fds_extra


def test_units_follow_the_project(api):
    api.units.set_system("EN")
    ed = EntityCollectionEditor(api, "meshes", "Edit Meshes")
    form = ed.tabs.widget(_tab_names(ed).index("Geometry")).layout()
    labels = [form.itemAt(i, QFormLayout.LabelRole).widget().text() for i in range(form.rowCount())]
    assert any(l.endswith("(ft)") for l in labels)
    assert ed.field_widget("x_max").value() == pytest.approx(3.28084, rel=1e-4)
    ed.field_widget("x_max").set_value(6.56168)            # typed in feet
    ed.apply()
    assert api.meshes.get("A").x_max == pytest.approx(2.0, rel=1e-4)
    ed.close()


def test_library_button_adds_from_the_library(api, monkeypatch):
    ed = EntityCollectionEditor(api, "materials", "Edit Materials")
    assert not ed.library_button.isHidden() and ed.names() == []
    first = api.library.names("materials")[0]
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: (first, True))
    entity = ed.add_from_library()
    assert entity is not None and ed.names() == [entity.name]
    ed.close()
    mesh_ed = EntityCollectionEditor(api, "meshes", "Edit Meshes")
    assert mesh_ed.library_button.isHidden()
    mesh_ed.close()


def test_empty_collection_and_reference_fields(api):
    ed = EntityCollectionEditor(api, "surfaces", "Edit Surfaces")
    assert ed.names() == [] and ed.tabs.count() == 0
    s = ed.new_object()
    assert ed.names() == [s.name] and ed.tabs.count() > 0
    assert "surface type" in ed.info.text() and "Layers" not in _tab_names(ed)      # a blank surface is 'basic'
    ed._on_type_chosen(ed.type_combo.findData("layered"))
    assert "Layers" in _tab_names(ed)
    ed.close()
    ob = EntityCollectionEditor(api, "obstructions", "Edit Obstructions")
    ob.new_object()
    assert "surface_id" in ob._widgets
    ob.close()


def test_changed_tokens():
    assert changed_tokens("&MESH ID='A', IJK=10,10,10, XB=0,1,0,1,0,1 /", "&MESH ID='A', IJK=20,10,10, XB=0,1,0,1,0,1 /") \
        == ["IJK=20,10,10"]


# -- wiring in the main window ---------------------------------------------------------------------------
def test_model_menu_has_the_edit_entries_and_opens_the_dialog(monkeypatch):
    from pyfds.gui.main_window import MainWindow
    opened = []
    monkeypatch.setattr(EntityCollectionEditor, "exec", lambda self: opened.append((self.attr, self.windowTitle())) or 0)
    w = MainWindow(FdsApi())
    model = next(a.menu() for a in w.menuBar().actions() if a.text() == "&Model")
    labels = [a.text().replace("&", "") for a in model.actions()[:9]]
    assert labels[:3] == ["Edit Meshes...", "Edit Zones...", "Edit Species..."]
    w.action_registry.action("model.edit.materials").trigger()
    assert opened == [("materials", "Edit Materials")]
    mesh = w.api.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M")
    w.explorer.select_entity("meshes", mesh)
    ctx = [a.text().replace("&", "") for a in w._build_entity_context_menu("meshes", mesh).actions()]
    assert "Open in Editor..." in ctx
    w._on_open_in_editor("meshes", mesh)
    assert opened[-1] == ("meshes", "Edit Meshes") and w._collection_editor.list.currentItem().text() == "M"
    w.close()


# -- tables of sub-objects: surface layers, pyrolysis reactions ------------------------------------------------
def test_surface_layers_are_edited_in_a_table(api):
    api.materials.create_default("STEEL")
    api.materials.create_default("WOOL")
    ed = EntityCollectionEditor(api, "surfaces", "Edit Surfaces")
    s = ed.new_object()
    ed._on_type_chosen(ed.type_combo.findData("layered"))
    assert "Layers" in _tab_names(ed) and "not editable" not in ed.info.text()
    fw = ed.field_widget("layers")
    fw.add_row({"material_id": "STEEL", "thickness": 0.01})
    fw.add_row({"material_id": "WOOL", "thickness": 0.05})
    assert fw.value() == [{"material_id": "STEEL", "thickness": 0.01}, {"material_id": "WOOL", "thickness": 0.05}]
    assert "MATL_ID" in ed.preview_text() and "THICKNESS" in ed.preview_text()
    changed = ed.apply()
    assert "layers" in changed and [(l.material_id, l.thickness) for l in s.layers] == [("STEEL", 0.01), ("WOOL", 0.05)]
    fw = ed.field_widget("layers")
    fw.table.cellWidget(1, 0).setCurrentText("STEEL")
    ed.apply()
    assert [l.material_id for l in s.layers] == ["STEEL", "STEEL"]
    api.history.undo()
    assert [l.material_id for l in s.layers] == ["STEEL", "WOOL"]
    ed.close()


def test_blank_required_cell_is_refused_not_stored(api, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    api.materials.create_default("STEEL")
    ed = EntityCollectionEditor(api, "surfaces", "Edit Surfaces")
    s = ed.new_object()
    ed._on_type_chosen(ed.type_combo.findData("layered"))
    ed.field_widget("layers").add_row({"material_id": "STEEL"})        # no thickness
    with pytest.raises(ValueError, match="Layers"):
        ed.apply()
    assert s.layers == []
    ed.close()


def test_pyrolysis_reactions_keep_their_list_columns(api):
    ed = EntityCollectionEditor(api, "materials", "Edit Materials")
    m = ed.new_object()
    fw = ed.field_widget("reactions")
    fw.add_row({"a": 1e10, "e": 1.5e5, "nu_spec": [0.3, 0.2]})
    ed.apply()
    r = m.reactions[0]
    assert (r.a, r.e, r.nu_spec) == (1e10, 1.5e5, [0.3, 0.2])
    assert ed.field_widget("reactions").value()[0]["nu_spec"] == [0.3, 0.2]
    ed.close()


def test_list_of_numbers_field(api):
    ed = EntityCollectionEditor(api, "inits", "Edit Init Regions")
    i = ed.new_object()
    ed.field_widget("mass_fractions").widget.setText("0.2, 0.8")
    ed.apply()
    assert i.mass_fractions == [0.2, 0.8]
    ed.close()
