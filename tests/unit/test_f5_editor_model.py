"""F5: the logic of the generic collection editor (no Qt)."""
import pytest

from pyfds.api import FdsApi
from pyfds.gui.editors.model import EntityEditorModel


@pytest.fixture
def api():
    return FdsApi()


def _model(api, attr):
    return EntityEditorModel(api, attr)


def test_fields_merge_schema_fields_and_the_rest_of_the_model(api):
    mesh = api.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M")
    specs = {s.name: s for s in _model(api, "meshes").fields(mesh)}
    assert specs["x_min"].kind == "float" and specs["x_min"].unit_kind == "length" and specs["x_min"].category == "Geometry"
    assert specs["cell_count"].kind == "vec" and specs["cell_count"].length == 3 and specs["cell_count"].int_vec
    assert specs["cylindrical"].kind == "bool" and specs["cylindrical"].advanced
    assert "priority" in specs and specs["priority"].category == "Other"      # not in the schema, found by introspection
    assert "tags" in specs and specs["tags"].kind == "list_str"
    assert "fds_extra" not in specs


def test_lists_of_sub_objects_become_row_tables(api):
    s = api.surfaces.create_default("S")
    m = _model(api, "surfaces")
    layers = next(f for f in m.fields(s) if f.name == "layers")
    assert layers.kind == "rows" and [c.name for c in layers.columns] == ["material_id", "thickness"]
    assert layers.columns[0].kind == "ref" and layers.columns[0].ref_collection == "materials"
    assert m.unsupported_fields(s) == []
    mat = api.materials.create_default("M")
    react = next(f for f in _model(api, "materials").fields(mat) if f.name == "reactions")
    assert "nu_spec" in [c.name for c in react.columns] and [c.kind for c in react.columns if c.name == "nu_spec"] == ["list_float"]


def test_rows_round_trip_through_apply_and_compare_equal(api):
    api.materials.create_default("STEEL")
    s = api.surfaces.create_default("S")
    m = _model(api, "surfaces")
    shown = m.current(s)
    shown["layers"] = [{"material_id": "STEEL", "thickness": 0.02}]
    assert m.apply(s, shown)["layers"][0].thickness == 0.02
    assert m.changes(s, m.current(s)) == {}
    shown = m.current(s)
    shown["layers"] = [{"material_id": "STEEL", "thickness": None}]
    with pytest.raises(ValueError, match="Layers"):
        m.apply(s, shown)
    assert s.layers[0].thickness == 0.02


def test_apply_is_one_undo_step_and_only_changes_what_differs(api):
    mesh = api.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M")
    m = _model(api, "meshes")
    shown = m.current(mesh)
    assert m.changes(mesh, shown) == {}                                      # nothing edited, nothing to do
    shown.update(x_max=2.0, cell_count=(20, 10, 10), cylindrical=True)
    assert m.apply(mesh, shown) == {"x_max": 2.0, "cell_count": (20, 10, 10), "cylindrical": True}
    assert (mesh.x_max, mesh.cell_count, mesh.cylindrical) == (2.0, (20, 10, 10), True)
    api.history.undo()
    assert (mesh.x_max, mesh.cell_count, mesh.cylindrical) == (1.0, (10, 10, 10), False)


def test_rename_through_apply_and_clash(api):
    api.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="A")
    b = api.meshes.add_mesh([10, 10, 10], [1, 2, 0, 1, 0, 1], name="B")
    m = _model(api, "meshes")
    shown = m.current(b)
    shown["name"] = "C"
    assert m.apply(b, shown)["name"] == "C" and b.name == "C"
    api.history.undo()
    assert b.name == "B"
    shown["name"] = "A"
    with pytest.raises(ValueError, match="exists"):
        m.apply(b, shown)
    assert b.name == "B"
    with pytest.raises(ValueError):
        m.rename(b, "  ")


def test_english_units_convert_in_both_directions(api):
    mesh = api.meshes.add_mesh([10, 10, 10], [0, 3.048, 0, 1, 0, 1], name="M")
    m = _model(api, "meshes")
    spec = next(s for s in m.fields(mesh) if s.name == "x_max")
    assert m.to_display(spec, mesh.x_max) == pytest.approx(3.048) and m.unit_label(spec) == "m"
    api.units.set_system("EN")
    assert m.to_display(spec, mesh.x_max) == pytest.approx(10.0) and m.unit_label(spec) == "ft"
    shown = m.current(mesh)
    shown["x_max"] = 20.0                                                      # typed in feet
    m.apply(mesh, shown)
    assert mesh.x_max == pytest.approx(6.096)
    assert m.changes(mesh, m.current(mesh)) == {}                              # round trip loses nothing


def test_optional_blank_values_and_types(api):
    mat = api.materials.create_default("MAT")
    m = _model(api, "materials")
    specs = {s.name: s for s in m.fields(mat)}
    assert any(s.optional for s in specs.values())
    opt_float = next(s for s in specs.values() if s.kind == "float" and s.optional)
    assert m.from_display(opt_float, None) is None
    assert m.from_display(specs["name"], "X") == "X"
    with pytest.raises(KeyError):
        m.changes(mat, {"no_such_field": 1})


def test_record_preview_shows_unsaved_edits_without_touching_the_object(api):
    mesh = api.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M")
    m = _model(api, "meshes")
    before = m.record(mesh)
    assert before.startswith("&MESH") and "IJK=10,10,10" in before.replace(" ", "")
    shown = m.current(mesh)
    shown["cell_count"] = (20, 10, 10)
    assert "IJK=20,10,10" in m.record(mesh, shown).replace(" ", "")
    assert mesh.cell_count == (10, 10, 10)


def test_new_clone_delete(api):
    m = _model(api, "surfaces")
    a = m.create()
    b = m.create("Wall")
    c = m.create("Wall")
    assert [s.name for s in (a, b, c)] == ["Surface", "Wall", "Wall_2"]
    api.surfaces.update(b, color="RED", tau_q=3.0)
    d = m.clone(b)
    assert d.name == "Wall_copy" and d.color == "RED" and d.tau_q == 3.0 and d is not b
    assert m.clone(b).name == "Wall_copy2"
    m.delete(d)
    assert m.get("Wall_copy") is None and m.get("Wall") is b
    api.history.undo()
    assert m.get("Wall_copy") is d


def test_extras_round_trip(api):
    mesh = api.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M")
    m = _model(api, "meshes")
    m.set_extra(mesh, "PERIODIC_X", ".TRUE.")
    assert m.extras(mesh) == {"PERIODIC_X": ".TRUE."}
    assert "PERIODIC_X" in m.record(mesh)
    m.remove_extra(mesh, "PERIODIC_X")
    assert m.extras(mesh) == {}


def test_library_and_info(api):
    m = _model(api, "materials")
    names = m.library_names()
    assert names
    added = m.add_from_library(names[0])
    assert added in api.materials.all()
    with pytest.raises(ValueError):
        _model(api, "meshes").add_from_library("x")
    assert _model(api, "meshes").library_names() == []
    mesh = api.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M")
    info = _model(api, "meshes").info(mesh)
    assert any(line.startswith("alignment test") for line in info)
    s = api.surfaces.create_default("S")
    assert any("surface type" in line for line in _model(api, "surfaces").info(s))


@pytest.mark.parametrize("attr", ["meshes", "surfaces", "materials", "reactions", "species", "zones", "particles",
                                  "ramps", "obstructions", "vents", "holes", "devices", "controls", "inits", "props"])
def test_every_collection_can_be_listed_described_edited_and_previewed(api, attr):
    m = _model(api, attr)
    e = m.create()
    specs = m.fields(e)
    assert specs and all(s.kind in ("float", "int", "str", "bool", "enum", "vec", "list_str", "list_float", "rows", "ref")
                         for s in specs)
    shown = m.current(e)
    assert m.changes(e, shown) == {}
    assert isinstance(m.record(e, shown), str)
