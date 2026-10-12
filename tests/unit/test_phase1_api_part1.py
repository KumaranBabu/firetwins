"""Unit tests — Phase 1 API additions. (part 1 of 3)."""


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
