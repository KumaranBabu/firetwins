"""Unit tests — pyfds.automation.commands (Command / CommandPipeline)."""
from __future__ import annotations

import pytest
from pyfds.domain.model import Device, FdsProject, Geom, HvacNode, Mesh, Obstruction, Surface
from pyfds.automation.commands import (
    CommandResult, CommandPipeline,
    AddEntityCommand, RemoveEntityCommand, ModifyPropertyCommand,
    MoveObstCommand, MoveHvacNodeCommand, SetTimingCommand,
    TranslateGeomCommand, ScaleGeomCommand, MirrorGeomCommand,
    RotateGeomCommand, TranslatePointCommand,
)


def _make_mesh(name="m1", nx=10, ny=10, nz=5):
    return Mesh(name=name, cell_count=(nx, ny, nz),
                x_min=0, x_max=2, y_min=0, y_max=2, z_min=0, z_max=1)


def _make_obst(name="obst", x_min=1.0, x_max=2.0):
    return Obstruction(name=name,
                       x_min=x_min, x_max=x_max,
                       y_min=0.0, y_max=1.0,
                       z_min=0.0, z_max=0.5,
                       surface_id="INERT")


@pytest.fixture
def project():
    p = FdsProject()
    p.chid = "cmd_test"
    p.add_entity(_make_mesh())
    return p


@pytest.fixture
def pipeline(project):
    return CommandPipeline(project)


# ---------------------------------------------------------------------------
# CommandResult
# ---------------------------------------------------------------------------

class TestCommandResult:
    def test_ok(self):
        r = CommandResult.ok("done", payload=42)
        assert r.success is True
        assert r.message == "done"
        assert r.payload == 42

    def test_fail(self):
        r = CommandResult.fail("oops")
        assert r.success is False
        assert r.message == "oops"

    def test_default_success_true(self):
        r = CommandResult()
        assert r.success is True


# ---------------------------------------------------------------------------
# AddEntityCommand
# ---------------------------------------------------------------------------

class TestAddEntityCommand:
    def test_add_mesh_to_project(self, project, pipeline):
        new_mesh = _make_mesh("m2")
        result = pipeline.execute(AddEntityCommand(project, new_mesh))
        assert result.success
        assert len(project.meshes) == 2

    def test_undo_add_removes_entity(self, project, pipeline):
        new_mesh = _make_mesh("m2")
        pipeline.execute(AddEntityCommand(project, new_mesh))
        pipeline.undo()
        assert len(project.meshes) == 1

    def test_redo_after_undo(self, project, pipeline):
        new_mesh = _make_mesh("m2")
        pipeline.execute(AddEntityCommand(project, new_mesh))
        pipeline.undo()
        pipeline.redo()
        assert len(project.meshes) == 2

    def test_add_surface(self, project, pipeline):
        s = Surface(name="fire", heat_release_rate=500.0)
        result = pipeline.execute(AddEntityCommand(project, s))
        assert result.success
        assert len(project.surfaces) == 1


# ---------------------------------------------------------------------------
# RemoveEntityCommand
# ---------------------------------------------------------------------------

class TestRemoveEntityCommand:
    def test_remove_existing_entity(self, project, pipeline):
        m1 = project.meshes[0]
        result = pipeline.execute(RemoveEntityCommand(project, m1))
        assert result.success
        assert len(project.meshes) == 0

    def test_undo_remove_restores_entity(self, project, pipeline):
        m1 = project.meshes[0]
        pipeline.execute(RemoveEntityCommand(project, m1))
        pipeline.undo()
        assert len(project.meshes) == 1


# ---------------------------------------------------------------------------
# ModifyPropertyCommand
# ---------------------------------------------------------------------------

class TestModifyPropertyCommand:
    def test_modify_simple_attr(self, project, pipeline):
        m = project.meshes[0]
        result = pipeline.execute(ModifyPropertyCommand(m, "name", "new_mesh_name"))
        assert result.success
        assert m.name == "new_mesh_name"

    def test_undo_restore_old_value(self, project, pipeline):
        m = project.meshes[0]
        original_name = m.name
        pipeline.execute(ModifyPropertyCommand(m, "name", "changed"))
        pipeline.undo()
        assert m.name == original_name

    def test_modify_dot_path(self, project, pipeline):
        """Dot-path: 'params.t_end' should set project.params.t_end."""
        result = pipeline.execute(ModifyPropertyCommand(project, "params.t_end", 300.0))
        assert result.success
        assert project.params.t_end == 300.0

    def test_undo_dot_path(self, project, pipeline):
        original = project.params.t_end
        pipeline.execute(ModifyPropertyCommand(project, "params.t_end", 300.0))
        pipeline.undo()
        assert project.params.t_end == original

    def test_modify_nested_misc_param(self, project, pipeline):
        result = pipeline.execute(ModifyPropertyCommand(project, "misc.tmpa", 25.0))
        assert result.success
        assert project.misc.tmpa == 25.0


# ---------------------------------------------------------------------------
# MoveObstCommand
# ---------------------------------------------------------------------------

class TestMoveObstCommand:
    def test_move_translates_coords(self, project, pipeline):
        obst = _make_obst("block", x_min=1.0, x_max=2.0)
        project.add_entity(obst)
        result = pipeline.execute(MoveObstCommand(obst, dx=0.5))
        assert result.success
        assert abs(obst.x_min - 1.5) < 1e-9
        assert abs(obst.x_max - 2.5) < 1e-9

    def test_move_undo_restores(self, project, pipeline):
        obst = _make_obst("block2", x_min=1.0, x_max=2.0)
        project.add_entity(obst)
        pipeline.execute(MoveObstCommand(obst, dx=1.0))
        pipeline.undo()
        assert abs(obst.x_min - 1.0) < 1e-9
        assert abs(obst.x_max - 2.0) < 1e-9

    def test_move_y_axis(self, project, pipeline):
        obst = _make_obst("block3")
        project.add_entity(obst)
        orig_y_min = obst.y_min
        pipeline.execute(MoveObstCommand(obst, dy=0.5))
        assert abs(obst.y_min - (orig_y_min + 0.5)) < 1e-9

    def test_move_z_axis(self, project, pipeline):
        obst = _make_obst("block4")
        project.add_entity(obst)
        orig_z_min = obst.z_min
        pipeline.execute(MoveObstCommand(obst, dz=0.25))
        assert abs(obst.z_min - (orig_z_min + 0.25)) < 1e-9


class TestMoveHvacNodeCommand:
    def test_move_translates_xy(self, project, pipeline):
        node = HvacNode(name="n1", x=1.0, y=2.0, z=0.0)
        project.add_entity(node)
        result = pipeline.execute(MoveHvacNodeCommand(node, dx=0.5, dy=-1.0))
        assert result.success
        assert abs(node.x - 1.5) < 1e-9
        assert abs(node.y - 1.0) < 1e-9

    def test_move_leaves_z_untouched(self, project, pipeline):
        node = HvacNode(name="n2", x=0.0, y=0.0, z=3.5)
        project.add_entity(node)
        pipeline.execute(MoveHvacNodeCommand(node, dx=10.0, dy=10.0))
        assert abs(node.z - 3.5) < 1e-9

    def test_move_undo_restores(self, project, pipeline):
        node = HvacNode(name="n3", x=0.0, y=0.0, z=0.0)
        project.add_entity(node)
        pipeline.execute(MoveHvacNodeCommand(node, dx=5.0, dy=7.0))
        pipeline.undo()
        assert abs(node.x - 0.0) < 1e-9
        assert abs(node.y - 0.0) < 1e-9


# ---------------------------------------------------------------------------
# SetTimingCommand
# ---------------------------------------------------------------------------

class TestSetTimingCommand:
    def test_set_t_end(self, project, pipeline):
        result = pipeline.execute(SetTimingCommand(project, t_end=120.0))
        assert result.success
        assert project.params.t_end == 120.0

    def test_undo_set_timing(self, project, pipeline):
        original_t_end = project.params.t_end
        pipeline.execute(SetTimingCommand(project, t_end=999.0))
        pipeline.undo()
        assert project.params.t_end == original_t_end

    def test_set_t_begin_and_end(self, project, pipeline):
        pipeline.execute(SetTimingCommand(project, t_end=180.0, t_begin=10.0))
        assert project.params.t_end == 180.0
        assert project.params.t_begin == 10.0


# ---------------------------------------------------------------------------
# CommandPipeline
# ---------------------------------------------------------------------------

class TestCommandPipeline:
    def test_can_undo_after_execute(self, project, pipeline):
        assert not pipeline.can_undo()
        pipeline.execute(AddEntityCommand(project, _make_mesh("x")))
        assert pipeline.can_undo()

    def test_cannot_redo_before_undo(self, project, pipeline):
        pipeline.execute(AddEntityCommand(project, _make_mesh("x")))
        assert not pipeline.can_redo()

    def test_can_redo_after_undo(self, project, pipeline):
        pipeline.execute(AddEntityCommand(project, _make_mesh("x")))
        pipeline.undo()
        assert pipeline.can_redo()

    def test_undo_on_empty_stack_returns_none(self, pipeline):
        result = pipeline.undo()
        assert result is None

    def test_redo_on_empty_stack_returns_none(self, pipeline):
        result = pipeline.redo()
        assert result is None

    def test_multiple_undo_redo(self, project, pipeline):
        pipeline.execute(AddEntityCommand(project, _make_mesh("m2")))
        pipeline.execute(AddEntityCommand(project, _make_mesh("m3")))
        assert len(project.meshes) == 3
        pipeline.undo()
        assert len(project.meshes) == 2
        pipeline.undo()
        assert len(project.meshes) == 1
        pipeline.redo()
        assert len(project.meshes) == 2

    def test_clear_history(self, project, pipeline):
        pipeline.execute(AddEntityCommand(project, _make_mesh("x")))
        pipeline.clear_history()
        assert not pipeline.can_undo()
        assert not pipeline.can_redo()

    def test_history_labels(self, project, pipeline):
        pipeline.execute(AddEntityCommand(project, _make_mesh("x")))
        labels = pipeline.history_labels()
        assert len(labels) >= 1
        assert isinstance(labels[0], str)

    def test_events_emitted_on_execute(self, project):
        from pyfds.core.events import EventType, get_global_bus
        received = []
        get_global_bus().subscribe(EventType.COMMAND_EXECUTED, received.append)
        pipe = CommandPipeline(project)
        pipe.execute(AddEntityCommand(project, _make_mesh("ev_mesh")))
        assert len(received) == 1

    def test_events_emitted_on_undo(self, project):
        from pyfds.core.events import EventType, get_global_bus
        received = []
        get_global_bus().subscribe(EventType.UNDO_PERFORMED, received.append)
        pipe = CommandPipeline(project)
        pipe.execute(AddEntityCommand(project, _make_mesh("ev_mesh2")))
        pipe.undo()
        assert len(received) == 1

    def test_max_history_limit(self, project):
        pipe = CommandPipeline(project, max_history=3)
        for i in range(5):
            pipe.execute(ModifyPropertyCommand(project, "chid", f"case_{i}"))
        labels = pipe.history_labels()
        assert len(labels) <= 3

    def test_redo_stack_cleared_on_new_execute(self, project, pipeline):
        pipeline.execute(AddEntityCommand(project, _make_mesh("r1")))
        pipeline.undo()
        assert pipeline.can_redo()
        pipeline.execute(AddEntityCommand(project, _make_mesh("r2")))
        assert not pipeline.can_redo()  # New command clears redo

    def test_failed_command_not_pushed_to_stack(self, project, pipeline):
        """A command that returns success=False should not be added to history."""
        class AlwaysFailCmd:
            description = "fail"
            def execute(self): return CommandResult.fail("intentional")
            def undo(self): return CommandResult.ok()

        pipeline.execute(AlwaysFailCmd())
        assert not pipeline.can_undo()


# ---------------------------------------------------------------------------
# Geom / point transform commands
# ---------------------------------------------------------------------------

def _make_box_geom(name="box"):
    from pyfds.domain.geometry_tools import GeometryTools
    return GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name=name)


class TestTranslateGeomCommand:
    def test_translate_shifts_every_vertex(self, project, pipeline):
        geom = _make_box_geom("g1")
        project.add_entity(geom)
        before = list(geom.verts)
        pipeline.execute(TranslateGeomCommand(geom, dx=1.0, dy=2.0, dz=3.0))
        for (x0, y0, z0), (x1, y1, z1) in zip(before, geom.verts):
            assert abs(x1 - (x0 + 1.0)) < 1e-9
            assert abs(y1 - (y0 + 2.0)) < 1e-9
            assert abs(z1 - (z0 + 3.0)) < 1e-9

    def test_translate_undo_restores(self, project, pipeline):
        geom = _make_box_geom("g2")
        project.add_entity(geom)
        before = list(geom.verts)
        pipeline.execute(TranslateGeomCommand(geom, dx=5.0))
        pipeline.undo()
        assert geom.verts == before


class TestScaleGeomCommand:
    def test_scale_doubles_extent_about_centroid(self, project, pipeline):
        geom = _make_box_geom("g3")
        project.add_entity(geom)
        pipeline.execute(ScaleGeomCommand(geom, factor=2.0))
        xs = [v[0] for v in geom.verts]
        assert abs(min(xs) - (-1.0)) < 1e-9
        assert abs(max(xs) - 3.0) < 1e-9

    def test_scale_undo_restores(self, project, pipeline):
        geom = _make_box_geom("g4")
        project.add_entity(geom)
        before = list(geom.verts)
        pipeline.execute(ScaleGeomCommand(geom, factor=3.0))
        pipeline.undo()
        assert geom.verts == before


class TestMirrorGeomCommand:
    def test_mirror_reflects_across_x_axis(self, project, pipeline):
        geom = _make_box_geom("g5")
        project.add_entity(geom)
        pipeline.execute(MirrorGeomCommand(geom, axis=0))
        xs = sorted(v[0] for v in geom.verts)
        assert abs(min(xs) - 0.0) < 1e-9
        assert abs(max(xs) - 2.0) < 1e-9

    def test_mirror_reverses_face_winding(self, project, pipeline):
        geom = _make_box_geom("g6")
        project.add_entity(geom)
        before_faces = list(geom.faces)
        pipeline.execute(MirrorGeomCommand(geom, axis=0))
        for (a0, b0, c0), (a1, b1, c1) in zip(before_faces, geom.faces):
            assert (a1, b1, c1) == (a0, c0, b0)

    def test_mirror_undo_restores_verts_and_faces(self, project, pipeline):
        geom = _make_box_geom("g7")
        project.add_entity(geom)
        before_verts = list(geom.verts)
        before_faces = list(geom.faces)
        pipeline.execute(MirrorGeomCommand(geom, axis=1))
        pipeline.undo()
        assert geom.verts == before_verts
        assert geom.faces == before_faces

    def test_mirror_rejects_invalid_axis(self, project, pipeline):
        geom = _make_box_geom("g8")
        project.add_entity(geom)
        with pytest.raises(ValueError):
            MirrorGeomCommand(geom, axis=3)


class TestRotateGeomCommand:
    def test_rotate_180_about_z_negates_xy_offset(self, project, pipeline):
        geom = _make_box_geom("g9")
        project.add_entity(geom)
        before = list(geom.verts)
        pipeline.execute(RotateGeomCommand(geom, degrees=180.0))
        cx, cy = 1.0, 1.0  # box centroid in XY
        for (x0, y0, z0), (x1, y1, z1) in zip(before, geom.verts):
            assert abs(x1 - (2 * cx - x0)) < 1e-6
            assert abs(y1 - (2 * cy - y0)) < 1e-6
            assert abs(z1 - z0) < 1e-9  # Z untouched

    def test_rotate_undo_restores(self, project, pipeline):
        geom = _make_box_geom("g10")
        project.add_entity(geom)
        before = list(geom.verts)
        pipeline.execute(RotateGeomCommand(geom, degrees=37.0))
        pipeline.undo()
        assert geom.verts == before

    def test_rotate_accepts_arbitrary_angle(self, project, pipeline):
        # Unlike the XB RotateCommand, a mesh has no axis-alignment to
        # preserve, so non-90-multiple angles must be accepted.
        geom = _make_box_geom("g11")
        project.add_entity(geom)
        result = pipeline.execute(RotateGeomCommand(geom, degrees=17.5))
        assert result.success


class TestTranslatePointCommand:
    def test_translate_shifts_xyz(self, project, pipeline):
        device = Device(name="d1", x=1.0, y=2.0, z=3.0)
        project.add_entity(device)
        pipeline.execute(TranslatePointCommand(device, dx=1.0, dy=-1.0, dz=0.5))
        assert abs(device.x - 2.0) < 1e-9
        assert abs(device.y - 1.0) < 1e-9
        assert abs(device.z - 3.5) < 1e-9

    def test_translate_undo_restores(self, project, pipeline):
        device = Device(name="d2", x=0.0, y=0.0, z=0.0)
        project.add_entity(device)
        pipeline.execute(TranslatePointCommand(device, dx=5.0, dy=5.0, dz=5.0))
        pipeline.undo()
        assert (device.x, device.y, device.z) == (0.0, 0.0, 0.0)

    def test_works_with_hvac_node(self, project, pipeline):
        node = HvacNode(name="n1", x=0.0, y=0.0, z=0.0)
        project.add_entity(node)
        pipeline.execute(TranslatePointCommand(node, dx=3.0, dy=4.0))
        assert (node.x, node.y) == (3.0, 4.0)

    def test_keeps_xyz_field_in_sync_for_devices(self, project, pipeline):
        # Device.add_device() populates .xyz, not .x/.y/.z (the FDS writer
        # reads .x/.y/.z for Device though) — the command must move both
        # representations together so the shift takes effect regardless of
        # which one is authoritative for a given entity type.
        device = Device(name="d3", xyz=(1.0, 2.0, 3.0))
        project.add_entity(device)
        pipeline.execute(TranslatePointCommand(device, dx=1.0, dy=1.0, dz=1.0))
        assert device.xyz == (2.0, 3.0, 4.0)
        pipeline.undo()
        assert device.xyz == (1.0, 2.0, 3.0)
