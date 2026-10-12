"""Unit tests — Phase 1 API additions. (part 2 of 3)."""


from __future__ import annotations

import math
import time
import pytest


def _make_project():
    from pyfds.domain.model import FdsProject, Mesh, Obstruction, Surface, Vent, Device
    p = FdsProject(chid="test")
    m = Mesh(name="Room", cell_count=(10, 10, 10),
             x_min=0, x_max=4, y_min=0, y_max=4, z_min=0, z_max=3)
    o = Obstruction(name="Wall", x_min=0, x_max=0.2, y_min=0, y_max=4,
                    z_min=0, z_max=3, surface_id="INERT")
    s = Surface(name="FIRE", heat_release_rate=500.0, color="RED")
    p.add_entity(m)
    p.add_entity(o)
    p.add_entity(s)
    return p


class TestEntityFactory:
    def test_create_mesh(self):
        from pyfds.domain.factory import EntityFactory
        from pyfds.domain.model import Mesh
        f = EntityFactory()
        m = f.create_mesh("Room", ijk=(20, 20, 15), xb=(0, 4, 0, 4, 0, 3))
        assert isinstance(m, Mesh)
        assert m.name == "Room"
        assert m.cell_count == (20, 20, 15)
        assert m.x_max == pytest.approx(4.0)

    def test_create_obstruction(self):
        from pyfds.domain.factory import EntityFactory
        from pyfds.domain.model import Obstruction
        f = EntityFactory()
        o = f.create_obstruction("Wall", xb=(0, 0.2, 0, 4, 0, 3))
        assert isinstance(o, Obstruction)
        assert o.surface_id == "INERT"

    def test_create_burner(self):
        from pyfds.domain.factory import EntityFactory
        from pyfds.domain.model import Surface
        f = EntityFactory()
        s = f.create_burner("Fire", xb=(1, 2, 1, 2, 0, 0), hrrpua=500.0)
        assert isinstance(s, Surface)
        assert s.heat_release_rate == 500.0

    def test_create_thermocouple(self):
        from pyfds.domain.factory import EntityFactory
        from pyfds.domain.model import Device
        f = EntityFactory()
        d = f.create_thermocouple("TC_01", xyz=(2.0, 2.0, 2.5))
        assert isinstance(d, Device)
        assert d.x == 2.0 and d.z == 2.5
        assert d.quantity == "TEMPERATURE"

    def test_create_sprinkler(self):
        from pyfds.domain.factory import EntityFactory
        from pyfds.domain.model import Device
        f = EntityFactory()
        spk = f.create_sprinkler("SPK_01", xyz=(2, 2, 2.4), prop_id="RTI-50")
        assert isinstance(spk, Device)
        assert spk.prop_id == "RTI-50"

    def test_create_reaction(self):
        from pyfds.domain.factory import EntityFactory
        from pyfds.domain.model import Reaction
        f = EntityFactory()
        r = f.create_reaction("FIRE", "PROPANE", heat_of_combustion=46460.0)
        assert isinstance(r, Reaction)
        assert r.heat_of_combustion == pytest.approx(46460.0)

    def test_create_ramp(self):
        from pyfds.domain.factory import EntityFactory
        from pyfds.domain.model import Ramp
        f = EntityFactory()
        ramp = f.create_ramp("R1", times=[0, 10, 60], values=[0, 0.5, 1.0])
        assert isinstance(ramp, Ramp)
        assert ramp.times[2] == 60.0

    def test_create_t_squared_ramp(self):
        from pyfds.domain.factory import EntityFactory
        f = EntityFactory()
        ramp = f.create_t_squared_ramp("T2", t_end=300.0)
        assert ramp.values[-1] == pytest.approx(1.0)
        assert ramp.values[0] == 0.0

    def test_create_sprinkler_prop(self):
        from pyfds.domain.factory import EntityFactory
        from pyfds.domain.model import Prop
        f = EntityFactory()
        prop = f.create_sprinkler_prop("RTI-50", rti=50.0)
        assert isinstance(prop, Prop)
        assert prop.rti == 50.0

    def test_generic_create_with_xb_shorthand(self):
        from pyfds.domain.factory import EntityFactory
        from pyfds.domain.model import Obstruction
        f = EntityFactory()
        o = f.create(Obstruction, name="O1", xb=(0, 1, 0, 2, 0, 1))
        assert o.x_min == 0.0 and o.x_max == 1.0

    def test_generic_create_with_ijk_shorthand(self):
        from pyfds.domain.factory import EntityFactory
        from pyfds.domain.model import Mesh
        f = EntityFactory()
        m = f.create(Mesh, name="M",
                     ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1))
        assert m.cell_count == (10, 10, 10)

    def test_plugin_registration(self):
        from pyfds.domain.factory import EntityFactory
        from pyfds.domain.model import Surface
        f = EntityFactory()
        f.register("create_hot_surface",
                   lambda **kw: Surface(name=kw["name"],
                                        heat_release_rate=kw.get("hrrpua", 1000.0)))
        fn = f.create_hot_surface
        surf = fn(name="HS", hrrpua=2000.0)
        assert surf.name == "HS"
        assert surf.heat_release_rate == 2000.0

    def test_xb_wrong_length_raises(self):
        from pyfds.domain.factory import EntityFactory
        f = EntityFactory()
        with pytest.raises(ValueError, match="XB must have 6"):
            f.create_mesh("Bad", ijk=(1, 1, 1), xb=(0, 1, 0, 1))

class TestGroupCommand:
    def test_execute_all_sub_commands(self):
        from pyfds.automation.commands import (
            GroupCommand, AddEntityCommand, RemoveEntityCommand,
        )
        from pyfds.domain.model import FdsProject, Surface
        p = FdsProject(chid="grp")
        s1 = Surface(name="S1")
        s2 = Surface(name="S2")
        cmd = GroupCommand([
            AddEntityCommand(p, s1),
            AddEntityCommand(p, s2),
        ], label="add two surfs")
        result = cmd.execute()
        assert result.success
        assert len(p.surfaces) == 2

    def test_undo_removes_all(self):
        from pyfds.automation.commands import GroupCommand, AddEntityCommand
        from pyfds.domain.model import FdsProject, Surface
        p = FdsProject(chid="grp")
        s1 = Surface(name="S1")
        s2 = Surface(name="S2")
        cmd = GroupCommand([AddEntityCommand(p, s1), AddEntityCommand(p, s2)])
        cmd.execute()
        cmd.undo()
        assert len(p.surfaces) == 0

    def test_rollback_on_failure(self):
        from pyfds.automation.commands import GroupCommand, AddEntityCommand, Command, CommandResult
        from pyfds.domain.model import FdsProject, Surface

        class FailCommand(Command):
            def execute(self):
                return CommandResult.fail("intentional fail")
            def undo(self):
                return CommandResult.ok("noop")

        p = FdsProject(chid="grp")
        s1 = Surface(name="S1")
        add_cmd = AddEntityCommand(p, s1)
        group = GroupCommand([add_cmd, FailCommand()])
        result = group.execute()
        assert not result.success
        assert len(p.surfaces) == 0  # rolled back

class TestSetHrrCommand:
    def test_changes_hrrpua(self):
        from pyfds.automation.commands import SetHrrCommand
        from pyfds.domain.model import Surface
        s = Surface(name="Fire", heat_release_rate=500.0)
        cmd = SetHrrCommand(s, new_hrrpua=1000.0)
        cmd.execute()
        assert s.heat_release_rate == pytest.approx(1000.0)

    def test_undo_restores_old_value(self):
        from pyfds.automation.commands import SetHrrCommand
        from pyfds.domain.model import Surface
        s = Surface(name="Fire", heat_release_rate=500.0)
        cmd = SetHrrCommand(s, new_hrrpua=1000.0)
        cmd.execute()
        cmd.undo()
        assert s.heat_release_rate == pytest.approx(500.0)

    def test_from_total_hrr_and_area(self):
        from pyfds.automation.commands import SetHrrCommand
        from pyfds.domain.model import Surface
        s = Surface(name="Fire", heat_release_rate=0.0)
        # 500 kW total over 2 m² => 250 kW/m²
        cmd = SetHrrCommand(s, new_hrrpua=500.0, area=2.0)
        cmd.execute()
        assert s.heat_release_rate == pytest.approx(250.0)

class TestScaleCommand:
    def test_scales_obstruction_bounds(self):
        from pyfds.automation.commands import ScaleCommand
        from pyfds.domain.model import Obstruction
        o = Obstruction(name="O", x_min=0, x_max=2, y_min=0, y_max=2,
                        z_min=0, z_max=1)
        cmd = ScaleCommand(o, factor=2.0, origin=(0, 0, 0))
        cmd.execute()
        assert o.x_max == pytest.approx(4.0)
        assert o.z_max == pytest.approx(2.0)

    def test_undo_restores_bounds(self):
        from pyfds.automation.commands import ScaleCommand
        from pyfds.domain.model import Obstruction
        o = Obstruction(name="O", x_min=0, x_max=2, y_min=0, y_max=2,
                        z_min=0, z_max=1)
        cmd = ScaleCommand(o, factor=2.0, origin=(0, 0, 0))
        cmd.execute()
        cmd.undo()
        assert o.x_max == pytest.approx(2.0)

class TestDuplicateEntityCommand:
    def test_creates_copy_with_new_name(self):
        from pyfds.automation.commands import DuplicateEntityCommand
        from pyfds.domain.model import FdsProject, Surface
        p = FdsProject(chid="dup")
        s = Surface(name="Original", heat_release_rate=500.0)
        p.add_entity(s)
        cmd = DuplicateEntityCommand(p, s, "Copy")
        cmd.execute()
        assert len(p.surfaces) == 2
        copy = p.get_by_name("Copy", Surface)
        assert copy is not None
        assert copy.heat_release_rate == pytest.approx(500.0)

    def test_undo_removes_copy(self):
        from pyfds.automation.commands import DuplicateEntityCommand
        from pyfds.domain.model import FdsProject, Surface
        p = FdsProject(chid="dup")
        s = Surface(name="Original", heat_release_rate=500.0)
        p.add_entity(s)
        cmd = DuplicateEntityCommand(p, s, "Copy")
        cmd.execute()
        cmd.undo()
        assert len(p.surfaces) == 1

class TestFdsProjectQueryMethods:
    def test_filter_by_name(self):
        p = _make_project()
        result = p.filter(type(p.meshes[0]), name="Room")
        assert len(result) == 1
        assert result[0].name == "Room"

    def test_filter_no_match(self):
        p = _make_project()
        result = p.filter(type(p.meshes[0]), name="Nonexistent")
        assert result == []

    def test_query_predicate(self):
        from pyfds.domain.model import Mesh
        p = _make_project()
        result = p.query(Mesh, lambda m: m.x_max > 3.0)
        assert len(result) == 1

    def test_query_unknown_type_returns_empty(self):
        from pyfds.domain.model import Mesh
        p = _make_project()

        class Alien:
            pass

        result = p.query(Alien, lambda x: True)  # type: ignore[arg-type]
        assert result == []

    def test_find_references_surface_id(self):
        p = _make_project()
        # Wall has surface_id="INERT"
        refs = p.find_references("INERT")
        assert any(getattr(e, "name", None) == "Wall" for e in refs)

    def test_find_references_no_match(self):
        p = _make_project()
        assert p.find_references("NONEXISTENT_SURFACE_XYZ") == []

    def test_filter_multiple_kwargs(self):
        from pyfds.domain.model import Obstruction
        p = _make_project()
        result = p.filter(Obstruction, name="Wall", surface_id="INERT")
        assert len(result) == 1

    def test_filter_wrong_field_no_match(self):
        from pyfds.domain.model import Obstruction
        p = _make_project()
        result = p.filter(Obstruction, surface_id="FIRE")
        assert result == []

class TestFdsApiNewManagers:
    def test_api_has_selection(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        assert hasattr(api, "selection")
        assert api.selection is not None

    def test_api_has_viewport(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        assert hasattr(api, "viewport")
        assert api.viewport is not None

    def test_api_has_schema(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        schema_reg = api.schema
        assert schema_reg is not None
        assert "Mesh" in schema_reg.entity_names

    def test_api_has_factory(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        assert hasattr(api, "factory")
        assert api.factory is not None

    def test_selection_rebinds_on_new(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        old_sel = api.selection
        api.new(chid="new_project")
        new_sel = api.selection
        assert old_sel is not new_sel

    def test_viewport_orbit_via_api(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        orig = api.viewport.state.camera.position
        api.viewport.orbit(45, 0)
        assert api.viewport.state.camera.position != orig

    def test_factory_creates_via_api(self):
        from pyfds.api.controller import FdsApi
        from pyfds.domain.model import Mesh
        api = FdsApi()
        m = api.factory.create_mesh("M", ijk=(5, 5, 5), xb=(0, 1, 0, 1, 0, 1))
        assert isinstance(m, Mesh)
