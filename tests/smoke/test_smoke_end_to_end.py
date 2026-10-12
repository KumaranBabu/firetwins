"""Smoke test: one realistic session that touches every feature area built so far, end to end.

Build a small building -> mesh it -> materials/surfaces/reaction from the library -> import CAD ->
copy/paste -> hide -> validate (gate) -> export FDS -> read it back -> save/load .pyfds -> scenario run
scripts -> results scene -> agent tools -> the GUI shell opens. Uses the files in ``tests/fixtures``.

It does NOT run FDS or Smokeview (neither is installed on the machine this was written on): the solver
step is covered by checking the generated input and run scripts instead.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter
from pyfds.io.serializer import Serializer

FIX = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    out = tmp_path_factory.mktemp("smoke")
    api = FdsApi()
    api.project.chid = "smoke"
    return api, out


def test_01_model_a_building(session):
    api, _ = session
    api.meshes.add_mesh(ijk=(60, 40, 25), xb=(0, 6, 0, 4, 0, 2.5), name="MAIN")
    api.library.add_to_model("surfaces", "gypsum_wall_25mm")
    room = api.geom.add_room([0.5, 5.5, 0.5, 3.5], 2.4, 0.2, floor_thickness=0.1, surf_id="GYPSUM_WALL_25MM",
                             openings=[{"side": "S", "centre": 3.0, "width": 0.9, "height": 2.0}])
    assert len(room["walls"]) == 5 and len(room["holes"]) == 1
    api.geom.add_stairs(1.0, 1.0, 0.0, "+X", 0.9, 4)
    api.geom.add_roof([0.5, 5.5, 0.5, 3.5], 2.4, 20, 0.1)
    assert len(api.obstructions.all()) > 20


def test_02_mesh_operations(session):
    api, _ = session
    n = len(api.meshes.all())
    api.meshes.split("MAIN", "X")
    assert len(api.meshes.all()) == n + 1
    api.history.undo()
    assert len(api.meshes.all()) == n
    api.meshes.open_boundaries()
    assert api.vents.all()
    assert api.meshes.project_stats()["total_cells"] == 60 * 40 * 25


def test_03_physics_and_library(session):
    api, _ = session
    api.surfaces.add_typed("burner", name="FIRE", heat_release_rate=1000.0, tau_q=-60)
    api.reactions.add_complex_reaction({"PROPANE": 1, "OXYGEN": 5}, {"CARBON DIOXIDE": 3, "WATER VAPOR": 4}, name="PROP",
                                       heat_of_combustion=46000.0)
    api.materials.add_liquid_fuel("HEPTANE", "N-HEPTANE", 98.0, 365.0, 684.0, 2.2)
    api.environment.set_ambient(temperature=22.0)
    api.library.add_to_model("sprinkler_links", "sprinkler_quick_68C")
    api.library.import_library(str(FIX / "user_library_sample.json"))
    assert api.library.add_to_model("materials", "test_foam").density == 30.0
    api.obstructions.add_obstruction([2, 3, 1.5, 2.5, 0, 0.5], surf_id="FIRE", name="BURNER")


def test_04_import_cad_and_clipboard(session):
    api, _ = session
    cube = api.geom.import_file(str(FIX / "cube_unit.obj"), translate=(4, 1, 0), name="CUBE")
    pyr = api.geom.import_file(str(FIX / "pyramid_3dface.dxf"), name="PYR")        # file says metres
    assert cube.bbox() == (4, 5, 1, 2, 0, 1) and pyr.bbox()[1] == 2
    before = len(api.obstructions.all())
    text = api.clipboard.copy([api.obstructions.get("BURNER")], include_dependencies=True)
    rep = api.clipboard.paste_fds_text(text, offset=(1.0, 0.0, 0.0))
    assert [e.name for e in rep["added"]] == ["BURNER_2"] and len(api.obstructions.all()) == before + 1
    api.view.hide(rep["added"])
    api.snapping.snap((1.0, 1.0, 1.0))


def test_05_validation_gate_and_export(session):
    api, out = session
    report = api.validation.validate()
    assert not report.errors, [r.message for r in report.errors][:5]
    api.validation.gate()                                                   # must not raise
    text = api.fds_format.to_string()
    for tag in ("&MESH", "&OBST", "&HOLE", "&REAC", "&SURF", "&MATL", "&VENT", "&PROP"):
        assert tag in text, tag
    assert "SPEC_ID_NU=" in text and "ID='BURNER_2'" in text                # hidden objects are still exported
    path = out / "smoke.fds"
    FdsWriter().write(api.project, str(path))
    back = FdsParser().parse(str(path))
    assert len(back.obstructions) == len(api.obstructions.all())
    assert back.reactions[0].spec_id_nu and back.surfaces


def test_06_save_load_pyfds_and_number_format(session):
    api, out = session
    api.fds_format.set_number_format(5, "auto")
    path = str(out / "smoke.pyfds")
    Serializer().save(api.project, path)
    loaded = FdsApi(Serializer().load(path))
    assert loaded.project.number_format == {"significant_digits": 5, "style": "auto"}
    assert [e.name for e in loaded.view.hidden()] == ["BURNER_2"]
    assert len(loaded.obstructions.all()) == len(api.obstructions.all())
    assert loaded.validation.validate().errors == []


def test_07_scenarios_and_run_scripts(session):
    api, out = session
    api.scenarios.create("baseline")
    api.scenarios.create("big_fire")
    written = api.scenarios.export_all(str(out / "scen"), num_processes=2)
    assert written
    assert (out / "scen" / "run_all.bat").exists() and (out / "scen" / "run_all.sh").exists()
    assert "mpiexec -n 2" in (out / "scen" / "run_all.sh").read_text()


def test_08_results_scene_from_fixture_slice(session):
    api, out = session
    import shutil
    shutil.copy(FIX / "slice_temperature_mesh1.sf", out / "smoke_1_1.sf")
    api.scene.open_results(str(out))
    (layer,) = api.scene.add_slices("TEMPERATURE")
    assert layer.n_frames == 3 and api.scene.playback.n_frames == 3
    api.scene.playback.seek_time(5.0)
    hit = api.scene.probe((0.5, 0.4, 0.3))        # the fixture slice is the plane y=0.4, x 0-1, z 0-0.5
    assert hit and hit[0]["units"] == "C"
    api.scene.add_clip("x", 0.5)
    frame = api.scene.frame(10.0)
    assert frame.items
    png = api.slice_view.render(layer.result, str(out / "t.png"), -1, "MAIN")
    assert open(png, "rb").read(4) == b"\x89PNG"
    api.scene.add_volume(np.random.rand(2, 60, 40, 25) * 1e-3, [0.0, 1.0], "MAIN", kind="smoke")
    assert api.scene.frame(1.0).of("smoke")[0].rgba.shape[-1] == 4


def test_09_imported_complex_fixture(session):
    api, _ = session
    proj = FdsParser().parse(str(FIX / "complex_reaction_propane.fds"))
    r = proj.reactions[0]
    assert r.spec_id_nu == ["PROPANE", "OXYGEN", "CARBON DIOXIDE", "WATER VAPOR"] and r.nu == [-1, -5, 3, 4]
    assert [l.material_id for l in proj.surfaces[0].layers] == ["GYP", "GYP"]
    other = FdsApi(proj)
    assert not any(x.rule == "ComplexReaction" for x in other.validation.validate().results)


def test_10_agent_drives_the_same_api(session):
    api, _ = session
    d = AgentToolDispatcher(api)
    n = len(api.obstructions.all())
    d.call("add_wall", {"path": [[0, 0], [1, 0]], "thickness": 0.2, "height": 2, "name": "AGW"})
    assert len(api.obstructions.all()) > n
    assert d.call("mesh_stats", {})["project"]["total_cells"] > 0
    d.call("set_ambient_conditions", {"temperature": 25.0})
    assert d.call("get_environment", {})["temperature"] == 25.0
    api.history.undo()
    assert api.environment.get()["temperature"] == 22.0


def test_11_whole_session_can_be_undone(session):
    api, _ = session
    while api.history.can_undo():
        api.history.undo()
    assert not api.obstructions.all() and not api.surfaces.all() and not api.reactions.all()


def test_12_gui_shell_opens_with_a_project(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pyfds.gui.main_window import MainWindow
    api = FdsApi()
    api.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1), name="M")
    api.hvac_nodes.add_node([0, 0, 0], name="N1")
    api.hvac_nodes.add_node([1, 0, 0], name="N2")
    api.hvac_ducts.add_duct("N1", "N2", name="D1")
    api.hvac_aircoils.add_aircoil("D1", 0.7, name="COIL")          # a type added after the GUI was written
    w = MainWindow(api)
    w.show()
    app.processEvents()
    assert w.windowTitle()
    w.close()
