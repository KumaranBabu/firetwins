"""Unit tests — pyfds.automation.commands (Command / CommandPipeline). (part 1 of 1). (part 1 of 3)."""


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
