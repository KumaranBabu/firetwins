"""A1 — typed fields for formerly-preserved extras, control functions, SM3D, extras table, mesh order."""
from __future__ import annotations

import pytest

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.domain.control_functions import list_control_functions, problems
from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter


@pytest.fixture
def api():
    return FdsApi()


def _roundtrip(project, tmp_path):
    out = tmp_path / "a1.fds"
    FdsWriter().write(project, str(out))
    return out.read_text(), FdsParser().parse(str(out))


# ------------------------------------------------------------------ GEO-02
def test_obstruction_typed_flags_roundtrip_not_as_extras(api, tmp_path):
    api.obstructions.add_obstruction(
        xb=[0, 1, 0, 1, 0, 1], name="B", permit_hole=False, removable=True, bulk_density=450.0,
        mult_id="M", ctrl_id="C", devc_id="D", transparency=0.5, rgb=(1, 2, 3),
        surface_ids=["TOP", "SIDE", "BOT"])
    text, back = _roundtrip(api.project, tmp_path)
    assert "PERMIT_HOLE=.FALSE." in text and "REMOVABLE=.TRUE." in text and "SURF_IDS=" in text
    o = back.obstructions[0]
    assert (o.permit_hole, o.removable, o.bulk_density) == (False, True, 450.0)
    assert (o.mult_id, o.ctrl_id, o.devc_id, o.transparency) == ("M", "C", "D", 0.5)
    assert o.rgb == (1, 2, 3) and o.surface_ids == ["TOP", "SIDE", "BOT"]
    assert not o.fds_extra                      # nothing left over: all typed


def test_unspecified_flags_stay_unspecified(api, tmp_path):
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="B")
    text, back = _roundtrip(api.project, tmp_path)
    assert "PERMIT_HOLE" not in text and back.obstructions[0].permit_hole is None


def test_six_face_surfaces_use_surf_id6(api, tmp_path):
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="B",
                                     surface_ids=["A", "B", "C", "D", "E", "F"])
    text, back = _roundtrip(api.project, tmp_path)
    assert "SURF_ID6=" in text and "SURF_IDS=" not in text
    assert back.obstructions[0].surface_ids == ["A", "B", "C", "D", "E", "F"]


# ------------------------------------------------------------------ DEV-06
def test_heat_detector_and_sprinkler_props_roundtrip(api, tmp_path):
    api.props.add_heat_detector("HD", rti=80.0, activation_temperature=68.0)
    api.props.add_sprinkler("SP", rti=50.0, activation_temperature=74.0,
                            spray_angle=(10.0, 80.0), flow_rate=60.0, particle_velocity=10.0)
    _, back = _roundtrip(api.project, tmp_path)
    hd, sp = back.props
    assert (hd.rti, hd.activation_temperature) == (80.0, 68.0)
    assert sp.activation_temperature == 74.0 and sp.spray_angle == (10.0, 80.0)
    assert (sp.flow_rate, sp.particle_velocity) == (60.0, 10.0)
    assert not hd.fds_extra and not sp.fds_extra


# ------------------------------------------------------------------ CTL-02
def test_control_function_enumeration_and_guards(api):
    assert {"ANY", "ALL", "TIME_DELAY", "DEADBAND", "CUSTOM", "PID"} <= set(list_control_functions())
    api.devices.add_device("TEMPERATURE", [0, 0, 1], name="T1")
    c = api.controls.add_control("time_delay", ["T1"], name="DELAY", delay=5.0)
    assert c.function_type == "TIME_DELAY"
    with pytest.raises(ValueError, match="unknown FUNCTION_TYPE"):
        api.controls.add_control("NOPE", ["T1"])
    with pytest.raises(ValueError, match="exactly one INPUT_ID"):
        api.controls.add_control("TIME_DELAY", ["T1", "X"], delay=1.0)
    with pytest.raises(ValueError, match="needs N"):
        api.controls.add_control("ONLY", ["T1"])
    with pytest.raises(ValueError, match="already exists"):
        api.controls.add_control("ANY", ["T1"], name="DELAY")
    api.history.undo()
    assert api.controls.count() == 0 and api.devices.count() == 1


def test_validation_flags_unknown_function_from_imported_file(api, tmp_path):
    f = tmp_path / "c.fds"
    f.write_text("&HEAD CHID='c' /\n&MESH IJK=5,5,5, XB=0,1,0,1,0,1 /\n&TIME T_END=1 /\n"
                 "&CTRL ID='X', FUNCTION_TYPE='WIBBLE', INPUT_ID='T1' /\n&TAIL /\n")
    proj = FdsParser().parse(str(f))
    assert proj.controls[0].function_type == "WIBBLE"          # still loads
    from pyfds.validation import ValidationEngine
    rules = {r.rule for r in ValidationEngine.default().validate(proj).warnings}
    assert "ControlFunction" in rules


def test_problems_helper():
    from pyfds.domain.model import Control
    assert problems(Control(name="a", function_type="ANY", input_ids=["x"])) == []
    assert problems(Control(name="a", function_type="CUSTOM", input_ids=["x"]))     # needs ramp_id


# ------------------------------------------------------------------ OUT-02 / SM3D
def test_smoke3d_and_volume_slice(api, tmp_path):
    api.smoke3ds.add_smoke3d("DENSITY", "SOOT", name="S1")
    api.slices.add_volume_slice("TEMPERATURE", [0, 1, 0, 1, 0, 1], name="V1")
    with pytest.raises(ValueError):
        api.slices.add_volume_slice("TEMPERATURE", [0, 1])
    text, back = _roundtrip(api.project, tmp_path)
    assert "&SM3D QUANTITY='DENSITY', SPEC_ID='SOOT' /" in text
    assert back.smoke3ds[0].spec_id == "SOOT" and back.slices[0].xb == (0, 1, 0, 1, 0, 1)
    assert not back.texts                        # no longer kept as an opaque text block
    api.history.undo()
    assert api.smoke3ds.count() == 1 and api.slices.count() == 0


def test_sm3d_from_example_files_is_typed_now(tmp_path):
    f = tmp_path / "s.fds"
    f.write_text("&HEAD CHID='s' /\n&MESH IJK=5,5,5, XB=0,1,0,1,0,1 /\n&TIME T_END=1 /\n"
                 "&SM3D QUANTITY='DENSITY', SPEC_ID='SOOT' /\n&TAIL /\n")
    proj = FdsParser().parse(str(f))
    assert [(s.quantity, s.spec_id) for s in proj.smoke3ds] == [("DENSITY", "SOOT")]


# ------------------------------------------------------------------ MSH-02
def test_mesh_order_controls_write_order_and_is_one_undo_step(api, tmp_path):
    for n, x in (("A", 0), ("B", 1), ("C", 2)):
        api.meshes.add_mesh(ijk=(4, 4, 4), xb=(x, x + 1, 0, 1, 0, 1), name=n)
    api.meshes.set_order(["C", "A"])
    assert [(m.name, m.priority) for m in api.meshes.all()] == [("A", 2), ("B", 3), ("C", 1)]
    text, back = _roundtrip(api.project, tmp_path)
    assert [m.x_min for m in back.meshes] == [2.0, 0.0, 1.0]              # C, A, B
    api.history.undo()
    assert [m.priority for m in api.meshes.all()] == [None, None, None]
    with pytest.raises(ValueError):
        api.meshes.set_order(["A", "A"])
    with pytest.raises(ValueError):
        api.meshes.set_order(["ZZ"])


def test_mesh_alignment_test_reports_per_mesh(api):
    api.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1), name="FINE")
    api.meshes.add_mesh(ijk=(7, 7, 7), xb=(1, 2, 0, 1, 0, 1), name="ODD")
    api.meshes.add_mesh(ijk=(4, 4, 4), xb=(5, 6, 5, 6, 5, 6), name="FAR")
    assert api.meshes.alignment_test() == {"FINE": "Failed", "ODD": "Failed", "FAR": "Passed"}
    api.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 1, 2, 0, 1), name="OK")
    assert api.meshes.alignment_test()["OK"] == "Passed"


def test_mesh_description_and_color_survive(api, tmp_path):
    api.meshes.add_mesh(ijk=(4, 4, 4), xb=(0, 1, 0, 1, 0, 1), name="M", color="RED", description="hall")
    _, back = _roundtrip(api.project, tmp_path)
    assert back.meshes[0].color == "RED"
    assert api.meshes.get("M").description == "hall"


# ------------------------------------------------------------------ MSH-05 extras table
def test_extras_table_set_remove_undo_and_validation(api):
    api.meshes.add_mesh(ijk=(4, 4, 4), xb=(0, 1, 0, 1, 0, 1), name="M")
    api.meshes.set_extra("M", "n_threads", 4)
    api.meshes.set_extra("M", "PERIODIC_X", True)
    api.meshes.set_extra("M", "RGB(1:3)", [1, 2, 3])
    assert api.meshes.extras("M") == {"N_THREADS": "4", "PERIODIC_X": ".TRUE.", "RGB(1:3)": "1,2,3"}
    api.history.undo()
    assert "RGB(1:3)" not in api.meshes.extras("M")
    api.meshes.remove_extra("M", "n_threads")
    assert list(api.meshes.extras("M")) == ["PERIODIC_X"]
    with pytest.raises(ValueError, match="typed field"):
        api.meshes.set_extra("M", "COLOR", "'RED'")
    with pytest.raises(ValueError, match="not a valid FDS keyword"):
        api.meshes.set_extra("M", "bad key", 1)
    with pytest.raises(KeyError):
        api.meshes.remove_extra("M", "NOPE")


def test_extras_are_written_and_reread(api, tmp_path):
    api.meshes.add_mesh(ijk=(4, 4, 4), xb=(0, 1, 0, 1, 0, 1), name="M")
    api.meshes.set_extra("M", "N_THREADS", 2)
    text, back = _roundtrip(api.project, tmp_path)
    assert "N_THREADS=2" in text and back.meshes[0].fds_extra == {"N_THREADS": "2"}


# ------------------------------------------------------------------ agent tools
def test_agent_tools_for_a1(api):
    d = AgentToolDispatcher(api)
    api.meshes.add_mesh(ijk=(4, 4, 4), xb=(0, 1, 0, 1, 0, 1), name="M")
    d.call("add_control", {"function_type": "ANY", "input_ids": ["T1"], "name": "C1"})
    with pytest.raises(Exception):
        d.call("add_control", {"function_type": "BOGUS"})
    d.call("add_heat_detector_prop", {"name": "HD"})
    d.call("add_volume_slice", {"quantity": "TEMPERATURE", "xb": [0, 1, 0, 1, 0, 1], "name": "V"})
    d.call("add_smoke3d", {"name": "S"})
    d.call("set_entity_extra", {"entity": "M", "key": "N_THREADS", "value": 2})
    assert d.call("list_entity_extras", {"entity": "M"}) == {"N_THREADS": "2"}
    d.call("remove_entity_extra", {"entity": "M", "key": "N_THREADS"})
    assert d.call("mesh_alignment_test", {}) == {"M": "Passed"}
    d.call("set_mesh_order", {"names": ["M"]})
    assert [len(d.call(t, {})) for t in ("list_controls", "list_smoke3d")] == [1, 1]
    d.call("remove_control", {"name": "C1"})
    d.call("remove_smoke3d", {"name": "S"})
