"""
Unit tests — Phase 4 & 5:
  1. FdsEntity.enabled flag (model + writer)
  2. FdsEntity.tags + SelectionManager tag helpers
  3. FdsEntity.bbox()
  4. Scenarios system (ScenarioStore + ScenarioManager)
  5. MirrorCommand + RotateCommand
  6. FloorManager
  7. resume_from_checkpoint (smoke test — no FDS binary)
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_obst(name="wall", x=(0, 1), y=(0, 4), z=(0, 3)):
    from pyfds.domain.model import Obstruction
    return Obstruction(
        name=name,
        x_min=x[0], x_max=x[1],
        y_min=y[0], y_max=y[1],
        z_min=z[0], z_max=z[1],
        surface_id="INERT",
    )


def _make_project():
    from pyfds.domain.model import FdsProject, Mesh
    p = FdsProject()
    p.chid = "test_case"
    p.add_entity(Mesh(
        name="m1", cell_count=(10, 10, 5),
        x_min=0, x_max=4, y_min=0, y_max=4, z_min=0, z_max=2
    ))
    p.add_entity(_make_obst())
    return p


# ===========================================================================
# 1. FdsEntity.enabled
# ===========================================================================

class TestEntityEnabled:

    def test_enabled_defaults_true(self):
        obst = _make_obst()
        assert obst.enabled is True

    def test_set_enabled_false(self):
        obst = _make_obst()
        obst.enabled = False
        assert obst.enabled is False

    def test_disabled_entity_not_written(self):
        from pyfds.domain.model import FdsProject, Obstruction
        from pyfds.io.fds_writer import FdsWriter
        p = FdsProject()
        p.chid = "test_disabled"
        obst = _make_obst("fire_wall")
        obst.enabled = False
        p.add_entity(obst)
        content = FdsWriter().generate_content(p)
        assert "fire_wall" not in content

    def test_enabled_entity_is_written(self):
        from pyfds.domain.model import FdsProject
        from pyfds.io.fds_writer import FdsWriter
        p = FdsProject()
        p.chid = "test_enabled"
        obst = _make_obst("active_wall")
        p.add_entity(obst)
        content = FdsWriter().generate_content(p)
        assert "active_wall" in content

    def test_disabled_ramp_not_written(self):
        from pyfds.domain.model import FdsProject, Ramp
        from pyfds.io.fds_writer import FdsWriter
        p = FdsProject()
        p.chid = "ramp_test"
        ramp = Ramp(name="fire_ramp", times=[0.0, 30.0], values=[0.0, 1.0])
        ramp.enabled = False
        p.add_entity(ramp)
        content = FdsWriter().generate_content(p)
        assert "fire_ramp" not in content


# ===========================================================================
# 2. FdsEntity.tags + SelectionManager tag helpers
# ===========================================================================

class TestEntityTags:

    def test_tags_default_empty(self):
        obst = _make_obst()
        assert obst.tags == []

    def test_tags_settable(self):
        obst = _make_obst()
        obst.tags = ["fire_load", "review"]
        assert "fire_load" in obst.tags

    def test_tag_entity_static(self):
        from pyfds.core.selection import SelectionManager
        obst = _make_obst()
        SelectionManager.tag_entity(obst, "structural")
        assert "structural" in obst.tags

    def test_tag_entity_no_duplicate(self):
        from pyfds.core.selection import SelectionManager
        obst = _make_obst()
        SelectionManager.tag_entity(obst, "structural")
        SelectionManager.tag_entity(obst, "structural")
        assert obst.tags.count("structural") == 1

    def test_untag_entity(self):
        from pyfds.core.selection import SelectionManager
        obst = _make_obst()
        obst.tags = ["structural", "review"]
        SelectionManager.untag_entity(obst, "structural")
        assert "structural" not in obst.tags
        assert "review" in obst.tags

    def test_select_by_tag(self):
        from pyfds.core.selection import SelectionManager
        p = _make_project()
        # Tag the obstruction
        obst = p.obstructions[0]
        obst.tags = ["fire_load"]
        sm = SelectionManager(project=p)
        matches = sm.select_by_tag("fire_load")
        assert len(matches) == 1
        assert matches[0].name == "wall"

    def test_select_by_tag_no_match(self):
        from pyfds.core.selection import SelectionManager
        p = _make_project()
        sm = SelectionManager(project=p)
        matches = sm.select_by_tag("nonexistent_tag")
        assert matches == []

    def test_select_by_tag_updates_selection(self):
        from pyfds.core.selection import SelectionManager
        p = _make_project()
        obst = p.obstructions[0]
        obst.tags = ["tagged"]
        sm = SelectionManager(project=p)
        sm.select_by_tag("tagged")
        assert sm.count == 1

    def test_select_by_tag_no_project(self):
        from pyfds.core.selection import SelectionManager
        sm = SelectionManager(project=None)
        assert sm.select_by_tag("any") == []


# ===========================================================================
# 3. FdsEntity.bbox()
# ===========================================================================

class TestEntityBbox:

    def test_obst_bbox(self):
        obst = _make_obst(x=(1, 3), y=(0, 4), z=(0, 2))
        bb = obst.bbox()
        assert bb == (1.0, 3.0, 0.0, 4.0, 0.0, 2.0)

    def test_mesh_bbox(self):
        from pyfds.domain.model import Mesh
        m = Mesh(name="m", cell_count=(10, 10, 5),
                 x_min=0, x_max=4, y_min=0, y_max=4, z_min=0, z_max=2)
        bb = m.bbox()
        assert bb == (0.0, 4.0, 0.0, 4.0, 0.0, 2.0)

    def test_device_bbox_is_point(self):
        from pyfds.domain.model import Device
        d = Device(name="tc1", quantity="TEMPERATURE", xyz=(2.0, 2.0, 1.5))
        bb = d.bbox()
        assert bb == (2.0, 2.0, 2.0, 2.0, 1.5, 1.5)

    def test_surface_bbox_is_none(self):
        from pyfds.domain.model import Surface
        s = Surface(name="inert")
        assert s.bbox() is None

    def test_ramp_bbox_is_none(self):
        from pyfds.domain.model import Ramp
        r = Ramp(name="fire_ramp", times=[0.0, 30.0], values=[0.0, 1.0])
        assert r.bbox() is None

    def test_bbox_returns_tuple_of_6_floats(self):
        obst = _make_obst()
        bb = obst.bbox()
        assert isinstance(bb, tuple)
        assert len(bb) == 6
        assert all(isinstance(v, float) for v in bb)


# ===========================================================================
# 4. Scenarios system
# ===========================================================================

class TestScenarioStore:

    def test_create_scenario(self):
        from pyfds.domain.scenario import ScenarioStore
        store = ScenarioStore()
        s = store.create("high_hrr")
        assert s.name == "high_hrr"

    def test_create_duplicate_raises(self):
        from pyfds.domain.scenario import ScenarioStore
        store = ScenarioStore()
        store.create("s1")
        with pytest.raises(ValueError, match="already exists"):
            store.create("s1")

    def test_get_returns_scenario(self):
        from pyfds.domain.scenario import ScenarioStore
        store = ScenarioStore()
        store.create("s1")
        assert store.get("s1") is not None

    def test_get_missing_returns_none(self):
        from pyfds.domain.scenario import ScenarioStore
        store = ScenarioStore()
        assert store.get("nope") is None

    def test_all_returns_list(self):
        from pyfds.domain.scenario import ScenarioStore
        store = ScenarioStore()
        store.create("a")
        store.create("b")
        assert len(store.all()) == 2

    def test_clone_copies_overrides(self):
        from pyfds.domain.scenario import ScenarioStore
        store = ScenarioStore()
        s = store.create("base")
        s.add_override("uid123", "heat_release_rate", 1000.0)
        cloned = store.clone("base", "high_hrr")
        assert "uid123" in cloned.overrides

    def test_delete_inactive_scenario(self):
        from pyfds.domain.scenario import ScenarioStore
        store = ScenarioStore()
        store.create("s1")
        store.delete("s1")
        assert store.get("s1") is None

    def test_set_override_registers_value(self):
        from pyfds.domain.scenario import ScenarioStore
        store = ScenarioStore()
        store.create("s1")
        entity = _make_obst()
        store.set_override("s1", entity, "x_max", 5.0)
        s = store.get("s1")
        assert entity.uid in s.overrides
        assert s.overrides[entity.uid]["x_max"] == 5.0

    def test_apply_patches_entity(self):
        from pyfds.domain.scenario import ScenarioStore
        p = _make_project()
        store = ScenarioStore()
        s = store.create("wide_room")
        obst = p.obstructions[0]
        store.set_override("wide_room", obst, "x_max", 99.0)
        store.apply(p, "wide_room")
        assert obst.x_max == 99.0

    def test_reset_restores_entity(self):
        from pyfds.domain.scenario import ScenarioStore
        p = _make_project()
        store = ScenarioStore()
        s = store.create("wide_room")
        obst = p.obstructions[0]
        original_x_max = obst.x_max
        store.set_override("wide_room", obst, "x_max", 99.0)
        store.apply(p, "wide_room")
        store.reset(p)
        assert obst.x_max == original_x_max

    def test_active_is_none_initially(self):
        from pyfds.domain.scenario import ScenarioStore
        assert ScenarioStore().active is None

    def test_active_set_after_apply(self):
        from pyfds.domain.scenario import ScenarioStore
        p = _make_project()
        store = ScenarioStore()
        store.create("s1")
        store.apply(p, "s1")
        assert store.active == "s1"

    def test_active_cleared_after_reset(self):
        from pyfds.domain.scenario import ScenarioStore
        p = _make_project()
        store = ScenarioStore()
        store.create("s1")
        store.apply(p, "s1")
        store.reset(p)
        assert store.active is None

    def test_double_apply_raises(self):
        from pyfds.domain.scenario import ScenarioStore
        p = _make_project()
        store = ScenarioStore()
        store.create("s1")
        store.create("s2")
        store.apply(p, "s1")
        with pytest.raises(RuntimeError):
            store.apply(p, "s2")


class TestScenarioManagerApi:

    def test_create_via_api(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        s = api.scenarios.create("smoke_test")
        assert s.name == "smoke_test"

    def test_all_empty_initially(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        assert api.scenarios.all() == []

    def test_apply_and_reset_via_api(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        from pyfds.domain.model import Obstruction
        obst = api.obstructions.add_obstruction(
            xb=[0, 1, 0, 1, 0, 1], surf_id="INERT", name="obst1"
        )
        api.scenarios.create("s1")
        api.scenarios.set_override("s1", obst, "x_max", 5.0)
        api.scenarios.apply("s1")
        assert obst.x_max == pytest.approx(5.0)
        api.scenarios.reset()
        assert obst.x_max == pytest.approx(1.0)

    def test_active_property(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.scenarios.create("s1")
        assert api.scenarios.active is None
        api.scenarios.apply("s1")
        assert api.scenarios.active == "s1"

    def test_remove_alias_deletes_by_entity_name(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        s = api.scenarios.create("s1")
        api.scenarios.remove(s)
        assert api.scenarios.get("s1") is None

    def test_export_all_writes_one_fds_per_scenario_and_resets(self, tmp_path):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="obst1")
        api.scenarios.create("low")
        api.scenarios.set_override("low", obst, "x_max", 3.0)
        api.scenarios.create("high")
        api.scenarios.set_override("high", obst, "x_max", 9.0)

        written = api.scenarios.export_all(str(tmp_path))

        assert set(written.keys()) == {"low", "high"}
        for path in written.values():
            assert Path(path).exists()
        # Never left applied after export, and the original value is restored.
        assert api.scenarios.active is None
        assert obst.x_max == pytest.approx(1.0)

    def test_export_all_raises_if_a_scenario_is_already_active(self, tmp_path):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.scenarios.create("s1")
        api.scenarios.apply("s1")
        with pytest.raises(RuntimeError):
            api.scenarios.export_all(str(tmp_path))
        api.scenarios.reset()


# ===========================================================================
# 5. MirrorCommand + RotateCommand
# ===========================================================================

class TestMirrorCommand:

    def test_mirror_x_axis(self):
        from pyfds.automation.commands import MirrorCommand
        obst = _make_obst(x=(1, 3), y=(0, 4), z=(0, 2))
        cmd = MirrorCommand(obst, axis=0, position=0.0)
        cmd.execute()
        assert obst.x_min == pytest.approx(-3.0)
        assert obst.x_max == pytest.approx(-1.0)
        assert obst.y_min == pytest.approx(0.0)

    def test_mirror_y_axis(self):
        from pyfds.automation.commands import MirrorCommand
        obst = _make_obst(x=(0, 2), y=(1, 3), z=(0, 2))
        cmd = MirrorCommand(obst, axis=1, position=0.0)
        cmd.execute()
        assert obst.y_min == pytest.approx(-3.0)
        assert obst.y_max == pytest.approx(-1.0)

    def test_mirror_z_axis(self):
        from pyfds.automation.commands import MirrorCommand
        obst = _make_obst(x=(0, 2), y=(0, 2), z=(1, 3))
        cmd = MirrorCommand(obst, axis=2, position=0.0)
        cmd.execute()
        assert obst.z_min == pytest.approx(-3.0)
        assert obst.z_max == pytest.approx(-1.0)

    def test_mirror_centroid_default(self):
        from pyfds.automation.commands import MirrorCommand
        obst = _make_obst(x=(0, 4), y=(0, 4), z=(0, 2))
        cmd = MirrorCommand(obst, axis=0)  # default pos = centroid x = 2.0
        cmd.execute()
        assert obst.x_min == pytest.approx(0.0)
        assert obst.x_max == pytest.approx(4.0)

    def test_mirror_undo_restores(self):
        from pyfds.automation.commands import MirrorCommand
        obst = _make_obst(x=(1, 3), y=(0, 4), z=(0, 2))
        cmd = MirrorCommand(obst, axis=0, position=0.0)
        cmd.execute()
        cmd.undo()
        assert obst.x_min == pytest.approx(1.0)
        assert obst.x_max == pytest.approx(3.0)

    def test_invalid_axis_raises(self):
        from pyfds.automation.commands import MirrorCommand
        obst = _make_obst()
        with pytest.raises(ValueError, match="axis"):
            MirrorCommand(obst, axis=3)

    def test_mirror_via_pipeline(self):
        from pyfds.automation.commands import MirrorCommand, CommandPipeline
        p = _make_project()
        pipe = CommandPipeline(p)
        obst = _make_obst(x=(1, 3), y=(0, 4), z=(0, 2))
        p.add_entity(obst)
        result = pipe.execute(MirrorCommand(obst, axis=0, position=0.0))
        assert result.success
        pipe.undo()
        assert obst.x_min == pytest.approx(1.0)


class TestRotateCommand:

    def test_rotate_180(self):
        from pyfds.automation.commands import RotateCommand
        # 1×1 box centred at (1,1) rotated 180° around origin (0,0)
        obst = _make_obst(x=(0.5, 1.5), y=(0.5, 1.5), z=(0, 2))
        cmd = RotateCommand(obst, degrees=180, origin=(0.0, 0.0))
        cmd.execute()
        assert obst.x_min == pytest.approx(-1.5)
        assert obst.x_max == pytest.approx(-0.5)
        assert obst.y_min == pytest.approx(-1.5)
        assert obst.y_max == pytest.approx(-0.5)

    def test_rotate_90(self):
        from pyfds.automation.commands import RotateCommand
        # 1×2 box: x=(0,1), y=(0,2) rotated 90° CCW around (0,0)
        obst = _make_obst(x=(0, 1), y=(0, 2), z=(0, 1))
        cmd = RotateCommand(obst, degrees=90, origin=(0.0, 0.0))
        cmd.execute()
        # After 90° CCW: (x,y) → (-y, x)
        # corners: (0,0)→(0,0), (1,0)→(0,1), (0,2)→(-2,0), (1,2)→(-2,1)
        assert obst.x_min == pytest.approx(-2.0)
        assert obst.x_max == pytest.approx(0.0)
        assert obst.y_min == pytest.approx(0.0)
        assert obst.y_max == pytest.approx(1.0)

    def test_rotate_z_unchanged(self):
        from pyfds.automation.commands import RotateCommand
        obst = _make_obst(z=(1, 3))
        cmd = RotateCommand(obst, degrees=180, origin=(0.0, 0.0))
        cmd.execute()
        assert obst.z_min == pytest.approx(1.0)
        assert obst.z_max == pytest.approx(3.0)

    def test_rotate_undo(self):
        from pyfds.automation.commands import RotateCommand
        obst = _make_obst(x=(0.5, 1.5), y=(0.5, 1.5), z=(0, 2))
        cmd = RotateCommand(obst, degrees=90, origin=(0.0, 0.0))
        cmd.execute()
        cmd.undo()
        assert obst.x_min == pytest.approx(0.5)
        assert obst.x_max == pytest.approx(1.5)

    def test_rotate_non_multiple_of_90_raises(self):
        from pyfds.automation.commands import RotateCommand
        obst = _make_obst()
        with pytest.raises(ValueError, match="multiple of 90"):
            RotateCommand(obst, degrees=45)

    def test_rotate_default_origin_centroid(self):
        from pyfds.automation.commands import RotateCommand
        # Square centred at (2,2) — rotating 360° = identity
        obst = _make_obst(x=(1, 3), y=(1, 3), z=(0, 1))
        cmd = RotateCommand(obst, degrees=360)
        cmd.execute()
        assert obst.x_min == pytest.approx(1.0)
        assert obst.x_max == pytest.approx(3.0)


# ===========================================================================
# 6. FloorManager
# ===========================================================================

class TestFloorManager:

    def test_define_floor(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        f = api.floors.define_floor("Ground", 0.0, 3.0)
        assert f.name == "Ground"
        assert f.z_min == 0.0
        assert f.z_max == 3.0

    def test_all_floors_sorted_by_z(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Level 2", 6.0, 9.0)
        api.floors.define_floor("Ground", 0.0, 3.0)
        api.floors.define_floor("Level 1", 3.0, 6.0)
        names = [f.name for f in api.floors.all_floors()]
        assert names == ["Ground", "Level 1", "Level 2"]

    def test_get_floor(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        assert api.floors.get_floor("Ground") is not None
        assert api.floors.get_floor("Roof") is None

    def test_delete_floor(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        api.floors.delete_floor("Ground")
        assert api.floors.get_floor("Ground") is None

    def test_floor_of_by_bbox(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        obst = _make_obst(z=(0, 2))   # z-centre = 1.0 → Ground
        f = api.floors.floor_of(obst)
        assert f is not None
        assert f.name == "Ground"

    def test_floor_of_no_match(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        obst = _make_obst(z=(5, 8))   # z-centre = 6.5 — outside Ground
        assert api.floors.floor_of(obst) is None

    def test_floor_of_surface_returns_none(self):
        from pyfds.api.controller import FdsApi
        from pyfds.domain.model import Surface
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        s = Surface(name="inert")
        assert api.floors.floor_of(s) is None

    def test_entities_on_floor(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        obst = api.obstructions.add_obstruction(
            xb=[0, 1, 0, 1, 0, 2], surf_id="INERT", name="ground_obst"
        )
        entities = api.floors.entities_on_floor("Ground")
        assert any(e.name == "ground_obst" for e in entities)

    def test_assign_and_floor_of(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        obst = _make_obst(z=(10, 12))   # outside ground by bbox
        api.floors.assign(obst, "Ground")
        f = api.floors.floor_of(obst)
        assert f.name == "Ground"

    def test_assign_unknown_floor_raises(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = _make_obst()
        with pytest.raises(KeyError):
            api.floors.assign(obst, "NonExistent")

    def test_auto_assign_all(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        api.obstructions.add_obstruction(
            xb=[0, 1, 0, 1, 0, 2], surf_id="INERT", name="low_obst"
        )
        count = api.floors.auto_assign_all()
        assert count > 0

    def test_repr(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        assert "Ground" in repr(api.floors)

    def test_all_alias_matches_all_floors(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Level 1", 3.0, 6.0)
        api.floors.define_floor("Ground", 0.0, 3.0)
        assert api.floors.all() == api.floors.all_floors()

    def test_remove_alias_deletes_by_entity_name(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        f = api.floors.define_floor("Ground", 0.0, 3.0)
        api.floors.remove(f)
        assert api.floors.get_floor("Ground") is None

    def test_export_then_import_floors_rematches_by_entity_name(self, tmp_path):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="ground_box")
        api.floors.define_floor("Ground", 0.0, 3.0, "ground floor")
        api.floors.define_floor("Level 1", 3.0, 6.0)
        api.floors.assign(obst, "Ground")

        path = tmp_path / "floors.json"
        api.floors.export_floors(str(path))
        assert path.exists()

        # A brand-new project/api — a fresh entity with the same NAME but a
        # different uid, simulating a save/reload round trip.
        api2 = FdsApi()
        obst2 = api2.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="ground_box")
        assert obst2.uid != obst.uid

        count = api2.floors.import_floors(str(path))

        assert count == 1
        assert [f.name for f in api2.floors.all_floors()] == ["Ground", "Level 1"]
        assert api2.floors.floor_of(obst2).name == "Ground"

    def test_import_floors_skips_unmatched_assignments(self, tmp_path):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="ghost_box")
        api.floors.define_floor("Ground", 0.0, 3.0)
        api.floors.assign(obst, "Ground")
        path = tmp_path / "floors.json"
        api.floors.export_floors(str(path))

        api2 = FdsApi()  # no "ghost_box" entity here
        count = api2.floors.import_floors(str(path))

        assert count == 0
        assert api2.floors.get_floor("Ground") is not None


# ===========================================================================
# 6b. GroupManager
# ===========================================================================

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


# ===========================================================================
# 7. resume_from_checkpoint (smoke — parses & writes, no FDS binary)
# ===========================================================================

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
