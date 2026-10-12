"""Unit tests — pyfds.automation.commands (Command / CommandPipeline). (part 1 of 1). (part 3 of 3)."""


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
