"""
Integration tests — parser/writer round-trip fidelity.

For every fixture .fds file: parse → write → re-parse and verify
that the key structural properties are preserved.
"""
from __future__ import annotations

import glob
import os
import textwrap
from pathlib import Path

import pytest
from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
FDS_FILES = list(FIXTURES_DIR.glob("*.fds"))


@pytest.fixture
def parser():
    return FdsParser()


@pytest.fixture
def writer():
    return FdsWriter()


# ---------------------------------------------------------------------------
# Parametric round-trip over all fixture files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fds_file", FDS_FILES, ids=[f.name for f in FDS_FILES])
def test_parser_writer_roundtrip(fds_file, tmp_path, parser, writer):
    """
    Parse a fixture file → write it → re-parse the output.
    Verify: mesh count, CHID, and device count are stable.
    """
    # First pass
    project1 = parser.parse(str(fds_file))

    # Write
    out_path = tmp_path / "roundtrip.fds"
    writer.write(project1, str(out_path))
    assert out_path.exists(), "Writer did not create output file"

    # Second pass
    parser2 = FdsParser()
    project2 = parser2.parse(str(out_path))

    # Structural assertions
    assert project2.chid == project1.chid, "CHID mismatch after round-trip"
    assert len(project2.meshes) == len(project1.meshes), (
        f"Mesh count mismatch: {len(project1.meshes)} → {len(project2.meshes)}"
    )
    assert len(project2.devices) == len(project1.devices), (
        f"Device count mismatch: {len(project1.devices)} → {len(project2.devices)}"
    )
    assert len(project2.obstructions) == len(project1.obstructions), (
        f"Obstruction count mismatch"
    )


@pytest.mark.parametrize("fds_file", FDS_FILES, ids=[f.name for f in FDS_FILES])
def test_roundtrip_ramp_count(fds_file, tmp_path, parser, writer):
    """Ramp IDs (and count) survive the round-trip."""
    project1 = parser.parse(str(fds_file))
    out_path = tmp_path / "rt_ramp.fds"
    writer.write(project1, str(out_path))
    project2 = FdsParser().parse(str(out_path))
    assert len(project2.ramps) == len(project1.ramps)


@pytest.mark.parametrize("fds_file", FDS_FILES, ids=[f.name for f in FDS_FILES])
def test_roundtrip_surface_ids_preserved(fds_file, tmp_path, parser, writer):
    """Surface IDs survive the round-trip."""
    project1 = parser.parse(str(fds_file))
    out_path = tmp_path / "rt_surf.fds"
    writer.write(project1, str(out_path))
    project2 = FdsParser().parse(str(out_path))
    ids1 = {s.id for s in project1.surfaces}
    ids2 = {s.id for s in project2.surfaces}
    assert ids1 == ids2


@pytest.mark.parametrize("fds_file", FDS_FILES, ids=[f.name for f in FDS_FILES])
def test_roundtrip_time_params_preserved(fds_file, tmp_path, parser, writer):
    """T_END survives the round-trip."""
    project1 = parser.parse(str(fds_file))
    out_path = tmp_path / "rt_time.fds"
    writer.write(project1, str(out_path))
    project2 = FdsParser().parse(str(out_path))
    assert abs(project2.params.t_end - project1.params.t_end) < 1e-6


# ---------------------------------------------------------------------------
# Writer output content checks
# ---------------------------------------------------------------------------

class TestWriterOutputContent:
    def test_tail_always_last_namelist(self, parser, writer, tmp_path, simple_room_fds_path):
        project = parser.parse(simple_room_fds_path)
        out = tmp_path / "tail_test.fds"
        writer.write(project, str(out))
        text = out.read_text()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        # Find last non-empty, non-comment line
        last_nl_lines = [l for l in lines if l.startswith("&")]
        assert last_nl_lines[-1].startswith("&TAIL")

    def test_no_private_attrs_in_output(self, parser, writer, tmp_path, simple_room_fds_path):
        project = parser.parse(simple_room_fds_path)
        out = tmp_path / "priv.fds"
        writer.write(project, str(out))
        text = out.read_text()
        # Pydantic private attributes must not leak
        assert "_uid" not in text
        assert "PrivateAttr" not in text

    def test_head_first_meaningful_block(self, parser, writer, tmp_path, simple_room_fds_path):
        project = parser.parse(simple_room_fds_path)
        out = tmp_path / "head_first.fds"
        writer.write(project, str(out))
        text = out.read_text()
        head_pos = text.find("&HEAD")
        mesh_pos = text.find("&MESH")
        assert head_pos < mesh_pos

    def test_multi_mesh_all_written(self, parser, writer, tmp_path, multi_mesh_fds_path):
        project = parser.parse(multi_mesh_fds_path)
        out = tmp_path / "mm_rt.fds"
        writer.write(project, str(out))
        text = out.read_text()
        assert text.count("&MESH") == 2

    def test_ramp_pairs_expand(self, writer, tmp_path):
        from pyfds.domain.model import FdsProject, Mesh, Ramp
        p = FdsProject(chid="ramp_test")
        p.meshes.append(Mesh(id="m", ijk=(10, 10, 5), xb=(0, 2, 0, 2, 0, 1)))
        p.ramps.append(Ramp(id="r1", times=[0.0, 10.0, 20.0, 30.0], values=[0.0, 0.25, 0.75, 1.0]))
        out = tmp_path / "ramp_expand.fds"
        writer.write(p, str(out))
        text = out.read_text()
        # 4 T/F pairs → 4 &RAMP namelists
        assert text.count("&RAMP") == 4


# ---------------------------------------------------------------------------
# Serializer round-trip (.pyfds)
# ---------------------------------------------------------------------------

class TestSerializerRoundtrip:
    def test_pyfds_roundtrip(self, tmp_path, simple_room_fds_path):
        from pyfds.io.fds_parser import FdsParser
        from pyfds.io.serializer import Serializer

        project = FdsParser().parse(simple_room_fds_path)
        pyfds_path = str(tmp_path / "test.pyfds")
        Serializer().save(project, pyfds_path)
        assert Path(pyfds_path).exists()

        loaded = Serializer().load(pyfds_path)
        assert loaded.chid == project.chid
        assert len(loaded.meshes) == len(project.meshes)
        assert len(loaded.obstructions) == len(project.obstructions)

    def test_pyfds_is_zip(self, tmp_path, simple_room_fds_path):
        import zipfile
        from pyfds.io.fds_parser import FdsParser
        from pyfds.io.serializer import Serializer

        project = FdsParser().parse(simple_room_fds_path)
        pyfds_path = str(tmp_path / "test.pyfds")
        Serializer().save(project, pyfds_path)
        assert zipfile.is_zipfile(pyfds_path)
