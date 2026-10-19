"""Unit tests — pyfds.io.fds_writer (FdsWriter)."""
from __future__ import annotations

import re
import pytest
from pyfds.io.fds_writer import FdsWriter
from pyfds.domain.model import (
    FdsProject, Mesh, Obstruction, Surface, Vent, Device,
    Ramp, Reaction, HvacNode, HvacDuct, Fan, Damper,
    Slice, BoundaryFile, IsoSurface, SimulationParams, DumpParams,
    Geom, Plot3D, MeshTransform, Zone, Control, Init, Mult,
)


@pytest.fixture
def writer():
    return FdsWriter()


@pytest.fixture
def simple_project():
    p = FdsProject(chid="test01", title="Test Project")
    p.params = SimulationParams(t_end=60.0)
    p.meshes.append(Mesh(name="mesh_01", cell_count=(20, 20, 10),
                         x_min=0, x_max=4, y_min=0, y_max=4, z_min=0, z_max=2))
    p.surfaces.append(Surface(name="fire", heat_release_rate=500.0, tau_q=-1.0))
    p.obstructions.append(
        Obstruction(name="floor", x_min=0, x_max=4, y_min=0, y_max=4,
                    z_min=0, z_max=0.1, surface_id="INERT")
    )
    p.vents.append(Vent(name="open", x_min=0, x_max=4, y_min=0, y_max=4,
                        z_min=2, z_max=2, surface_id="OPEN"))
    p.devices.append(Device(name="tc01", x=2.0, y=2.0, z=1.5, quantity="TEMPERATURE"))
    ramp = Ramp(name="q_ramp", times=[0.0, 30.0], values=[0.0, 1.0])
    p.ramps.append(ramp)
    return p


class TestFdsWriter:
    def test_write_creates_file(self, writer, simple_project, tmp_path):
        out = tmp_path / "out.fds"
        writer.write(simple_project, str(out))
        assert out.exists()

    def test_head_block_present(self, writer, simple_project, tmp_path):
        out = tmp_path / "out.fds"
        writer.write(simple_project, str(out))
        text = out.read_text()
        assert "&HEAD" in text
        assert "CHID='test01'" in text or 'CHID="test01"' in text

    def test_time_block_written(self, writer, simple_project, tmp_path):
        out = tmp_path / "out.fds"
        writer.write(simple_project, str(out))
        text = out.read_text()
        assert "&TIME" in text
        assert "T_END" in text

    def test_mesh_block_written(self, writer, simple_project, tmp_path):
        out = tmp_path / "out.fds"
        writer.write(simple_project, str(out))
        text = out.read_text()
        assert "&MESH" in text
        assert "mesh_01" in text

    def test_surf_block_written(self, writer, simple_project, tmp_path):
        out = tmp_path / "out.fds"
        writer.write(simple_project, str(out))
        text = out.read_text()
        assert "&SURF" in text
        assert "fire" in text
        assert "HRRPUA" in text

    def test_obst_block_written(self, writer, simple_project, tmp_path):
        out = tmp_path / "out.fds"
        writer.write(simple_project, str(out))
        text = out.read_text()
        assert "&OBST" in text
        assert "floor" in text

    def test_vent_block_written(self, writer, simple_project, tmp_path):
        out = tmp_path / "out.fds"
        writer.write(simple_project, str(out))
        text = out.read_text()
        assert "&VENT" in text

    def test_devc_block_written(self, writer, simple_project, tmp_path):
        out = tmp_path / "out.fds"
        writer.write(simple_project, str(out))
        text = out.read_text()
        assert "&DEVC" in text
        assert "TEMPERATURE" in text

    def test_ramp_expanded_to_pairs(self, writer, simple_project, tmp_path):
        out = tmp_path / "out.fds"
        writer.write(simple_project, str(out))
        text = out.read_text()
        ramp_blocks = re.findall(r"&RAMP", text)
        assert len(ramp_blocks) >= 2   # 2 pairs in q_ramp

    def test_tail_block_at_end(self, writer, simple_project, tmp_path):
        out = tmp_path / "out.fds"
        writer.write(simple_project, str(out))
        text = out.read_text()
        assert "&TAIL" in text
        assert text.rstrip().endswith("&TAIL /") or "&TAIL" in text[-100:]

    def test_no_uid_in_output(self, writer, simple_project, tmp_path):
        out = tmp_path / "out.fds"
        writer.write(simple_project, str(out))
        text = out.read_text()
        assert "_uid" not in text
        assert "PrivateAttr" not in text

    def test_write_returns_string(self, writer, simple_project):
        result = writer.to_string(simple_project)
        assert isinstance(result, str)
        assert "&HEAD" in result

    def test_generate_content_returns_string(self, writer, simple_project):
        result = writer.generate_content(simple_project)
        assert isinstance(result, str)
        assert "&HEAD" in result

    def test_write_empty_project(self, writer, tmp_path):
        p = FdsProject(chid="empty")
        out = tmp_path / "empty.fds"
        writer.write(p, str(out))
        text = out.read_text()
        assert "&HEAD" in text
        assert "&TAIL" in text

    def test_slice_written(self, writer, tmp_path):
        p = FdsProject(chid="slc")
        p.meshes.append(Mesh(name="m1", cell_count=(10, 10, 5),
                             x_min=0, x_max=2, y_min=0, y_max=2, z_min=0, z_max=1))
        p.slices.append(Slice(name="sl1", quantity="TEMPERATURE", plane="Z", position=0.5))
        out = tmp_path / "slc.fds"
        writer.write(p, str(out))
        text = out.read_text()
        assert "&SLCF" in text

    def test_boundary_written(self, writer, tmp_path):
        p = FdsProject(chid="bndf")
        p.meshes.append(Mesh(name="m1", cell_count=(10, 10, 5),
                             x_min=0, x_max=2, y_min=0, y_max=2, z_min=0, z_max=1))
        p.bndfs.append(BoundaryFile(name="b1", quantity="WALL TEMPERATURE"))
        out = tmp_path / "bndf.fds"
        writer.write(p, str(out))
        text = out.read_text()
        assert "&BNDF" in text

    def test_ijk_written_as_integers(self, writer, tmp_path):
        p = FdsProject(chid="ijk_test")
        p.meshes.append(Mesh(name="m", cell_count=(20, 20, 10),
                             x_min=0, x_max=4, y_min=0, y_max=4, z_min=0, z_max=2))
        out = tmp_path / "ijk.fds"
        writer.write(p, str(out))
        text = out.read_text()
        assert "20,20,10" in text or "20, 20, 10" in text

    def test_xb_written_as_floats(self, writer, tmp_path):
        p = FdsProject(chid="xb_test")
        p.meshes.append(Mesh(name="m", cell_count=(10, 10, 5),
                             x_min=0.0, x_max=4.0, y_min=0.0, y_max=4.0,
                             z_min=0.0, z_max=2.0))
        out = tmp_path / "xb.fds"
        writer.write(p, str(out))
        text = out.read_text()
        assert "XB=" in text

    def test_multiple_meshes_all_written(self, writer, tmp_path):
        p = FdsProject(chid="mm")
        p.meshes.append(Mesh(name="m1", cell_count=(10, 10, 5),
                             x_min=0, x_max=2, y_min=0, y_max=2, z_min=0, z_max=1))
        p.meshes.append(Mesh(name="m2", cell_count=(10, 10, 5),
                             x_min=2, x_max=4, y_min=0, y_max=2, z_min=0, z_max=1))
        out = tmp_path / "mm.fds"
        writer.write(p, str(out))
        text = out.read_text()
        assert text.count("&MESH") == 2


class TestPhase1Writer:
    """Tests for Phase 1 new entity writers."""

    def test_geom_written(self, writer, tmp_path):
        p = FdsProject(chid="geom_test")
        p.geoms.append(Geom(name="terrain", surf_id="INERT", is_terrain=True))
        text = writer.generate_content(p)
        assert "&GEOM" in text
        assert "IS_TERRAIN=.TRUE." in text

    def test_geom_with_verts_faces(self, writer, tmp_path):
        p = FdsProject(chid="geom_vf")
        p.geoms.append(Geom(
            name="box",
            surf_id="INERT",
            verts=[(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)],
            faces=[(0, 1, 2), (0, 1, 3)],
        ))
        text = writer.generate_content(p)
        assert "VERTS=" in text
        assert "FACES=" in text

    def test_plot3d_written(self, writer, tmp_path):
        p = FdsProject(chid="pl3d_test")
        p.plot3ds.append(Plot3D(name="temp", quantity="TEMPERATURE"))
        text = writer.generate_content(p)
        assert "&PL3D" in text
        assert "TEMPERATURE" in text

    def test_mesh_transform_trnx(self, writer, tmp_path):
        p = FdsProject(chid="trn_test")
        p.mesh_transforms.append(MeshTransform(name="t1", direction="X",
                                                mesh_number=1, cc=0.5, pc=0.3))
        text = writer.generate_content(p)
        assert "&TRNX" in text
        assert "CC=0.5" in text

    def test_mesh_transform_trny(self, writer, tmp_path):
        p = FdsProject(chid="trny_test")
        p.mesh_transforms.append(MeshTransform(name="t1", direction="Y",
                                                mesh_number=1, cc=1.0, pc=0.5))
        text = writer.generate_content(p)
        assert "&TRNY" in text

    def test_mesh_transform_trnz(self, writer, tmp_path):
        p = FdsProject(chid="trnz_test")
        p.mesh_transforms.append(MeshTransform(name="t1", direction="Z",
                                                mesh_number=1, cc=2.0, pc=0.8))
        text = writer.generate_content(p)
        assert "&TRNZ" in text

    def test_mult_dx0_written_when_nonzero(self, writer, tmp_path):
        p = FdsProject(chid="mult_test")
        p.mults.append(Mult(name="m1", dx=2.0, dx0=0.5, i_lower=0, i_upper=3))
        text = writer.generate_content(p)
        assert "DX0=0.5" in text

    def test_mult_dx0_omitted_when_zero(self, writer, tmp_path):
        p = FdsProject(chid="mult_zero")
        p.mults.append(Mult(name="m1", dx=2.0, dx0=0.0, i_lower=0, i_upper=3))
        text = writer.generate_content(p)
        assert "DX0" not in text

    def test_zone_leak_areas_written(self, writer, tmp_path):
        p = FdsProject(chid="zone_test")
        p.zones.append(Zone(name="z1", x_min=0, x_max=4, y_min=0, y_max=4,
                            z_min=0, z_max=3, leak_areas=[0.001, 0.002]))
        text = writer.generate_content(p)
        assert "LEAK_AREA(0)=0.001" in text and "LEAK_AREA(1)=0.002" in text

    def test_zone_no_leak_areas_omitted(self, writer, tmp_path):
        p = FdsProject(chid="zone_no_leak")
        p.zones.append(Zone(name="z1", x_min=0, x_max=4, y_min=0, y_max=4,
                            z_min=0, z_max=3))
        text = writer.generate_content(p)
        assert "LEAK_AREAS" not in text

    def test_reaction_fuel_radcal_id(self, writer, tmp_path):
        p = FdsProject(chid="reac_test")
        p.reactions.append(Reaction(name="fire", fuel="WOOD",
                                    heat_of_combustion=17700.0,
                                    fuel_radcal_id="PROPANE"))
        text = writer.generate_content(p)
        assert "FUEL_RADCAL_ID='PROPANE'" in text

    def test_device_quantity2(self, writer, tmp_path):
        p = FdsProject(chid="devc_q2")
        p.devices.append(Device(name="d1", x=1.0, y=1.0, z=0.5,
                                 quantity="RADIATIVE HEAT FLUX",
                                 quantity2="CONVECTIVE HEAT FLUX"))
        text = writer.generate_content(p)
        assert "QUANTITY2='CONVECTIVE HEAT FLUX'" in text

    def test_control_deadband(self, writer, tmp_path):
        p = FdsProject(chid="ctrl_test")
        p.controls.append(Control(name="thermo", function_type="DEADBAND",
                                   deadband=(18.0, 22.0)))
        text = writer.generate_content(p)
        assert "DEADBAND=18.0,22.0" in text

    def test_init_sphere_shape(self, writer, tmp_path):
        p = FdsProject(chid="init_test")
        p.inits.append(Init(name="sp", shape="SPHERE", radius=0.5,
                             xyz_center=(2.0, 2.0, 1.0)))
        text = writer.generate_content(p)
        assert "SHAPE='SPHERE'" in text
        assert "RADIUS=0.5" in text

    def test_mesh_cylindrical(self, writer, tmp_path):
        p = FdsProject(chid="cyl_test")
        p.meshes.append(Mesh(name="cyl", cell_count=(10, 10, 20),
                             x_min=0, x_max=1, y_min=0, y_max=1,
                             z_min=0, z_max=2, cylindrical=True))
        text = writer.generate_content(p)
        assert "CYLINDRICAL=.TRUE." in text

    def test_dump_plot3d_quantities(self, writer, tmp_path):
        p = FdsProject(chid="dump_q")
        p.dump.plot3d_quantities = ["TEMPERATURE", "U-VELOCITY", "V-VELOCITY"]
        text = writer.generate_content(p)
        assert "PLOT3D_QUANTITY" in text
