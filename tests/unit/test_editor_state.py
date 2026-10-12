"""Floors / groups / scenarios belong to the project: isolated per document and saved."""
from pyfds.api import FdsApi


def _mesh(api, name="m", x=1.0):
    return api.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, x, 0, 1, 0, 1), name=name)


def test_each_document_has_its_own_floors_groups_scenarios():
    api = FdsApi()
    api.session.new_project("a")
    api.floors.define_floor("L1", 0, 3)
    api.groups.create("g")
    api.scenarios.create("s")
    api.session.new_project("b")
    assert api.floors.all_floors() == []
    assert api.groups.all() == []
    assert api.scenarios.all() == []
    api.floors.define_floor("OTHER", 0, 1)
    api.session.switch_project("a")
    assert [f.name for f in api.floors.all_floors()] == ["L1"]
    assert api.groups.get("g") is not None and api.scenarios.get("s") is not None


def test_undo_in_one_document_does_not_touch_another():
    api = FdsApi()
    api.session.new_project("a")
    api.groups.create("ga")
    api.session.new_project("b")
    api.groups.create("gb")
    api.history.undo()
    assert api.groups.get("gb") is None
    api.session.switch_project("a")
    assert api.groups.get("ga") is not None


def test_new_project_starts_with_empty_editor_state():
    api = FdsApi()
    api.new("a")
    api.floors.define_floor("L1", 0, 3)
    api.new("b")
    assert api.floors.all_floors() == []


def test_editor_state_survives_save_and_load(tmp_path):
    api = FdsApi()
    api.new("a")
    m1 = _mesh(api, "m1")
    m2 = _mesh(api, "m2", x=2.0)
    api.floors.define_floor("L1", 0, 3, "ground")
    api.floors.assign(m1, "L1")
    api.groups.create("g", "my group")
    api.groups.assign(m2, "g")
    api.scenarios.create("hot", "peak")
    api.scenarios.set_override("hot", m1, "x_max", 7.0)
    path = tmp_path / "case.pyfds"
    api.save(str(path))

    api2 = FdsApi()
    api2.load(str(path))
    n1, n2 = api2.project.meshes
    assert api2.floors.get_floor("L1").description == "ground"
    assert api2.floors.floor_of(n1).name == "L1"
    assert api2.groups.get("g").description == "my group"
    assert api2.groups.group_of(n2) == "g" and api2.groups.group_of(n1) is None
    s = api2.scenarios.get("hot")
    assert s.description == "peak"
    api2.scenarios.apply("hot")
    assert n1.x_max == 7.0                      # override re-resolved to the NEW entity
    api2.scenarios.reset()
    assert n1.x_max == 1.0


def test_saving_a_project_without_editor_data_adds_no_editor_key():
    import json
    from pyfds.io.serializer import Serializer
    api = FdsApi()
    api.new("a")
    _mesh(api)
    assert "editor" not in json.loads(Serializer().save_string(api.project))


def test_old_archives_without_editor_key_still_load():
    import json
    from pyfds.io.serializer import Serializer
    api = FdsApi()
    api.new("a")
    _mesh(api)
    api.floors.define_floor("L1", 0, 3)
    data = json.loads(Serializer().save_string(api.project))
    assert "editor" in data
    data.pop("editor")
    project = Serializer().load_string(json.dumps(data))
    assert len(project.meshes) == 1 and project.editor.is_empty()
