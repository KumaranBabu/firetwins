"""F5: activation-control relationships on api.controls."""
import pytest

from pyfds.api import FdsApi


@pytest.fixture
def api():
    a = FdsApi()
    a.devices.add_device("TEMPERATURE", [1, 1, 1], name="TC1")
    a.devices.add_device("TEMPERATURE", [2, 1, 1], name="TC2")
    return a


def test_inputs_candidates_exclude_self_and_loops(api):
    a = api.controls.add_control("ANY", ["TC1"], name="A")
    b = api.controls.add_control("ALL", ["TC1", "A"], name="B")
    assert sorted(api.controls.input_candidates("A")) == ["TC1", "TC2"]        # B depends on A, so A cannot use B
    assert sorted(api.controls.input_candidates("B")) == ["A", "TC1", "TC2"]
    with pytest.raises(ValueError, match="loop"):
        api.controls.set_inputs("A", ["B"])
    with pytest.raises(ValueError):
        api.controls.set_inputs("A", ["NOPE"])
    api.controls.set_inputs("B", ["TC2", "TC2", "A"])                          # duplicates collapse
    assert b.input_ids == ["TC2", "A"] and b.input_id is None
    api.history.undo()
    assert b.input_ids == ["TC1", "A"]
    assert api.controls.used_as_input("A") == [b] and api.controls.used_as_input("B") == []


def test_assign_unassign_and_listing(api):
    c = api.controls.add_control("ANY", ["TC1"], name="C")
    o = api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1])
    v = api.vents.add_vent([0, 1, 0, 1, 0, 0])
    mesh = api.meshes.add_mesh([5, 5, 5], [0, 1, 0, 1, 0, 1])
    api.controls.assign(c, o)
    api.controls.assign("C", v)
    assert sorted(k for k, _e in api.controls.controlled(c)) == ["Obstruction", "Vent"]
    assert (type(o).__name__, o) in api.controls.assignable() and all(e is not c for _k, e in api.controls.assignable())
    api.controls.unassign(o)
    assert o.ctrl_id is None and len(api.controls.controlled(c)) == 1
    with pytest.raises(ValueError):
        api.controls.unassign(o)
    with pytest.raises(ValueError):
        api.controls.assign(c, mesh)                                            # meshes have no CTRL_ID
    api.history.undo()
    assert o.ctrl_id == "C"


def test_rename_follows_every_reference_in_one_undo_step(api):
    a = api.controls.add_control("ANY", ["TC1"], name="A")
    b = api.controls.add_control("ALL", ["TC1", "A"], name="B")
    o = api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1])
    api.controls.assign(a, o)
    api.controls.rename("A", "ALARM")
    assert a.name == "ALARM" and o.ctrl_id == "ALARM" and b.input_ids == ["TC1", "ALARM"]
    api.history.undo()
    assert a.name == "A" and o.ctrl_id == "A" and b.input_ids == ["TC1", "A"]
    with pytest.raises(ValueError):
        api.controls.rename("A", "B")
    with pytest.raises(ValueError):
        api.controls.rename("A", "TC1")                                        # a device already has that name
    with pytest.raises(ValueError):
        api.controls.rename("A", " ")


def test_problems_reports_what_is_missing(api):
    api.controls.add_control("ANY", ["TC1"], name="OK")
    c = api.controls.add_control("ANY", ["TC1"], name="NEEDS")
    api.controls.update(c, function_type="TIME_DELAY", input_ids=None)
    assert api.controls.problems("OK") == []
    assert any("INPUT_ID" in p for p in api.controls.problems("NEEDS"))
