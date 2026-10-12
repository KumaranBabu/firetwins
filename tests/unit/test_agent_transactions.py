"""Agent tool calls are attributed to the agent, atomic, and undoable as one task."""
import pytest

from pyfds.agent.dispatcher import AgentToolDispatcher
from pyfds.api import FdsApi


@pytest.fixture
def disp():
    api = FdsApi()
    api.new("ag")
    return AgentToolDispatcher(api)


def mesh_args(name="m"):
    return {"ijk": [10, 10, 10], "xb": [0, 1, 0, 1, 0, 1], "name": name}


def test_single_mutating_call_is_agent_attributed_and_one_step(disp):
    disp.call("add_mesh", mesh_args())
    entries = disp.api.history.entries()
    assert len(entries) == 1
    assert entries[0]["actor"] == "agent" and entries[0]["label"] == "agent: add_mesh"
    disp.api.history.undo()
    assert disp.api.project.meshes == []


def test_read_only_tool_records_nothing(disp):
    disp.call("add_mesh", mesh_args())
    before = len(disp.api.history.entries())
    disp.call("list_history")
    assert len(disp.api.history.entries()) == before


def test_failing_tool_leaves_no_partial_change_or_history(disp):
    with pytest.raises(Exception):
        disp.call("add_obstruction", {"xb": [0, 1]})      # malformed
    assert disp.api.project.obstructions == []
    assert disp.api.history.entries() == []


def test_undo_and_redo_tools_still_work(disp):
    disp.call("add_mesh", mesh_args())
    disp.call("undo")
    assert disp.api.project.meshes == []
    disp.call("redo")
    assert len(disp.api.project.meshes) == 1


def test_plan_is_one_undo_step(disp):
    steps = [{"name": "add_mesh", "arguments": mesh_args("m1")}] + [
        {"name": "add_obstruction", "arguments": {"xb": [i, i + 1, 0, 1, 0, 1]}}
        for i in range(5)
    ]
    results = disp.run_plan(steps, label="agent: build room")
    assert len(results) == 6
    assert len(disp.api.project.obstructions) == 5 and len(disp.api.project.meshes) == 1
    assert disp.api.history.entries() == [{"label": "agent: build room", "actor": "agent"}]
    disp.api.history.undo()
    assert disp.api.project.obstructions == [] and disp.api.project.meshes == []
    disp.api.history.redo()
    assert len(disp.api.project.obstructions) == 5


def test_plan_failure_rolls_back_every_step(disp):
    steps = [
        {"name": "add_mesh", "arguments": mesh_args()},
        {"name": "create_scenario", "arguments": {"name": "s"}},
        {"name": "add_obstruction", "arguments": {"xb": [0, 1]}},   # fails
    ]
    with pytest.raises(Exception):
        disp.run_plan(steps)
    assert disp.api.project.meshes == [] and disp.api.scenarios.all() == []
    assert disp.api.history.entries() == []


def test_plan_rejects_unknown_or_history_tools_before_running_anything(disp):
    with pytest.raises(Exception):
        disp.run_plan([{"name": "add_mesh", "arguments": mesh_args()},
                       {"name": "undo", "arguments": {}}])
    assert disp.api.project.meshes == []


def test_approver_can_block_mutations_but_not_reads(disp):
    d = AgentToolDispatcher(disp.api, approver=lambda names, args: False)
    with pytest.raises(PermissionError):
        d.call("add_mesh", mesh_args())
    with pytest.raises(PermissionError):
        d.run_plan([{"name": "add_mesh", "arguments": mesh_args()}])
    assert disp.api.project.meshes == []
    d.call("list_history")                                      # reads are not gated


def test_approver_sees_tool_names(disp):
    seen = []
    d = AgentToolDispatcher(disp.api, approver=lambda names, args: seen.append(list(names)) or True)
    d.run_plan([{"name": "add_mesh", "arguments": mesh_args()},
                {"name": "list_history", "arguments": {}}])
    assert seen == [["add_mesh"]]
