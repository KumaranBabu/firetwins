"""Unit tests — pyfds.api.controller (FdsApi facade)."""
from __future__ import annotations

import pytest
from pyfds.api.controller import FdsApi
from pyfds.domain.model import (
    FdsProject, Mesh, Surface, Obstruction, Device, Ramp, Vent, Material,
)


@pytest.fixture
def api():
    """FdsApi instance with a blank project."""
    return FdsApi()


@pytest.fixture
def loaded_api(simple_room_fds_path):
    """FdsApi loaded from the simple_room fixture."""
    a = FdsApi()
    a.load(simple_room_fds_path)
    return a


# ---------------------------------------------------------------------------
# Construction / new
# ---------------------------------------------------------------------------

class TestFdsApiConstruction:
    def test_default_api_has_project(self, api):
        assert api.project is not None
        assert isinstance(api.project, FdsProject)

    def test_api_with_provided_project(self):
        p = FdsProject(chid="custom")
        a = FdsApi(project=p)
        assert a.project.chid == "custom"

    def test_new_replaces_project(self, api):
        old_id = id(api.project)
        api.new(chid="fresh", title="Fresh Project")
        assert id(api.project) != old_id
        assert api.project.chid == "fresh"


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

class TestFdsApiLoadSave:
    def test_load_fds_file(self, api, simple_room_fds_path):
        api.load(simple_room_fds_path)
        assert api.project.chid == "simple_room"

    def test_load_updates_meshes(self, api, simple_room_fds_path):
        api.load(simple_room_fds_path)
        assert len(api.project.meshes) == 1

    def test_load_updates_devices(self, api, simple_room_fds_path):
        api.load(simple_room_fds_path)
        assert len(api.project.devices) >= 1

    def test_save_fds_file(self, api, simple_room_fds_path, tmp_path):
        api.load(simple_room_fds_path)
        out = tmp_path / "saved.fds"
        api.save(str(out))
        assert out.exists()

    def test_save_and_reload(self, api, simple_room_fds_path, tmp_path):
        api.load(simple_room_fds_path)
        out = tmp_path / "reload.fds"
        api.save(str(out))
        api2 = FdsApi()
        api2.load(str(out))
        assert api2.project.chid == api.project.chid

    def test_save_pyfds_format(self, api, simple_room_fds_path, tmp_path):
        api.load(simple_room_fds_path)
        out = tmp_path / "project.pyfds"
        api.save(str(out))
        assert out.exists()


# ---------------------------------------------------------------------------
# Mesh manager
# ---------------------------------------------------------------------------

class TestMeshManager:
    def test_add_mesh(self, api):
        api.meshes.add_mesh(ijk=(16, 16, 8), xb=(0, 4, 0, 4, 0, 2), id="m1")
        assert len(api.meshes.all()) == 1

    def test_add_mesh_returns_mesh_object(self, api):
        m = api.meshes.add_mesh(ijk=(10, 10, 5), xb=(0, 2, 0, 2, 0, 1), id="m2")
        assert isinstance(m, Mesh)

    def test_remove_mesh(self, api):
        m = api.meshes.add_mesh(ijk=(10, 10, 5), xb=(0, 2, 0, 2, 0, 1), id="m3")
        api.meshes.remove(m)
        assert len(api.meshes.all()) == 0

    def test_get_mesh_by_id(self, api):
        api.meshes.add_mesh(ijk=(10, 10, 5), xb=(0, 2, 0, 2, 0, 1), id="find_me")
        found = api.meshes.get("find_me")
        assert found is not None
        assert found.id == "find_me"

    def test_count(self, api):
        api.meshes.add_mesh(ijk=(10, 10, 5), xb=(0, 2, 0, 2, 0, 1), id="c1")
        api.meshes.add_mesh(ijk=(10, 10, 5), xb=(2, 4, 0, 2, 0, 1), id="c2")
        assert api.meshes.count() == 2

    def test_clear(self, api):
        api.meshes.add_mesh(ijk=(10, 10, 5), xb=(0, 2, 0, 2, 0, 1), id="clr")
        api.meshes.clear()
        assert api.meshes.count() == 0

    def test_check_poisson(self, api):
        api.meshes.add_mesh(ijk=(16, 16, 8), xb=(0, 4, 0, 4, 0, 2), id="p1")
        result = api.meshes.check_poisson()
        # Should return a dict mapping mesh id → bool
        assert "p1" in result


# ---------------------------------------------------------------------------
# Surface manager
# ---------------------------------------------------------------------------

class TestSurfaceManager:
    def test_add_burner(self, api):
        s = api.surfaces.add_burner(hrrpua=500.0, tau_q=-1.0, name="fire")
        assert isinstance(s, Surface)
        # Regression: add_burner used to pass hrrpua= straight into Surface(),
        # whose real field is heat_release_rate — the mismatch was silently
        # absorbed by pydantic's extra="allow", leaving heat_release_rate at
        # its None default while a meaningless .hrrpua extra leaked through
        # (which is what this test used to assert on).
        assert s.heat_release_rate == 500.0
        assert s.name == "fire"

    def test_all_surfaces(self, api):
        api.surfaces.add_burner(hrrpua=200.0, name="s1")
        api.surfaces.add_burner(hrrpua=300.0, name="s2")
        assert api.surfaces.count() == 2
        assert api.surfaces.get("s1").heat_release_rate == 200.0
        assert api.surfaces.get("s2").heat_release_rate == 300.0

    def test_add_from_library_returns_multilayer_surface(self, api):
        s = api.surfaces.add_from_library("gypsum_wall_12mm")
        assert isinstance(s, Surface)
        assert s.name == "GYPSUM_WALL_12MM"
        assert len(s.layers) >= 1

    def test_add_from_library_unknown_preset_raises(self, api):
        with pytest.raises(KeyError):
            api.surfaces.add_from_library("not_a_real_surface")


# ---------------------------------------------------------------------------
# Obstruction manager
# ---------------------------------------------------------------------------

class TestObstManager:
    def test_add_obstruction_sets_real_bounds_and_surface(self, api):
        # Regression: add_obstruction used to pass xb=/surf_id= straight into
        # Obstruction(), whose real fields are x_min..z_max/surface_id — the
        # mismatch was silently absorbed by extra="allow" and every
        # obstruction came out as a default (0,1)x(0,1)x(0,1) INERT cube
        # no matter what was requested.
        o = api.obstructions.add_obstruction(xb=[1, 2, 3, 4, 5, 6], surf_id="BURNER", name="box1")
        assert isinstance(o, Obstruction)
        assert (o.x_min, o.x_max, o.y_min, o.y_max, o.z_min, o.z_max) == (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
        assert o.surface_id == "BURNER"
        assert o.name == "box1"

    def test_add_obstruction_default_surf_id(self, api):
        o = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="plain")
        assert o.surface_id == "INERT"


# ---------------------------------------------------------------------------
# Vent / Hole managers
# ---------------------------------------------------------------------------

class TestVentManager:
    def test_add_vent_sets_bounds_and_surface(self, api):
        v = api.vents.add_vent(xb=[0, 1, 0, 1, 2, 2], surf_id="BURNER", name="vent1")
        assert (v.x_min, v.x_max, v.y_min, v.y_max, v.z_min, v.z_max) == (0.0, 1.0, 0.0, 1.0, 2.0, 2.0)
        assert v.surface_id == "BURNER"
        assert v.name == "vent1"

    def test_add_vent_default_surf_id_is_open(self, api):
        v = api.vents.add_vent(xb=[0, 1, 0, 1, 0, 0], name="v1")
        assert v.surface_id == "OPEN"

    def test_remove_vent(self, api):
        v = api.vents.add_vent(xb=[0, 1, 0, 1, 0, 0], name="v1")
        api.vents.remove(v)
        assert api.vents.count() == 0


class TestHoleManager:
    def test_add_hole_sets_bounds(self, api):
        h = api.holes.add_hole(xb=[1, 2, 1, 2, 0, 3], name="door1")
        assert (h.x_min, h.x_max, h.y_min, h.y_max, h.z_min, h.z_max) == (1.0, 2.0, 1.0, 2.0, 0.0, 3.0)
        assert h.name == "door1"

    def test_remove_hole(self, api):
        h = api.holes.add_hole(xb=[0, 1, 0, 1, 0, 1], name="h1")
        api.holes.remove(h)
        assert api.holes.count() == 0


# ---------------------------------------------------------------------------
# Output managers (Slice / BoundaryFile / IsoSurface / Plot3D)
# ---------------------------------------------------------------------------

class TestOutputManagers:
    def test_add_slice(self, api):
        s = api.slices.add_slice(quantity="TEMPERATURE", plane="Y", position=2.0, name="slc1")
        assert s.name == "slc1"
        assert s.quantity == "TEMPERATURE"
        assert s.plane == "Y"
        assert s.position == 2.0

    def test_add_slice_rejects_invalid_quantity(self, api):
        with pytest.raises(ValueError):
            api.slices.add_slice(quantity="NOT_REAL", name="bad")

    def test_add_slice_3d_volumetric_via_xb(self, api):
        s = api.slices.add_slice(quantity="TEMPERATURE", xb=[0, 4, 0, 4, 0, 2], name="vol1")
        assert s.xb == (0, 4, 0, 4, 0, 2) or list(s.xb) == [0, 4, 0, 4, 0, 2]

    def test_add_boundary_file(self, api):
        b = api.bndfs.add_boundary_file(quantity="WALL TEMPERATURE", name="bndf1")
        assert b.name == "bndf1"
        assert b.quantity == "WALL TEMPERATURE"

    def test_add_boundary_file_rejects_invalid_quantity(self, api):
        with pytest.raises(ValueError):
            api.bndfs.add_boundary_file(quantity="NOT_REAL")

    def test_add_isosurface(self, api):
        iso = api.isofs.add_isosurface(quantity="TEMPERATURE", value=60.0, name="iso1")
        assert iso.name == "iso1"
        assert iso.value == 60.0

    def test_add_isosurface_rejects_invalid_quantity(self, api):
        with pytest.raises(ValueError):
            api.isofs.add_isosurface(quantity="NOT_REAL", value=1.0)

    def test_add_plot3d(self, api):
        p = api.plot3ds.add_plot3d(quantity="TEMPERATURE", name="pl1")
        assert p.name == "pl1"
        assert p.quantity == "TEMPERATURE"

    def test_add_plot3d_rejects_invalid_quantity(self, api):
        with pytest.raises(ValueError):
            api.plot3ds.add_plot3d(quantity="NOT_REAL")

    def test_counts_and_removal(self, api):
        s = api.slices.add_slice(quantity="TEMPERATURE", name="s1")
        b = api.bndfs.add_boundary_file(quantity="WALL TEMPERATURE", name="b1")
        iso = api.isofs.add_isosurface(quantity="TEMPERATURE", value=1.0, name="i1")
        p = api.plot3ds.add_plot3d(quantity="TEMPERATURE", name="p1")
        assert (api.slices.count(), api.bndfs.count(), api.isofs.count(), api.plot3ds.count()) == (1, 1, 1, 1)
        api.slices.remove(s)
        api.bndfs.remove(b)
        api.isofs.remove(iso)
        api.plot3ds.remove(p)
        assert (api.slices.count(), api.bndfs.count(), api.isofs.count(), api.plot3ds.count()) == (0, 0, 0, 0)


# ---------------------------------------------------------------------------
# HVAC managers (Node / Duct / Fan / Damper / Filter / Leakage)
# ---------------------------------------------------------------------------

class TestHvacManagers:
    def test_add_hvac_node(self, api):
        node = api.hvac_nodes.add_node(xyz=[1.0, 2.0, 3.0], ambient=True, name="amb1")
        assert (node.x, node.y, node.z) == (1.0, 2.0, 3.0)
        assert node.ambient is True
        assert node.name == "amb1"

    def test_add_hvac_node_default_not_ambient(self, api):
        node = api.hvac_nodes.add_node(xyz=[0, 0, 0], name="room_node")
        assert node.ambient is False
        assert node.vent_id is None

    def test_add_hvac_duct_connects_two_nodes(self, api):
        api.hvac_nodes.add_node(xyz=[0, 0, 0], name="n1")
        api.hvac_nodes.add_node(xyz=[5, 0, 0], name="n2")
        duct = api.hvac_ducts.add_duct(node_id_1="n1", node_id_2="n2", diameter=0.3, name="duct1")
        assert duct.node_id_1 == "n1"
        assert duct.node_id_2 == "n2"
        assert duct.diameter == 0.3

    def test_add_fan_on_duct(self, api):
        fan = api.fans.add_fan(duct_id="duct1", volume_flow_rate=1.5, name="fan1")
        assert fan.duct_id == "duct1"
        assert fan.volume_flow_rate == 1.5

    def test_add_damper_on_duct(self, api):
        damper = api.dampers.add_damper(duct_id="duct1", ctrl_id="ctrl1", name="damper1")
        assert damper.duct_id == "duct1"
        assert damper.ctrl_id == "ctrl1"

    def test_add_hvac_filter_on_duct(self, api):
        f = api.hvac_filters.add_filter(duct_id="duct1", efficiency=0.95, name="filter1")
        assert f.duct_id == "duct1"
        assert f.efficiency == 0.95

    def test_add_hvac_leakage_between_zones(self, api):
        leak = api.hvac_leakages.add_leakage(zone_id_1="z1", zone_id_2="z2", area=0.002, name="leak1")
        assert (leak.zone_id_1, leak.zone_id_2, leak.area) == ("z1", "z2", 0.002)

    def test_counts_and_removal(self, api):
        n = api.hvac_nodes.add_node(xyz=[0, 0, 0], name="n1")
        d = api.hvac_ducts.add_duct(node_id_1="n1", node_id_2="n1", name="d1")
        fan = api.fans.add_fan(duct_id="d1", name="fan1")
        damper = api.dampers.add_damper(duct_id="d1", ctrl_id="c1", name="damper1")
        filt = api.hvac_filters.add_filter(duct_id="d1", name="filter1")
        leak = api.hvac_leakages.add_leakage(zone_id_1="z1", zone_id_2="z2", name="leak1")
        counts = (
            api.hvac_nodes.count(), api.hvac_ducts.count(), api.fans.count(),
            api.dampers.count(), api.hvac_filters.count(), api.hvac_leakages.count(),
        )
        assert counts == (1, 1, 1, 1, 1, 1)
        api.hvac_nodes.remove(n)
        api.hvac_ducts.remove(d)
        api.fans.remove(fan)
        api.dampers.remove(damper)
        api.hvac_filters.remove(filt)
        api.hvac_leakages.remove(leak)
        counts_after = (
            api.hvac_nodes.count(), api.hvac_ducts.count(), api.fans.count(),
            api.dampers.count(), api.hvac_filters.count(), api.hvac_leakages.count(),
        )
        assert counts_after == (0, 0, 0, 0, 0, 0)


# ---------------------------------------------------------------------------
# Init / Particle / Prof managers
# ---------------------------------------------------------------------------

class TestInitParticleProfManagers:
    def test_add_init_sets_bounds_and_temperature(self, api):
        init = api.inits.add_init(xb=[0, 2, 0, 2, 0, 2], temperature=25.0, name="init1")
        assert (init.x_min, init.x_max, init.y_min, init.y_max, init.z_min, init.z_max) == (0.0, 2.0, 0.0, 2.0, 0.0, 2.0)
        assert init.temperature == 25.0

    def test_add_particle_class(self, api):
        particle = api.particles.add_particle_class(diameter=200.0, name="water_droplet")
        assert particle.name == "water_droplet"
        assert particle.diameter == 200.0

    def test_add_init_as_particle_cloud_references_particle_class(self, api):
        api.particles.add_particle_class(diameter=200.0, name="water_droplet")
        cloud = api.inits.add_init(xb=[0, 1, 0, 1, 0, 1], part_id="water_droplet", n_particles=1000, name="cloud1")
        assert cloud.part_id == "water_droplet"
        assert cloud.n_particles == 1000

    def test_add_profile(self, api):
        prof = api.profs.add_profile(quantity="TEMPERATURE", xyz=[1.0, 2.0, 0.0], name="prof1")
        assert prof.quantity == "TEMPERATURE"
        assert (prof.x, prof.y, prof.z) == (1.0, 2.0, 0.0)

    def test_add_profile_rejects_invalid_quantity(self, api):
        with pytest.raises(ValueError):
            api.profs.add_profile(quantity="NOT_REAL", xyz=[0, 0, 0])

    def test_counts_and_removal(self, api):
        init = api.inits.add_init(xb=[0, 1, 0, 1, 0, 1], name="i1")
        particle = api.particles.add_particle_class(name="p1")
        prof = api.profs.add_profile(quantity="TEMPERATURE", xyz=[0, 0, 0], name="pr1")
        assert (api.inits.count(), api.particles.count(), api.profs.count()) == (1, 1, 1)
        api.inits.remove(init)
        api.particles.remove(particle)
        api.profs.remove(prof)
        assert (api.inits.count(), api.particles.count(), api.profs.count()) == (0, 0, 0)


# ---------------------------------------------------------------------------
# Ramp manager
# ---------------------------------------------------------------------------

class TestRampManager:
    def test_add_ramp_sets_name(self, api):
        # Regression: Ramp.id is a read-only alias for .name (FdsEntity) —
        # constructing with id= instead of name= left every ramp named
        # "DefaultRamp", colliding across the whole project.
        r = api.ramps.add_ramp(ramp_id="fire_ramp", times=[0, 60, 120], values=[0, 1, 1])
        assert isinstance(r, Ramp)
        assert r.name == "fire_ramp"
        assert api.ramps.get("fire_ramp") is r

    def test_two_ramps_do_not_collide(self, api):
        api.ramps.add_ramp(ramp_id="r1", times=[0, 10], values=[0, 1])
        api.ramps.add_ramp(ramp_id="r2", times=[0, 10], values=[1, 0])
        assert api.ramps.count() == 2
        assert api.ramps.get("r1").name == "r1"
        assert api.ramps.get("r2").name == "r2"


# ---------------------------------------------------------------------------
# Material manager
# ---------------------------------------------------------------------------

class TestMaterialManager:
    def test_add_from_library_returns_populated_material(self, api):
        # Regression: add_from_library instantiated a fresh, empty
        # domain.materials.MaterialLibrary() (a legacy v0.2 shim) instead of
        # the populated domain.material_presets registry — every preset
        # name, including real ones, always raised KeyError.
        m = api.materials.add_from_library("concrete")
        assert isinstance(m, Material)
        assert m.density == pytest.approx(2280.0)
        assert m.conductivity == pytest.approx(1.6)

    def test_add_from_library_unknown_preset_raises(self, api):
        with pytest.raises(KeyError):
            api.materials.add_from_library("not_a_real_material")


# ---------------------------------------------------------------------------
# Device manager
# ---------------------------------------------------------------------------

class TestDeviceManager:
    def test_add_thermocouple(self, api):
        d = api.devices.add_thermocouple(xyz=(1.0, 1.0, 1.5), devc_id="tc01")
        assert isinstance(d, Device)
        assert d.quantity == "TEMPERATURE"

    def test_add_thermocouple_sets_name_from_devc_id(self, api):
        # Regression: Device.id is a read-only alias for .name (FdsEntity), so
        # constructing with id= instead of name= silently drops it via
        # pydantic's extra="allow" and every device ends up "DefaultDevice".
        d = api.devices.add_thermocouple(xyz=(1, 1, 1), devc_id="tc01")
        assert d.name == "tc01"
        assert api.devices.get("tc01") is d

    def test_add_sprinkler_sets_name_from_id(self, api):
        d = api.devices.add_sprinkler(xyz=(1, 1, 2), prop_id="SPRINKLER_PROP", id="spk01")
        assert d.name == "spk01"
        assert api.devices.get("spk01") is d

    def test_all_devices(self, api):
        api.devices.add_thermocouple((1, 1, 1), "tc_a")
        api.devices.add_thermocouple((2, 2, 2), "tc_b")
        assert api.devices.count() == 2
        assert api.devices.get("tc_a") is not None
        assert api.devices.get("tc_b") is not None
        assert api.devices.get("tc_a") is not api.devices.get("tc_b")

    def test_add_device_generic_quantity(self, api):
        d = api.devices.add_device(quantity="VISIBILITY", xyz=(2, 2, 1), name="smoke01")
        assert isinstance(d, Device)
        assert d.quantity == "VISIBILITY"
        assert d.name == "smoke01"

    def test_add_device_rejects_invalid_quantity(self, api):
        with pytest.raises(ValueError):
            api.devices.add_device(quantity="NOT_A_REAL_QUANTITY", xyz=(0, 0, 0))

    def test_add_device_default_name_when_unnamed(self, api):
        d1 = api.devices.add_device(quantity="VELOCITY", xyz=(0, 0, 0))
        d2 = api.devices.add_device(quantity="VELOCITY", xyz=(1, 0, 0))
        assert d1.name != d2.name


# ---------------------------------------------------------------------------
# Validation manager
# ---------------------------------------------------------------------------

class TestValidationManager:
    def test_validate_clean_project(self, api):
        api.meshes.add_mesh(ijk=(16, 16, 8), xb=(0, 4, 0, 4, 0, 2), id="vm1")
        report = api.validation.validate()
        assert report is not None
        assert report.passed is True

    def test_validate_empty_project_fails(self, api):
        report = api.validation.validate()
        assert report.passed is False


# ---------------------------------------------------------------------------
# History manager (undo/redo via API)
# ---------------------------------------------------------------------------

class TestHistoryManager:
    def test_can_undo_after_set_timing(self, api):
        api.set_timing(t_end=300.0)
        assert api.history.can_undo()

    def test_undo_reverses_set_timing(self, api):
        original = api.project.params.t_end
        api.set_timing(t_end=999.0)
        api.history.undo()
        assert api.project.params.t_end == original

    def test_history_labels_not_empty(self, api):
        api.set_timing(t_end=200.0)
        labels = api.history.history()
        assert len(labels) >= 1

    def test_clear_history(self, api):
        api.set_timing(t_end=100.0)
        api.history.clear()
        assert not api.history.can_undo()


# ---------------------------------------------------------------------------
# subscribe / emit
# ---------------------------------------------------------------------------

class TestApiEvents:
    def test_subscribe_and_receive_event(self, api):
        from pyfds.core.events import EventType
        received = []
        api.subscribe(EventType.OBJECT_ADDED, received.append)
        api.meshes.add_mesh(ijk=(10, 10, 5), xb=(0, 2, 0, 2, 0, 1), id="evt_m")
        assert len(received) >= 1

    def test_unsubscribe_stops_events(self, api):
        from pyfds.core.events import EventType
        received = []
        sub_id = api.subscribe(EventType.OBJECT_ADDED, received.append)
        api.unsubscribe(sub_id)
        api.meshes.add_mesh(ijk=(10, 10, 5), xb=(0, 2, 0, 2, 0, 1), id="no_evt")
        assert len(received) == 0


# ---------------------------------------------------------------------------
# set_timing / set_property
# ---------------------------------------------------------------------------

class TestApiMutators:
    def test_set_timing(self, api):
        api.set_timing(t_end=180.0, t_begin=5.0)
        assert api.project.params.t_end == 180.0
        assert api.project.params.t_begin == 5.0

    def test_set_property_via_dot_path(self, api):
        api.set_property(api.project, "chid", "new_chid")
        assert api.project.chid == "new_chid"


# ---------------------------------------------------------------------------
# Info / snapshot
# ---------------------------------------------------------------------------

class TestApiInfo:
    def test_info_returns_string(self, api, simple_room_fds_path):
        api.load(simple_room_fds_path)
        info = api.info()
        assert isinstance(info, str)
        assert "simple_room" in info

    def test_snapshot_returns_state_snapshot(self, api):
        from pyfds.core.state import StateSnapshot
        snap = api.snapshot()
        assert isinstance(snap, StateSnapshot)
