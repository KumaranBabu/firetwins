"""
Unit tests — Phase 1 API additions.

Covers:
  - SelectionManager
  - ViewportController / ViewportCamera
  - PropertyDescriptor / EntitySchema / SchemaRegistry
  - EntityFactory
  - GroupCommand, DuplicateEntityCommand, SetHrrCommand, ScaleCommand
  - FdsProject.filter(), query(), find_references()
  - FdsApi.selection, viewport, schema, factory
  - ValidationManager.auto_fix()
  - ExecutionManager.run_async()
  - CLI autofix + schema subcommands
"""
from __future__ import annotations

import math
import time
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ===========================================================================
# SelectionManager
# ===========================================================================

class TestSelectionManager:
    def test_select_and_clear(self):
        from pyfds.core.selection import SelectionManager
        from pyfds.domain.model import FdsProject, Mesh
        p = _make_project()
        sm = SelectionManager(project=p)
        mesh = p.meshes[0]
        sm.select(mesh)
        assert sm.count == 1
        assert sm.first is mesh
        sm.clear()
        assert sm.is_empty

    def test_select_many(self):
        from pyfds.core.selection import SelectionManager
        p = _make_project()
        sm = SelectionManager(project=p)
        sm.select_many([p.meshes[0], p.obstructions[0]])
        assert sm.count == 2

    def test_deselect(self):
        from pyfds.core.selection import SelectionManager
        p = _make_project()
        sm = SelectionManager(project=p)
        mesh = p.meshes[0]
        sm.select(mesh)
        sm.deselect(mesh)
        assert sm.is_empty

    def test_toggle(self):
        from pyfds.core.selection import SelectionManager, SelectionMode
        p = _make_project()
        sm = SelectionManager(project=p)
        mesh = p.meshes[0]
        sm.select(mesh, mode=SelectionMode.TOGGLE)
        assert sm.count == 1
        sm.select(mesh, mode=SelectionMode.TOGGLE)
        assert sm.count == 0

    def test_select_all_by_type(self):
        from pyfds.core.selection import SelectionManager
        from pyfds.domain.model import Mesh
        p = _make_project()
        sm = SelectionManager(project=p)
        sm.select_all(Mesh)
        assert sm.count == len(p.meshes)

    def test_filter_select(self):
        from pyfds.core.selection import SelectionManager
        p = _make_project()
        sm = SelectionManager(project=p)
        sm.filter_select(lambda e: getattr(e, "name", "") == "Room")
        assert sm.count == 1

    def test_snapshot_restore(self):
        from pyfds.core.selection import SelectionManager
        p = _make_project()
        sm = SelectionManager(project=p)
        sm.select(p.meshes[0])
        snap = sm.snapshot()
        sm.clear()
        assert sm.is_empty
        sm.restore(snap)
        assert sm.count == 1

    def test_only_returns_none_when_not_single(self):
        from pyfds.core.selection import SelectionManager
        p = _make_project()
        sm = SelectionManager(project=p)
        sm.select_many([p.meshes[0], p.obstructions[0]])
        assert sm.only is None

    def test_only_returns_entity_when_single(self):
        from pyfds.core.selection import SelectionManager
        p = _make_project()
        sm = SelectionManager(project=p)
        sm.select(p.meshes[0])
        assert sm.only is p.meshes[0]

    def test_save_and_restore_named_group(self):
        from pyfds.core.selection import SelectionManager
        p = _make_project()
        sm = SelectionManager(project=p)
        sm.select(p.meshes[0])
        sm.save_group("grp1")
        sm.clear()
        sm.restore_group("grp1")
        assert sm.count == 1

    def test_box_select(self):
        from pyfds.core.selection import SelectionManager
        p = _make_project()
        sm = SelectionManager(project=p)
        # Wall at x=(0,0.2), y=(0,4), z=(0,3) — fully inside box
        sm.box_select(-1, 5, -1, 5, -1, 5)
        assert sm.count >= 1


# ===========================================================================
# ViewportCamera / ViewportController
# ===========================================================================

class TestViewportCamera:
    def test_defaults(self):
        from pyfds.core.viewport import ViewportCamera, ProjectionMode
        cam = ViewportCamera()
        assert cam.projection == ProjectionMode.PERSPECTIVE
        assert cam.fov_deg == 45.0

    def test_distance(self):
        from pyfds.core.viewport import ViewportCamera
        cam = ViewportCamera(position=(3, 0, 0), target=(0, 0, 0))
        assert abs(cam.distance - 3.0) < 1e-9

    def test_orbit_changes_position(self):
        from pyfds.core.viewport import ViewportCamera
        cam = ViewportCamera(position=(10, 0, 0), target=(0, 0, 0))
        cam2 = cam.orbit(90, 0)
        assert abs(cam2.distance - cam.distance) < 1e-6
        assert abs(cam2.position[0] - cam.position[0]) > 0.1

    def test_pan_shifts_both(self):
        from pyfds.core.viewport import ViewportCamera
        cam = ViewportCamera()
        cam2 = cam.pan(1.0, 2.0)
        assert cam2.position[0] == cam.position[0] + 1.0
        assert cam2.target[1] == cam.target[1] + 2.0

    def test_zoom_perspective_moves_eye(self):
        from pyfds.core.viewport import ViewportCamera
        cam = ViewportCamera(position=(10, 0, 0), target=(0, 0, 0))
        cam2 = cam.zoom_to(2.0)
        assert cam2.distance < cam.distance

    def test_zoom_orthographic_changes_factor(self):
        from pyfds.core.viewport import ViewportCamera, ProjectionMode
        cam = ViewportCamera(projection=ProjectionMode.ORTHOGRAPHIC, zoom=1.0)
        cam2 = cam.zoom_to(2.0)
        assert cam2.zoom == pytest.approx(2.0)

    def test_from_preset_isometric(self):
        from pyfds.core.viewport import ViewportCamera, CameraPreset
        cam = ViewportCamera.from_preset(CameraPreset.ISOMETRIC)
        assert cam.target == (0, 0, 0)
        assert cam.distance > 0

    def test_to_dict_roundtrip(self):
        from pyfds.core.viewport import ViewportCamera
        cam = ViewportCamera()
        d = cam.to_dict()
        assert "position" in d
        assert "projection" in d


class TestViewportController:
    def test_initial_state(self):
        from pyfds.core.viewport import ViewportController, TransformMode
        vc = ViewportController()
        assert vc.state.transform_mode == TransformMode.SELECT

    def test_set_camera(self):
        from pyfds.core.viewport import ViewportController, ViewportCamera
        vc = ViewportController()
        new_cam = ViewportCamera(position=(5, 5, 5), target=(0, 0, 0))
        vc.set_camera(new_cam)
        assert vc.state.camera.position == (5, 5, 5)

    def test_apply_preset(self):
        from pyfds.core.viewport import ViewportController, CameraPreset
        vc = ViewportController()
        vc.apply_preset(CameraPreset.TOP)
        assert abs(vc.state.camera.position[0]) < 1e-6  # TOP view: x=0

    def test_orbit(self):
        from pyfds.core.viewport import ViewportController
        vc = ViewportController()
        orig_pos = vc.state.camera.position
        vc.orbit(45, 0)
        assert vc.state.camera.position != orig_pos

    def test_set_transform_mode(self):
        from pyfds.core.viewport import ViewportController, TransformMode
        vc = ViewportController()
        vc.set_transform_mode(TransformMode.TRANSLATE)
        assert vc.state.transform_mode == TransformMode.TRANSLATE

    def test_set_visibility(self):
        from pyfds.core.viewport import ViewportController, VisibilityFlags
        vc = ViewportController()
        vc.set_visibility(VisibilityFlags.MESHES, False)
        assert vc.state.is_visible(VisibilityFlags.MESHES) is False

    def test_toggle_wireframe(self):
        from pyfds.core.viewport import ViewportController
        vc = ViewportController()
        assert vc.state.show_wireframe is False
        vc.toggle_wireframe()
        assert vc.state.show_wireframe is True

    def test_frame_all(self):
        from pyfds.core.viewport import ViewportController
        vc = ViewportController()
        vc.frame_all(bbox=(0, 4, 0, 4, 0, 3))
        cx = vc.state.camera.target[0]
        assert abs(cx - 2.0) < 1e-6

    def test_set_clip_plane(self):
        from pyfds.core.viewport import ViewportController
        vc = ViewportController()
        vc.set_clip_plane(1.5)
        assert vc.state.clip_plane_z == 1.5

    def test_snap_settings(self):
        from pyfds.core.viewport import ViewportController
        vc = ViewportController()
        vc.set_snap(grid_size=0.05, enabled=False)
        assert vc.state.snap.grid_size == pytest.approx(0.05)
        assert vc.state.snap.enabled is False

    def test_to_dict(self):
        from pyfds.core.viewport import ViewportController
        vc = ViewportController()
        d = vc.to_dict()
        assert "camera" in d
        assert "visibility" in d


# ===========================================================================
# EntitySchema / SchemaRegistry
# ===========================================================================

class TestSchemaRegistry:
    def test_get_schema_registry_is_singleton(self):
        from pyfds.domain.schema import get_schema_registry
        r1 = get_schema_registry()
        r2 = get_schema_registry()
        assert r1 is r2

    def test_mesh_schema_registered(self):
        from pyfds.domain.schema import get_schema_registry
        reg = get_schema_registry()
        schema = reg.get("Mesh")
        assert schema is not None
        assert schema.fds_namelist == "MESH"

    def test_mesh_has_required_properties(self):
        from pyfds.domain.schema import get_schema_registry
        schema = get_schema_registry().get("Mesh")
        req = {p.name for p in schema.required_properties()}
        assert "cell_count" in req

    def test_by_category_returns_props(self):
        from pyfds.domain.schema import get_schema_registry
        schema = get_schema_registry().get("Mesh")
        cats = schema.by_category()
        assert isinstance(cats, dict)
        assert len(cats) > 0

    def test_entity_names_includes_expected(self):
        from pyfds.domain.schema import get_schema_registry
        names = get_schema_registry().entity_names
        for expected in ("Mesh", "Obstruction", "Surface", "Device"):
            assert expected in names

    def test_register_custom_schema(self):
        from pyfds.domain.schema import (
            SchemaRegistry, EntitySchema, PropertyDescriptor, FieldType,
        )
        reg = SchemaRegistry()
        schema = EntitySchema(
            entity_class_name="Custom",
            display_name="Custom Entity",
            fds_namelist="CUST",
            category="Test",
            properties=[
                PropertyDescriptor(
                    name="value",
                    display_name="Value",
                    field_type=FieldType.FLOAT,
                ),
            ],
        )
        reg.register(schema)
        assert reg.get("Custom") is schema

    def test_for_entity(self):
        from pyfds.domain.schema import get_schema_registry
        from pyfds.domain.model import Mesh
        m = Mesh(name="M", cell_count=(5, 5, 5),
                 x_min=0, x_max=1, y_min=0, y_max=1, z_min=0, z_max=1)
        schema = get_schema_registry().for_entity(m)
        assert schema is not None
        assert schema.entity_class_name == "Mesh"

    def test_schema_to_dict(self):
        from pyfds.domain.schema import get_schema_registry
        d = get_schema_registry().get("Surface").to_dict()
        assert "entity_class_name" in d
        assert "properties" in d


class TestFieldType:
    def test_enum_values_exist(self):
        from pyfds.domain.schema import FieldType
        assert FieldType.FLOAT.name == "FLOAT"
        assert FieldType.VECTOR6.name == "VECTOR6"
        assert FieldType.ENTITY_REF.name == "ENTITY_REF"


# ===========================================================================
# EntityFactory
# ===========================================================================

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


# ===========================================================================
# New Commands: GroupCommand, DuplicateEntityCommand, SetHrrCommand, ScaleCommand
# ===========================================================================

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


# ===========================================================================
# FdsProject.filter() / query() / find_references()
# ===========================================================================

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


# ===========================================================================
# FdsApi integration
# ===========================================================================

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


class TestValidationAutoFix:
    def test_auto_fix_returns_report(self):
        from pyfds.api.controller import FdsApi
        from pyfds.domain.model import Mesh
        api = FdsApi()
        api.project.add_entity(
            Mesh(name="M", cell_count=(10, 10, 10),
                 x_min=0, x_max=1, y_min=0, y_max=1, z_min=0, z_max=1)
        )
        report = api.validation.auto_fix()
        assert hasattr(report, "results") and hasattr(report, "errors")

    def test_auto_fix_does_not_raise_on_clean_project(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        report = api.validation.auto_fix()
        assert report is not None


class TestExecutionRunAsync:
    def test_run_async_returns_future(self):
        from pyfds.api.controller import FdsApi
        import concurrent.futures
        api = FdsApi()
        future = api.execution.run_async(output_dir="tmp_async_test")
        assert isinstance(future, concurrent.futures.Future)
        # Don't wait for the actual FDS run — just confirm the Future was created


# ===========================================================================
# CLI autofix and schema subcommands
# ===========================================================================

class TestCLIAutofix:
    def test_autofix_missing_file(self, tmp_path):
        from pyfds.cli.main import main
        rc = main(["autofix", str(tmp_path / "nonexistent.fds")])
        assert rc == 1

    def test_autofix_invalid_project(self, tmp_path):
        bad = tmp_path / "bad.fds"
        bad.write_text("&RUBBISH /\n", encoding="utf-8")
        from pyfds.cli.main import main
        # Parser may raise or succeed; just confirm no unhandled exception
        try:
            rc = main(["autofix", str(bad)])
        except SystemExit as exc:
            rc = exc.code
        assert isinstance(rc, int)


class TestCLISchema:
    def test_schema_list(self, capsys):
        from pyfds.cli.main import main
        rc = main(["schema"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "Mesh" in captured.out

    def test_schema_entity(self, capsys):
        from pyfds.cli.main import main
        rc = main(["schema", "Mesh"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "MESH" in captured.out or "Mesh" in captured.out

    def test_schema_json(self, capsys):
        import json
        from pyfds.cli.main import main
        rc = main(["schema", "--json", "Surface"])
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "properties" in data

    def test_schema_unknown_entity(self):
        from pyfds.cli.main import main
        rc = main(["schema", "GhostEntity"])
        assert rc == 1


# ===========================================================================
# Export smoke test
# ===========================================================================

class TestExports:
    def test_selection_exports(self):
        from pyfds import SelectionManager, SelectionMode, SelectionSnapshot
        assert SelectionManager is not None
        assert SelectionMode is not None

    def test_viewport_exports(self):
        from pyfds import (
            ViewportCamera, ViewportState, ViewportController,
            TransformMode, CameraPreset, ProjectionMode, VisibilityFlags, SnapSettings,
        )
        assert ViewportController is not None

    def test_schema_exports(self):
        from pyfds import (
            PropertyDescriptor, FieldType, EntitySchema,
            SchemaRegistry, get_schema_registry,
        )
        assert get_schema_registry() is not None

    def test_factory_export(self):
        from pyfds import EntityFactory
        assert EntityFactory is not None

    def test_new_command_exports(self):
        from pyfds import (
            GroupCommand, DuplicateEntityCommand,
            SetHrrCommand, ScaleCommand,
        )
        assert GroupCommand is not None
