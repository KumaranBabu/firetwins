"""Regressions found by running the real FDS 6.10.1 (see tests/smoke/test_real_fds_smokeview.py):
things only a real solver rejects, checked here without needing one."""
from __future__ import annotations

import os
import stat
import sys

import pytest

from pyfds.api import FdsApi
from pyfds.domain.model import Material
from pyfds.execution.runner import SimulationRunner
from pyfds.io.fds_writer import FdsWriter


def _text(api):
    return FdsWriter().generate_content(api.project)


def test_inert_material_has_no_n_reactions():
    api = FdsApi()
    api.library.add_to_model("materials", "concrete")
    api.library.add_to_model("surfaces", "gypsum_wall_12mm")
    assert "N_REACTIONS" not in _text(api)               # FDS 6.10: N_REACTIONS=1 needs REFERENCE_TEMPERATURE or A, E


def test_reacting_material_keeps_n_reactions():
    api = FdsApi()
    api.materials.add(Material(name="WOOD", a=1e10, e=1.5e5, heat_of_reaction=400.0, n_reactions=1))
    assert "N_REACTIONS=1" in _text(api)
    api.materials.add_liquid_fuel("HEPTANE", "N-HEPTANE", 98.0, 365.0, 684.0, 2.2)
    assert _text(api).count("N_REACTIONS=1") == 2


@pytest.mark.skipif(sys.platform != "win32", reason="uses a .bat stand-in for the FDS binary")
def test_fds_error_with_exit_code_zero_is_a_failure(tmp_path):
    fake = tmp_path / "fds.bat"
    fake.write_text("@echo off\r\necho ERROR(101): Problem with MISC line. (CHID: x)\r\nexit /b 0\r\n")
    inp = tmp_path / "x.fds"
    inp.write_text("&HEAD CHID='x' /\n&TAIL /\n")
    runner = SimulationRunner(fds_binary=str(fake))
    rc = runner.run_blocking(str(inp))
    assert rc == -2 and runner.fds_error.startswith("ERROR(101)")


@pytest.mark.skipif(sys.platform != "win32", reason="uses a .bat stand-in for the FDS binary")
def test_clean_run_still_succeeds(tmp_path):
    fake = tmp_path / "fds.bat"
    fake.write_text("@echo off\r\necho STOP: FDS completed successfully (CHID: x)\r\nexit /b 0\r\n")
    inp = tmp_path / "x.fds"
    inp.write_text("&HEAD CHID='x' /\n&TAIL /\n")
    runner = SimulationRunner(fds_binary=str(fake))
    assert runner.run_blocking(str(inp)) == 0 and runner.fds_error is None


def test_object_straddling_two_meshes_is_not_reported_outside():
    api = FdsApi()
    api.meshes.add_mesh(ijk=(20, 20, 15), xb=(0, 3, 0, 3, 0, 2.25), name="M")
    api.meshes.split("M", "X", 1.5)
    api.obstructions.add_obstruction([1.2, 1.8, 1.2, 1.8, 0, 0.15], name="ACROSS")
    api.obstructions.add_obstruction([2.8, 3.4, 1.2, 1.8, 0, 0.15], name="STICKS_OUT")
    msgs = [r.message for r in api.validation.validate().results if r.rule == "ObstBounds"]
    assert len(msgs) == 1 and "STICKS_OUT" in msgs[0]


def test_particle_cloud_writes_its_particle_class_and_reads_it_back(tmp_path):
    from pyfds.io.fds_parser import FdsParser
    api = FdsApi()
    api.particles.add_particle_class(name="DROPS")
    api.inits.add_init([0, 1, 0, 1, 0, 1], part_id="DROPS", n_particles=50, name="CLOUD")
    text = _text(api)
    assert "PART_ID='DROPS'" in text
    f = tmp_path / "p.fds"
    f.write_text(text)
    assert FdsParser().parse(str(f)).inits[0].part_id == "DROPS"
