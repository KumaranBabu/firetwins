"""Unit tests — Phase 4 & 5: (part 1 of 3)."""


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
