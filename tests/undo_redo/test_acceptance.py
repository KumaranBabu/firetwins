"""Undo/redo acceptance suite.

Each test maps to a foundation-reliability criterion (see
docs/active_docs/PYROSIM_IMPLEMENTATION_PLAN.md / the architecture review): identity-preserving
undo/redo, dependency restoration, atomic compound actions, redo-branch
clearing, AI/agent grouped transactions, plugin-failure isolation, and
save/reopen.

Not covered here (needs a real FDS install / a GUI event loop): "solver
execution does not block the GUI thread" and "cancelling a job does not
corrupt the project".
"""
import pytest

from pyfds.api import FdsApi
from pyfds.automation.commands import (
    AddEntityCommand,
    CommandResult,
    Command,
    GroupCommand,
    ModifyPropertyCommand,
)


@pytest.fixture
def api():
    a = FdsApi()
    a.new("acc")
    return a


def box(api, i=0, **kw):
    return api.obstructions.add_obstruction(xb=[i, i + 1, 0, 1, 0, 1], **kw)


def steps(api):
    return len(api.history.history())


# ── 1. identity ──────────────────────────────────────────────────────────────

def test_create_undo_redo_keeps_object_identity_and_state(api):
    obst = box(api)
    snapshot = obst.model_dump()
    api.history.undo()
    assert obst not in api.project.obstructions
    api.history.redo()
    assert api.project.obstructions == [obst]
    assert api.project.obstructions[0] is obst
    assert obst.model_dump() == snapshot


# ── 2. property edit restores everything ─────────────────────────────────────

def test_edit_material_undo_restores_all_properties(api):
    from pyfds.domain.material_presets import list_material_presets
    mat = api.materials.add_from_library(list_material_presets()[0])
    before = mat.model_dump()
    with api.transaction("edit material"):
        api.set_property(mat, "density", 9999.0)
        api.set_property(mat, "conductivity", 42.0)
        api.set_property(mat, "emissivity", 0.123)
    assert mat.density == 9999.0
    api.history.undo()
    assert mat.model_dump() == before
    api.history.redo()
    assert (mat.density, mat.conductivity, mat.emissivity) == (9999.0, 42.0, 0.123)


# ── 3. delete a referenced object, undo restores the graph ───────────────────

def test_delete_referenced_surface_undo_restores_reference(api):
    surf = api.surfaces.add_burner(hrrpua=500.0)
    obst = box(api, surf_id=surf.name)
    assert obst.surface_id == surf.name
    api.surfaces.remove(surf)
    assert surf not in api.project.surfaces
    api.history.undo()
    assert surf in api.project.surfaces
    assert obst.surface_id == surf.name


def test_delete_group_undo_restores_memberships(api):
    o = box(api)
    api.groups.create("g")
    api.groups.assign(o, "g")
    api.groups.delete_group("g")
    assert api.groups.group_of(o) is None
    api.history.undo()
    assert api.groups.group_of(o) == "g"


# ── 4. atomicity ─────────────────────────────────────────────────────────────

class _Boom(Command):
    description = "boom"

    def execute(self):
        return CommandResult.fail("kaput")

    def undo(self):
        return CommandResult.ok("n/a")


def test_group_command_failing_midway_leaves_no_partial_change(api):
    from pyfds.domain.model import Obstruction
    ok = Obstruction(x_min=0, x_max=1, y_min=0, y_max=1, z_min=0, z_max=1)
    result = api.history.execute(GroupCommand([AddEntityCommand(api.project, ok), _Boom()], "mixed"))
    assert not result.success
    assert api.project.obstructions == []
    assert steps(api) == 0


def test_transaction_exception_rolls_back_everything(api):
    with pytest.raises(RuntimeError):
        with api.transaction("import 5 objects"):
            for i in range(3):
                box(api, i)
            raise RuntimeError("importer crashed")
    assert api.project.obstructions == []
    assert steps(api) == 0
    assert not api.history.can_redo()


def test_transaction_rolls_back_store_changes_too(api):
    with pytest.raises(RuntimeError):
        with api.transaction("x"):
            api.groups.create("g")
            api.floors.define_floor("L1", 0, 3)
            raise RuntimeError("boom")
    assert api.groups.get("g") is None and api.floors.get_floor("L1") is None


# ── 5. redo branch ───────────────────────────────────────────────────────────

def test_new_command_after_undo_clears_redo(api):
    box(api, 0)
    api.history.undo()
    assert api.history.can_redo()
    box(api, 5)
    assert not api.history.can_redo()


def test_failed_command_does_not_clear_redo(api):
    box(api, 0)
    api.history.undo()
    assert not api.history.execute(_Boom()).success
    assert api.history.can_redo()


# ── 6. cancelled interaction records nothing ─────────────────────────────────

def test_cancelled_interaction_leaves_no_history(api):
    with pytest.raises(KeyboardInterrupt):
        with api.transaction("draw wall"):
            box(api, 0)
            raise KeyboardInterrupt        # user pressed Esc
    assert steps(api) == 0 and api.project.obstructions == []


# ── 7. AI agent: many objects, one approved task, one undo ───────────────────

def test_agent_creates_20_objects_as_one_undoable_task(api):
    with api.transaction("agent: build compartment", actor="agent"):
        for i in range(20):
            box(api, i)
    assert len(api.project.obstructions) == 20
    assert steps(api) == 1
    assert api.history.entries()[0]["actor"] == "agent"
    api.history.undo()
    assert api.project.obstructions == []
    api.history.redo()
    assert len(api.project.obstructions) == 20


def test_actor_is_recorded_per_command(api):
    box(api, 0)
    with api.history.actor("plugin:demo"):
        box(api, 1)
    assert [e["actor"] for e in api.history.entries()] == ["user", "plugin:demo"]


# ── 8. plugin failure ────────────────────────────────────────────────────────

def test_plugin_failure_does_not_corrupt_project_or_history(api):
    box(api, 0)
    before = [o.model_dump() for o in api.project.obstructions]
    history_before = api.history.history()

    def bad_plugin():
        with api.transaction("plugin work", actor="plugin:bad"):
            box(api, 10)
            api.groups.create("tmp")
            raise ValueError("plugin bug")

    with pytest.raises(ValueError):
        bad_plugin()
    assert [o.model_dump() for o in api.project.obstructions] == before
    assert api.history.history() == history_before
    assert api.groups.get("tmp") is None
    box(api, 3)                      # still fully usable afterwards
    assert steps(api) == len(history_before) + 1


# ── 9. persistence ───────────────────────────────────────────────────────────

def test_save_and_reopen_preserves_project_but_not_history(api, tmp_path):
    box(api, 0)
    box(api, 1)
    path = tmp_path / "case.pyfds"
    api.save(str(path))
    api2 = FdsApi()
    api2.load(str(path))
    assert len(api2.project.obstructions) == 2
    assert not api2.history.can_undo()           # history is not persisted


# ── transactions: nesting, undo guard ────────────────────────────────────────

def test_nested_transactions_join_the_outer_step(api):
    with api.transaction("outer"):
        box(api, 0)
        with api.transaction("inner"):
            box(api, 1)
    assert steps(api) == 1
    assert api.history.history() == ["outer"]
    api.history.undo()
    assert api.project.obstructions == []


def test_inner_failure_rolls_back_the_whole_outer_transaction(api):
    with pytest.raises(ValueError):
        with api.transaction("outer"):
            box(api, 0)
            with api.transaction("inner"):
                box(api, 1)
                raise ValueError("inner")
    assert api.project.obstructions == [] and steps(api) == 0


def test_undo_is_refused_inside_a_transaction(api):
    box(api, 0)
    with api.transaction("t"):
        with pytest.raises(RuntimeError):
            api.history.undo()
        box(api, 1)
    assert len(api.project.obstructions) == 2


def test_empty_transaction_records_nothing(api):
    with api.transaction("nothing"):
        pass
    assert steps(api) == 0


# ── coalescing ───────────────────────────────────────────────────────────────

def test_coalesced_edits_are_one_undo_step(api):
    o = box(api)
    api.history.clear()
    for v in (2.0, 3.0, 4.0, 5.0):
        api.set_property(o, "x_max", v, coalesce=True)
    assert o.x_max == 5.0 and steps(api) == 1
    api.history.undo()
    assert o.x_max == 1.0
    api.history.redo()
    assert o.x_max == 5.0


def test_seal_ends_a_coalescing_run(api):
    o = box(api)
    api.history.clear()
    api.set_property(o, "x_max", 2.0, coalesce=True)
    api.set_property(o, "x_max", 3.0, coalesce=True)
    api.history.seal()
    api.set_property(o, "x_max", 4.0, coalesce=True)
    assert steps(api) == 2
    api.history.undo()
    assert o.x_max == 3.0


def test_coalescing_does_not_merge_different_attributes_or_plain_edits(api):
    o = box(api)
    api.history.clear()
    api.set_property(o, "x_max", 2.0, coalesce=True)
    api.set_property(o, "y_max", 2.0, coalesce=True)     # different attr
    api.set_property(o, "y_max", 3.0)                    # not coalescing
    assert steps(api) == 3


def test_coalescing_is_opt_in(api):
    o = box(api)
    api.history.clear()
    api.set_property(o, "x_max", 2.0)
    api.set_property(o, "x_max", 3.0)
    assert steps(api) == 2


def test_modify_property_command_unchanged_semantics(api):
    o = box(api)
    api.history.execute(ModifyPropertyCommand(o, "x_max", 9.0))
    api.history.undo()
    assert o.x_max == 1.0
