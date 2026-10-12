"""Unit tests — pyfds.core.state (StateSnapshot, StateManager, build_snapshot)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from pyfds.core.state import StateSnapshot, StateManager, build_snapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_project(**overrides):
    p = MagicMock()
    p._project_id = "proj-001"
    p.chid = "test_case"
    p.title = "Test Fire"
    p.params.t_begin = 0.0
    p.params.t_end = 60.0
    p.meshes = []
    p.obstructions = []
    p.surfaces = []
    p.vents = []
    p.devices = []
    p.materials = []
    p.reactions = []
    p.slices = []
    p.bndfs = []
    p.isofs = []
    p.hvac_nodes = []
    p.hvac_ducts = []
    for k, v in overrides.items():
        setattr(p, k, v)
    return p


def _make_snapshot(**kwargs) -> StateSnapshot:
    defaults = dict(
        timestamp=1.0,
        project_id="proj-001",
        chid="test",
        title="Test",
        filepath=None,
        is_dirty=False,
        t_end=60.0,
        t_begin=0.0,
        mesh_count=1,
        obstruction_count=0,
        surface_count=0,
        vent_count=0,
        device_count=0,
        material_count=0,
        reaction_count=0,
        slice_count=0,
        boundary_count=0,
        isosurface_count=0,
        hvac_node_count=0,
        hvac_duct_count=0,
        validation_errors=[],
        extra={},
    )
    defaults.update(kwargs)
    return StateSnapshot(**defaults)


# ---------------------------------------------------------------------------
# StateSnapshot
# ---------------------------------------------------------------------------

class TestStateSnapshot:
    def test_frozen_dataclass(self):
        snap = _make_snapshot()
        with pytest.raises((AttributeError, TypeError)):
            snap.chid = "modified"  # type: ignore[misc]

    def test_to_dict_keys(self):
        snap = _make_snapshot(chid="hotel", mesh_count=4)
        d = snap.to_dict()
        assert d["chid"] == "hotel"
        assert d["entity_counts"]["meshes"] == 4

    def test_to_dict_simulation_block(self):
        snap = _make_snapshot(t_begin=5.0, t_end=300.0)
        d = snap.to_dict()
        assert d["simulation"]["t_begin"] == 5.0
        assert d["simulation"]["t_end"] == 300.0

    def test_to_dict_validation_errors(self):
        snap = _make_snapshot(validation_errors=["err1", "err2"])
        d = snap.to_dict()
        assert d["validation_errors"] == ["err1", "err2"]

    def test_to_dict_extra_deep_copy(self):
        extra = {"foo": [1, 2]}
        snap = _make_snapshot(extra=extra)
        d = snap.to_dict()
        d["extra"]["foo"].append(3)
        assert extra["foo"] == [1, 2]

    def test_filepath_in_dict(self):
        snap = _make_snapshot(filepath="/path/to/case.fds")
        assert snap.to_dict()["filepath"] == "/path/to/case.fds"


# ---------------------------------------------------------------------------
# build_snapshot
# ---------------------------------------------------------------------------

class TestBuildSnapshot:
    def test_builds_from_project(self):
        p = _mock_project()
        snap = build_snapshot(p)
        assert snap.chid == "test_case"
        assert snap.project_id == "proj-001"
        assert snap.t_end == 60.0

    def test_mesh_count_from_list(self):
        p = _mock_project(meshes=[MagicMock(), MagicMock()])
        snap = build_snapshot(p)
        assert snap.mesh_count == 2

    def test_filepath_passed_through(self):
        p = _mock_project()
        snap = build_snapshot(p, filepath="/a/b/c.fds")
        assert snap.filepath == "/a/b/c.fds"

    def test_is_dirty_passed_through(self):
        p = _mock_project()
        snap = build_snapshot(p, is_dirty=True)
        assert snap.is_dirty is True

    def test_validation_errors_default_empty(self):
        p = _mock_project()
        snap = build_snapshot(p)
        assert snap.validation_errors == []

    def test_validation_errors_passed(self):
        p = _mock_project()
        snap = build_snapshot(p, validation_errors=["missing mesh"])
        assert "missing mesh" in snap.validation_errors

    def test_extra_passed_through(self):
        p = _mock_project()
        snap = build_snapshot(p, extra={"run_id": "abc"})
        assert snap.extra["run_id"] == "abc"

    def test_timestamp_is_positive_float(self):
        p = _mock_project()
        snap = build_snapshot(p)
        assert snap.timestamp > 0.0


# ---------------------------------------------------------------------------
# StateManager
# ---------------------------------------------------------------------------

class TestStateManager:
    def test_initial_current_is_none(self):
        mgr = StateManager()
        assert mgr.current is None

    def test_update_sets_current(self):
        mgr = StateManager()
        snap = _make_snapshot()
        mgr.update(snap)
        assert mgr.current is snap

    def test_listener_called_on_update(self):
        mgr = StateManager()
        received = []
        mgr.on_change(received.append)
        snap = _make_snapshot()
        mgr.update(snap)
        assert received == [snap]

    def test_multiple_listeners(self):
        mgr = StateManager()
        calls_a, calls_b = [], []
        mgr.on_change(calls_a.append)
        mgr.on_change(calls_b.append)
        mgr.update(_make_snapshot())
        assert len(calls_a) == 1
        assert len(calls_b) == 1

    def test_remove_listener_stops_notifications(self):
        mgr = StateManager()
        calls = []
        mgr.on_change(calls.append)
        mgr.remove_listener(calls.append)
        mgr.update(_make_snapshot())
        assert calls == []

    def test_remove_nonexistent_listener_no_error(self):
        mgr = StateManager()
        mgr.remove_listener(lambda s: None)

    def test_history_newest_first(self):
        mgr = StateManager()
        s1 = _make_snapshot(timestamp=1.0)
        s2 = _make_snapshot(timestamp=2.0)
        mgr.update(s1)
        mgr.update(s2)
        hist = mgr.history(limit=10)
        assert hist[0] is s2
        assert hist[1] is s1

    def test_history_limit_respected(self):
        mgr = StateManager()
        for i in range(5):
            mgr.update(_make_snapshot(timestamp=float(i)))
        assert len(mgr.history(limit=3)) == 3

    def test_history_max_100_entries(self):
        mgr = StateManager()
        for i in range(110):
            mgr.update(_make_snapshot(timestamp=float(i)))
        assert len(mgr._history) == 100

    def test_clear_resets_state(self):
        mgr = StateManager()
        mgr.update(_make_snapshot())
        mgr.clear()
        assert mgr.current is None
        assert mgr.history() == []

    def test_faulty_listener_does_not_propagate(self):
        mgr = StateManager()
        def bad_listener(s):
            raise RuntimeError("oops")
        mgr.on_change(bad_listener)
        mgr.update(_make_snapshot())
