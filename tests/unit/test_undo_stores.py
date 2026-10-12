"""Scenarios, floors and groups are undoable (one history entry per user action)."""
import pytest

from pyfds.api import FdsApi


@pytest.fixture
def api():
    a = FdsApi()
    a.new("t")
    return a


def _steps(api):
    return len(api.history.history())


# ── scenarios ────────────────────────────────────────────────────────────────

def test_scenario_create_undo_redo(api):
    api.scenarios.create("a", "desc")
    assert [s.name for s in api.scenarios.all()] == ["a"]
    api.history.undo()
    assert api.scenarios.all() == []
    api.history.redo()
    assert [s.name for s in api.scenarios.all()] == ["a"]


def test_scenario_duplicate_raises_and_records_nothing(api):
    api.scenarios.create("a")
    before = _steps(api)
    with pytest.raises(ValueError):
        api.scenarios.create("a")
    assert _steps(api) == before
    assert len(api.scenarios.all()) == 1


def test_scenario_apply_and_reset_restore_entity_values(api):
    api.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1), name="m")
    mesh = api.meshes.get("m")
    api.scenarios.create("s")
    api.scenarios.set_override("s", mesh, "x_max", 5.0)
    api.scenarios.apply("s")
    assert mesh.x_max == 5.0 and api.scenarios.active == "s"
    api.history.undo()                       # undo apply
    assert mesh.x_max == 1.0 and api.scenarios.active is None
    api.history.redo()
    assert mesh.x_max == 5.0 and api.scenarios.active == "s"
    api.scenarios.reset()
    assert mesh.x_max == 1.0
    api.history.undo()                       # undo reset -> scenario active again
    assert mesh.x_max == 5.0 and api.scenarios.active == "s"


def test_scenario_remove_alias_is_single_step(api):
    api.scenarios.create("a")
    before = _steps(api)
    scen = api.scenarios.get("a")
    api.scenarios.remove(scen)
    assert _steps(api) == before + 1
    api.history.undo()
    assert api.scenarios.get("a") is not None


def test_export_all_adds_no_history(api, tmp_path):
    api.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1), name="m")
    api.scenarios.create("a")
    before = _steps(api)
    api.scenarios.export_all(str(tmp_path))
    assert _steps(api) == before
    assert api.scenarios.active is None


# ── floors ───────────────────────────────────────────────────────────────────

def test_floor_define_assign_delete_undo(api):
    api.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1), name="m")
    mesh = api.meshes.get("m")
    api.floors.define_floor("L1", 0, 3)
    api.floors.assign(mesh, "L1")
    assert api.floors.floor_of(mesh).name == "L1"
    api.floors.delete_floor("L1")
    assert api.floors.get_floor("L1") is None
    api.history.undo()                       # undo delete: floor AND assignment back
    assert api.floors.get_floor("L1") is not None
    assert api.floors.floor_of(mesh).name == "L1"
    api.history.undo()                       # undo assign
    api.history.undo()                       # undo define
    assert api.floors.get_floor("L1") is None


def test_floor_assign_unknown_raises_without_history(api):
    api.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1), name="m")
    before = _steps(api)
    with pytest.raises(KeyError):
        api.floors.assign(api.meshes.get("m"), "nope")
    assert _steps(api) == before


def test_floor_import_is_single_undo_step(api, tmp_path):
    api.floors.define_floor("A", 0, 3)
    path = tmp_path / "floors.json"
    api.floors.export_floors(str(path))
    api.floors.define_floor("B", 3, 6)
    before = _steps(api)
    api.floors.import_floors(str(path))
    assert _steps(api) == before + 1
    assert {f.name for f in api.floors.all_floors()} == {"A"}
    api.history.undo()
    assert {f.name for f in api.floors.all_floors()} == {"A", "B"}


# ── groups ───────────────────────────────────────────────────────────────────

def test_group_lifecycle_undo(api):
    api.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1), name="m")
    mesh = api.meshes.get("m")
    api.groups.create("g")
    api.groups.assign(mesh, "g")
    assert api.groups.group_of(mesh) == "g"
    api.groups.unassign(mesh)
    assert api.groups.group_of(mesh) is None
    api.history.undo()
    assert api.groups.group_of(mesh) == "g"
    api.groups.delete_group("g")
    assert api.groups.get("g") is None and api.groups.group_of(mesh) is None
    api.history.undo()
    assert api.groups.get("g") is not None and api.groups.group_of(mesh) == "g"


def test_group_remove_alias_is_single_step(api):
    api.groups.create("g")
    before = _steps(api)
    api.groups.remove(api.groups.get("g"))
    assert _steps(api) == before + 1


# ── ordering with ordinary model edits ───────────────────────────────────────

def test_mixed_model_and_store_edits_undo_in_order(api):
    api.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1), name="m")
    api.groups.create("g")
    assert _steps(api) == 2
    api.history.undo()
    assert api.groups.get("g") is None and api.meshes.get("m") is not None
    api.history.undo()
    assert api.meshes.get("m") is None
