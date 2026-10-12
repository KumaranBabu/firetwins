"""Unit tests — pyfds.io.serializer (Serializer save/load/roundtrip)."""
from __future__ import annotations

import json
import zipfile
import pytest

from pyfds.io.serializer import Serializer
from pyfds.domain.model import FdsProject, Mesh, Obstruction, Surface, Vent, Device, Ramp
from pyfds.core.exceptions import FdsSerializationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_project() -> FdsProject:
    p = FdsProject()
    p.chid = "test_case"
    p.title = "Test Fire"
    p.params.t_end = 120.0
    m = Mesh(name="Room", x_min=0, x_max=5, y_min=0, y_max=4,
             z_min=0, z_max=3, cell_count=(10, 8, 6))
    p.add_entity(m)
    p.add_entity(Surface(name="Burner", heat_release_rate=500.0))
    return p


# ---------------------------------------------------------------------------
# Serializer.save_string / load_string
# ---------------------------------------------------------------------------

class TestSerializerString:
    def test_save_string_is_valid_json(self):
        s = Serializer()
        proj = _simple_project()
        text = s.save_string(proj)
        data = json.loads(text)
        assert data["chid"] == "test_case"

    def test_save_string_contains_version(self):
        text = Serializer().save_string(_simple_project())
        assert json.loads(text)["version"] == "2.0"

    def test_roundtrip_via_string(self):
        orig = _simple_project()
        ser = Serializer()
        text = ser.save_string(orig)
        restored = ser.load_string(text)
        assert restored.chid == orig.chid
        assert restored.title == orig.title

    def test_roundtrip_t_end(self):
        orig = _simple_project()
        orig.params.t_end = 300.0
        text = Serializer().save_string(orig)
        restored = Serializer().load_string(text)
        assert restored.params.t_end == 300.0

    def test_roundtrip_mesh_count(self):
        orig = _simple_project()
        text = Serializer().save_string(orig)
        restored = Serializer().load_string(text)
        assert len(restored.meshes) == len(orig.meshes)

    def test_roundtrip_surface_name(self):
        orig = _simple_project()
        text = Serializer().save_string(orig)
        restored = Serializer().load_string(text)
        names = [s.name for s in restored.surfaces]
        assert "Burner" in names

    def test_load_string_bad_json_raises(self):
        with pytest.raises(FdsSerializationError):
            Serializer().load_string("not json {{}")

    def test_load_string_unknown_version_still_loads(self):
        orig = _simple_project()
        text = Serializer().save_string(orig)
        data = json.loads(text)
        data["version"] = "9.9"
        restored = Serializer().load_string(json.dumps(data))
        assert restored.chid == orig.chid


# ---------------------------------------------------------------------------
# Serializer.save / load (file I/O)
# ---------------------------------------------------------------------------

class TestSerializerFile:
    def test_save_creates_zip_file(self, tmp_path):
        path = str(tmp_path / "case.pyfds")
        Serializer().save(_simple_project(), path)
        assert zipfile.is_zipfile(path)

    def test_saved_zip_contains_project_json(self, tmp_path):
        path = str(tmp_path / "case.pyfds")
        Serializer().save(_simple_project(), path)
        with zipfile.ZipFile(path) as zf:
            assert "project.json" in zf.namelist()

    def test_save_and_load_roundtrip(self, tmp_path):
        path = str(tmp_path / "case.pyfds")
        orig = _simple_project()
        Serializer().save(orig, path)
        restored = Serializer().load(path)
        assert restored.chid == orig.chid

    def test_load_bad_path_raises(self):
        with pytest.raises(FdsSerializationError):
            Serializer().load("/nonexistent/path/file.pyfds")

    def test_save_creates_parent_dirs(self, tmp_path):
        path = str(tmp_path / "sub" / "dir" / "case.pyfds")
        Serializer().save(_simple_project(), path)
        assert zipfile.is_zipfile(path)


# ---------------------------------------------------------------------------
# Entity round-trips
# ---------------------------------------------------------------------------

class TestEntityRoundtrips:
    def test_ramp_roundtrip(self):
        orig = FdsProject()
        orig.chid = "ramp_test"
        orig.add_entity(Ramp(name="HRR_RAMP", times=[0.0, 10.0, 60.0],
                              values=[0.0, 0.5, 1.0]))
        text = Serializer().save_string(orig)
        restored = Serializer().load_string(text)
        assert len(restored.ramps) == 1
        assert restored.ramps[0].name == "HRR_RAMP"

    def test_device_roundtrip(self):
        orig = FdsProject()
        orig.chid = "devc_test"
        orig.add_entity(Device(name="TC_01", quantity="TEMPERATURE",
                                x=1.0, y=1.0, z=2.0))
        text = Serializer().save_string(orig)
        restored = Serializer().load_string(text)
        assert len(restored.devices) == 1
        assert restored.devices[0].quantity == "TEMPERATURE"

    def test_obstruction_roundtrip(self):
        orig = FdsProject()
        orig.chid = "obst_test"
        orig.add_entity(Obstruction(name="Wall",
                                     x_min=0, x_max=5, y_min=0, y_max=0.1,
                                     z_min=0, z_max=3, surface_id="INERT"))
        text = Serializer().save_string(orig)
        restored = Serializer().load_string(text)
        assert len(restored.obstructions) == 1

    def test_vent_roundtrip(self):
        orig = FdsProject()
        orig.chid = "vent_test"
        orig.add_entity(Vent(name="OPEN_TOP",
                              x_min=0, x_max=5, y_min=0, y_max=4,
                              z_min=3, z_max=3, surface_id="OPEN"))
        text = Serializer().save_string(orig)
        restored = Serializer().load_string(text)
        assert len(restored.vents) == 1

    def test_multi_mesh_roundtrip(self):
        orig = FdsProject()
        orig.chid = "multi"
        for i in range(3):
            orig.add_entity(Mesh(name=f"M{i}", x_min=i, x_max=i+1,
                                  y_min=0, y_max=1, z_min=0, z_max=1,
                                  cell_count=(4, 4, 4)))
        text = Serializer().save_string(orig)
        restored = Serializer().load_string(text)
        assert len(restored.meshes) == 3

    def test_empty_project_roundtrip(self):
        orig = FdsProject()
        orig.chid = "empty"
        text = Serializer().save_string(orig)
        restored = Serializer().load_string(text)
        assert restored.chid == "empty"
        assert len(restored.meshes) == 0
