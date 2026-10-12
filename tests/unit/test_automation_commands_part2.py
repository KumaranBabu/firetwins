"""Unit tests — pyfds.automation.commands (Command / CommandPipeline). (part 1 of 1). (part 2 of 3)."""


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

@pytest.fixture
def project():
    p = FdsProject()
    p.chid = "cmd_test"
    p.add_entity(_make_mesh())
    return p

@pytest.fixture
def pipeline(project):
    return CommandPipeline(project)

def _make_box_geom(name="box"):
    from pyfds.domain.geometry_tools import GeometryTools
    return GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name=name)


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
