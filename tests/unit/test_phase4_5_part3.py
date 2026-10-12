"""Unit tests — Phase 4 & 5: (part 3 of 3)."""


from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_obst(name="wall", x=(0, 1), y=(0, 4), z=(0, 3)):
    from pyfds.domain.model import Obstruction
    return Obstruction(
        name=name,
        x_min=x[0], x_max=x[1],
        y_min=y[0], y_max=y[1],
        z_min=z[0], z_max=z[1],
        surface_id="INERT",
    )


class TestGroupManager:

    def test_create(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        g = api.groups.create("Kitchen Block", "kitchen fixtures")
        assert g.name == "Kitchen Block"
        assert g.description == "kitchen fixtures"

    def test_all(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.groups.create("A")
        api.groups.create("B")
        assert {g.name for g in api.groups.all()} == {"A", "B"}

    def test_get(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.groups.create("A")
        assert api.groups.get("A") is not None
        assert api.groups.get("Missing") is None

    def test_assign_and_group_of(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = _make_obst()
        api.groups.create("A")
        api.groups.assign(obst, "A")
        assert api.groups.group_of(obst) == "A"

    def test_group_of_unassigned_is_none(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = _make_obst()
        assert api.groups.group_of(obst) is None

    def test_assign_unknown_group_raises(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = _make_obst()
        with pytest.raises(KeyError):
            api.groups.assign(obst, "NonExistent")

    def test_assign_replaces_prior_group(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = _make_obst()
        api.groups.create("A")
        api.groups.create("B")
        api.groups.assign(obst, "A")
        api.groups.assign(obst, "B")
        assert api.groups.group_of(obst) == "B"
        assert obst not in api.groups.members("A")

    def test_members(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        a = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
        b = api.obstructions.add_obstruction(xb=[2, 3, 0, 1, 0, 1], name="b")
        c = api.obstructions.add_obstruction(xb=[4, 5, 0, 1, 0, 1], name="c")
        api.groups.create("A")
        api.groups.assign(a, "A")
        api.groups.assign(b, "A")
        names = {m.name for m in api.groups.members("A")}
        assert names == {"a", "b"}
        assert c not in api.groups.members("A")

    def test_members_of_undefined_group_is_empty(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        assert api.groups.members("Nope") == []

    def test_unassign(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = _make_obst()
        api.groups.create("A")
        api.groups.assign(obst, "A")
        api.groups.unassign(obst)
        assert api.groups.group_of(obst) is None

    def test_unassign_never_assigned_is_a_noop(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = _make_obst()
        api.groups.unassign(obst)  # must not raise
        assert api.groups.group_of(obst) is None

    def test_delete_group_clears_memberships(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = _make_obst()
        api.groups.create("A")
        api.groups.assign(obst, "A")
        api.groups.delete_group("A")
        assert api.groups.get("A") is None
        assert api.groups.group_of(obst) is None

    def test_remove_alias_deletes_by_entity_name(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        g = api.groups.create("A")
        api.groups.remove(g)
        assert api.groups.get("A") is None

    def test_membership_survives_rename(self):
        # Membership is keyed by uid, not name — confirmed important since
        # a plain-name key would desync on rename, same reasoning
        # FloorManager._assignments already relies on.
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="orig")
        api.groups.create("A")
        api.groups.assign(obst, "A")
        api.set_property(obst, "name", "renamed")
        assert api.groups.group_of(obst) == "A"
        assert [m.name for m in api.groups.members("A")] == ["renamed"]

    def test_repr(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.groups.create("A")
        assert "A" in repr(api.groups)

class TestResumeFromCheckpoint:

    def _write_simple_fds(self, path: str) -> None:
        content = (
            "&HEAD CHID='restart_test', TITLE='Test' /\n"
            "&TIME T_END=60.0 /\n"
            "&TAIL /\n"
        )
        Path(path).write_text(content, encoding="utf-8")

    def test_resume_writes_restart_file(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        with tempfile.TemporaryDirectory() as d:
            fds_path = str(Path(d) / "case.fds")
            self._write_simple_fds(fds_path)
            restart_path = str(Path(d) / "case_restart.fds")
            # Patch orchestrator so we don't need FDS binary
            with patch(
                "pyfds.automation.orchestrator.ScenarioOrchestrator.run",
                return_value=MagicMock(success=False),
            ):
                api.execution.resume_from_checkpoint(fds_path)
            assert Path(restart_path).exists()

    def test_resume_sets_restart_true(self):
        from pyfds.api.controller import FdsApi
        from pyfds.io.fds_parser import FdsParser
        api = FdsApi()
        with tempfile.TemporaryDirectory() as d:
            fds_path = str(Path(d) / "case.fds")
            self._write_simple_fds(fds_path)
            with patch(
                "pyfds.automation.orchestrator.ScenarioOrchestrator.run",
                return_value=MagicMock(success=False),
            ):
                api.execution.resume_from_checkpoint(fds_path)
            restart_path = str(Path(d) / "case_restart.fds")
            content = Path(restart_path).read_text()
            assert "RESTART" in content.upper()
