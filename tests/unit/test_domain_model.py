"""Unit tests — pyfds.domain.model (FdsProject and entity models)."""
from __future__ import annotations

import pytest
from pyfds.domain.model import (
    FdsProject, Mesh, Obstruction, Hole, Surface, Vent, Device,
    Material, Reaction, Ramp, Control, Prop, Particle, Species,
    HvacNode, HvacDuct, Fan, Damper, Zone, Prof, Slice, BoundaryFile,
    IsoSurface, SimulationParams, DumpParams, MiscParams, PresParams, RadiParams,
)


# ---------------------------------------------------------------------------
# SimulationParams / sub-models
# ---------------------------------------------------------------------------

class TestSimulationParams:
    def test_defaults(self):
        p = SimulationParams()
        assert p.t_end == 60.0
        assert p.t_begin == 0.0

    def test_custom_values(self):
        p = SimulationParams(t_end=300.0, t_begin=10.0)
        assert p.t_end == 300.0
        assert p.t_begin == 10.0

    def test_pydantic_model(self):
        p = SimulationParams(t_end=120.0)
        d = p.model_dump()
        assert d["t_end"] == 120.0


class TestMiscParams:
    def test_gvec_default(self):
        m = MiscParams()
        assert m.gvec == (0.0, 0.0, -9.81)

    def test_tmpa_default(self):
        assert MiscParams().tmpa == 20.0


class TestDumpParams:
    def test_dt_slcf_default(self):
        d = DumpParams()
        assert d.dt_slcf == 1.0

    def test_smoke3d_default(self):
        assert DumpParams().smoke3d is True


# ---------------------------------------------------------------------------
# Mesh
# ---------------------------------------------------------------------------

class TestMesh:
    def test_basic_creation(self):
        m = Mesh(name="m1", cell_count=(10, 10, 5),
                 x_min=0, x_max=2, y_min=0, y_max=2, z_min=0, z_max=1)
        assert m.name == "m1"
        assert m.cell_count == (10, 10, 5)

    def test_x_max_gt_x_min_validation(self):
        """x_max must be > x_min (Pydantic validator)."""
        with pytest.raises(Exception):
            Mesh(name="bad", x_min=2.0, x_max=1.0, y_min=0, y_max=1, z_min=0, z_max=1)

    def test_default_cell_count(self):
        m = Mesh()
        assert m.cell_count == (10, 10, 10)

    def test_uid_is_private(self):
        """Internal _uid should not appear in Pydantic model_dump."""
        m = Mesh(name="m")
        d = m.model_dump()
        assert "_uid" not in d

    def test_name_field(self):
        m = Mesh(name="test_mesh")
        assert m.name == "test_mesh"


# ---------------------------------------------------------------------------
# Obstruction
# ---------------------------------------------------------------------------

class TestObstruction:
    def test_basic_creation(self):
        o = Obstruction(name="floor", surface_id="INERT",
                        x_min=0, x_max=4, y_min=0, y_max=4, z_min=0, z_max=0.1)
        assert o.name == "floor"
        assert o.surface_id == "INERT"

    def test_coordinates_stored(self):
        o = Obstruction(name="o", x_min=1.0, x_max=2.0,
                        y_min=0.0, y_max=1.0, z_min=0.0, z_max=0.5)
        assert o.x_min == 1.0
        assert o.x_max == 2.0


# ---------------------------------------------------------------------------
# Surface
# ---------------------------------------------------------------------------

class TestSurface:
    def test_burner_surface(self):
        s = Surface(name="fire", heat_release_rate=500.0, tau_q=-1.0)
        assert s.heat_release_rate == 500.0
        assert s.tau_q == -1.0

    def test_inert_surface(self):
        s = Surface(name="inert")
        assert s.name == "inert"
        assert s.heat_release_rate is None

    def test_default_color(self):
        s = Surface(name="s")
        assert s.color == "GRAY"


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------

class TestDevice:
    def test_thermocouple(self):
        d = Device(name="tc01", quantity="TEMPERATURE", x=1.0, y=2.0, z=3.0)
        assert d.quantity == "TEMPERATURE"
        assert d.x == 1.0

    def test_xyz_tuple_accepted(self):
        d = Device(name="tc02", xyz=(1.0, 2.0, 3.0))
        assert d.xyz == (1.0, 2.0, 3.0)


# ---------------------------------------------------------------------------
# Ramp
# ---------------------------------------------------------------------------

class TestRamp:
    def test_times_and_values(self):
        r = Ramp(name="ramp_q", times=[0.0, 30.0, 60.0], values=[0.0, 1.0, 1.0])
        assert len(r.times) == 3
        assert r.values[1] == 1.0

    def test_empty_ramp(self):
        r = Ramp(name="r")
        assert r.times == []
        assert r.values == []

    def test_mismatched_times_values_raises(self):
        with pytest.raises(Exception):
            Ramp(name="bad", times=[0.0, 1.0], values=[0.0])

    def test_non_monotonic_times_raises(self):
        with pytest.raises(Exception):
            Ramp(name="bad", times=[10.0, 0.0], values=[1.0, 0.0])

    def test_add_point(self):
        r = Ramp(name="r")
        r.add_point(0.0, 0.0)
        r.add_point(10.0, 1.0)
        assert len(r.times) == 2


# ---------------------------------------------------------------------------
# FdsProject
# ---------------------------------------------------------------------------

class TestFdsProject:
    def test_blank_project(self):
        p = FdsProject()
        assert isinstance(p.chid, str)

    def test_custom_chid(self):
        p = FdsProject()
        p.chid = "my_case"
        assert p.chid == "my_case"

    def test_empty_collections_on_init(self):
        p = FdsProject()
        assert p.meshes == []
        assert p.obstructions == []
        assert p.surfaces == []
        assert p.devices == []
        assert p.ramps == []
        assert p.vents == []

    def test_get_collection_mesh(self):
        p = FdsProject()
        coll = p._get_collection(Mesh)
        assert coll is p.meshes

    def test_get_collection_obstruction(self):
        p = FdsProject()
        assert p._get_collection(Obstruction) is p.obstructions

    def test_get_collection_surface(self):
        p = FdsProject()
        assert p._get_collection(Surface) is p.surfaces

    def test_get_collection_device(self):
        p = FdsProject()
        assert p._get_collection(Device) is p.devices

    def test_get_collection_ramp(self):
        p = FdsProject()
        assert p._get_collection(Ramp) is p.ramps

    def test_get_collection_vent(self):
        p = FdsProject()
        assert p._get_collection(Vent) is p.vents

    def test_get_collection_material(self):
        p = FdsProject()
        assert p._get_collection(Material) is p.materials

    def test_get_collection_boundary_file(self):
        p = FdsProject()
        assert p._get_collection(BoundaryFile) is p.bndfs

    def test_get_collection_unknown_returns_none(self):
        p = FdsProject()
        result = p._get_collection(SimulationParams)
        assert result is None

    def test_project_has_unique_id(self):
        p1 = FdsProject()
        p2 = FdsProject()
        assert p1._project_id != p2._project_id

    def test_params_is_simulation_params(self):
        p = FdsProject()
        assert isinstance(p.params, SimulationParams)

    def test_dump_params_is_dump_params(self):
        p = FdsProject()
        assert isinstance(p.dump, DumpParams)

    def test_misc_params_defaults(self):
        p = FdsProject()
        assert isinstance(p.misc, MiscParams)

    def test_add_entity(self):
        p = FdsProject()
        m = Mesh(name="m1")
        p.add_entity(m)
        assert len(p.meshes) == 1
        assert m in p.meshes

    def test_add_registers_in_uid_index(self):
        p = FdsProject()
        m = Mesh(name="m1")
        p.add_entity(m)
        assert p.get_by_uid(m.uid) is m

    def test_remove_entity_by_uid(self):
        p = FdsProject()
        m = Mesh(name="m_to_remove")
        p.add_entity(m)
        p.remove_entity_by_uid(m.uid)
        assert m not in p.meshes

    def test_remove_nonexistent_uid_no_error(self):
        p = FdsProject()
        p.remove_entity_by_uid("nonexistent-uid")  # should not raise

    def test_add_direct_to_collection(self):
        p = FdsProject()
        m = Mesh(name="direct")
        p.add(p.meshes, m)
        assert len(p.meshes) == 1

    def test_remove_by_collection_and_uid(self):
        p = FdsProject()
        m = Mesh(name="rm")
        p.add(p.meshes, m)
        p.remove(p.meshes, m.uid)
        assert len(p.meshes) == 0

    def test_get_by_name(self):
        p = FdsProject()
        m = Mesh(name="find_me")
        p.add_entity(m)
        found = p.get_by_name("find_me", Mesh)
        assert found is m

    def test_all_entities(self):
        p = FdsProject()
        m = Mesh(name="m")
        s = Surface(name="s")
        p.add_entity(m)
        p.add_entity(s)
        entities = p.all_entities
        assert m in entities
        assert s in entities

    def test_clear(self):
        p = FdsProject()
        p.add_entity(Mesh(name="m"))
        p.add_entity(Surface(name="s"))
        p.clear()
        assert p.meshes == []
        assert p.surfaces == []
        assert p._uid_index == {}

    def test_entity_count(self):
        p = FdsProject()
        p.add_entity(Mesh(name="m"))
        p.add_entity(Mesh(name="m2"))
        counts = p.entity_count()
        assert counts["meshes"] == 2

    def test_surface_ids_includes_builtins(self):
        p = FdsProject()
        ids = p.surface_ids()
        assert "OPEN" in ids
        assert "INERT" in ids

    def test_observer_notified_on_add(self):
        class FakeObserver:
            events = []
            def update(self, et, payload):
                self.events.append(et)

        p = FdsProject()
        obs = FakeObserver()
        p.register_global_observer(obs)
        p.add_entity(Mesh(name="obs_mesh"))
        assert "OBJECT_ADDED" in obs.events


# ---------------------------------------------------------------------------
# Other entity stubs
# ---------------------------------------------------------------------------

class TestSlice:
    def test_creation(self):
        s = Slice(name="sl1", quantity="TEMPERATURE")
        assert s.quantity == "TEMPERATURE"


class TestBoundaryFile:
    def test_creation(self):
        b = BoundaryFile(name="bndf1", quantity="WALL TEMPERATURE")
        assert b.quantity == "WALL TEMPERATURE"


class TestIsoSurface:
    def test_creation(self):
        iso = IsoSurface(name="iso1", quantity="TEMPERATURE", value=200.0)
        assert iso.value == 200.0


class TestZone:
    def test_creation(self):
        z = Zone(name="zone1")
        assert z.name == "zone1"


class TestSpecies:
    def test_creation(self):
        s = Species(name="CO2")
        assert s.name == "CO2"


class TestRampMonotonic:
    """Ramp model validator enforces monotonic times."""
    def test_equal_times_rejected(self):
        with pytest.raises(Exception):
            Ramp(name="bad", times=[0.0, 0.0], values=[0.0, 1.0])
