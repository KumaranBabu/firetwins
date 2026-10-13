"""B4 (part 2) - HVAC in FDS 6.10 syntax, fan curves, filters, jet fans, fire library and pool fires,
pyrolysis fitting and by-products, activation/HRR summaries, egress outputs."""
from __future__ import annotations

import math
import shutil
from pathlib import Path

import pytest

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.api.hvac_extras import jet_fan_flow, jet_fan_thrust, quadratic_curve
from pyfds.domain import pyrolysis_kinetics as pk
from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter
from pyfds.io.serializer import Serializer


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh(ijk=(40, 20, 20), xb=(0, 8, 0, 4, 0, 4), name="M")
    return a


def _roundtrip(api, tmp_path):
    f = tmp_path / "m.fds"
    FdsWriter().write(api.project, str(f))
    return f.read_text(), FdsParser().parse(str(f))


def _rules(api, name=None):
    return {(r.rule, r.entity_name) for r in api.validation.validate().results if name in (None, r.rule)}


# -- HVAC is written and read as &HVAC TYPE_ID=... --------------------------------------------------
def _duct_system(api):
    api.hvac_nodes.add_node([1, 1, 3], name="A")
    api.hvac_nodes.add_node([2, 1, 3], name="B")
    api.hvac_nodes.add_node([3, 1, 3], name="C")
    api.hvac_ducts.add_duct("A", "B", area=0.2, name="D1")
    api.hvac_ducts.add_duct("B", "C", area=0.2, name="D2")


def test_network_written_in_fds6_form_and_read_back(api, tmp_path):
    _duct_system(api)
    api.fans.add_fan("D1", volume_flow_rate=1.5, name="FAN1")
    api.hvac_filters.add_filter("D2", node_id="B", efficiency=0.99, spec_id="SOOT", loading=0.0, loss=100.0,
                                clean_loss=2.0, name="FLT")
    text, back = _roundtrip(api, tmp_path)
    assert "&HVAC TYPE_ID='NODE', ID='B', DUCT_ID='D1','D2', XYZ=2.0,1.0,3.0, FILTER_ID='FLT' /" in text
    assert "FAN_ID='FAN1'" in text and "TYPE_ID='FAN', ID='FAN1', VOLUME_FLOW=1.5" in text
    assert not any(ln.startswith(("&NODE", "&DUCT", "&FAN", "&FILTER")) for ln in text.splitlines())
    assert {n.name for n in back.hvac_nodes} == {"A", "B", "C"}
    assert back.fans[0].duct_id == "D1" and back.fans[0].volume_flow_rate == 1.5
    f = back.hvac_filters[0]
    assert (f.node_id, f.spec_id, f.clean_loss, f.loss) == ("B", "SOOT", 2.0, 100.0)


def test_shared_fan_class_is_copied_per_duct_on_import(tmp_path):
    f = tmp_path / "x.fds"
    f.write_text("&HEAD CHID='x'/\n&HVAC TYPE_ID='NODE',ID='A',XYZ=0,0,0,DUCT_ID='D1'/\n"
                 "&HVAC TYPE_ID='NODE',ID='B',XYZ=1,0,0,DUCT_ID='D1','D2'/\n&HVAC TYPE_ID='NODE',ID='C',XYZ=2,0,0,DUCT_ID='D2'/\n"
                 "&HVAC TYPE_ID='DUCT',ID='D1',NODE_ID='A','B',AREA=0.1,FAN_ID='F'/\n"
                 "&HVAC TYPE_ID='DUCT',ID='D2',NODE_ID='B','C',AREA=0.1,FAN_ID='F',DAMPER=F/\n"
                 "&HVAC TYPE_ID='FAN',ID='F',MAX_FLOW=1.,MAX_PRESSURE=500./\n&TAIL/\n")
    p = FdsParser().parse(str(f))
    assert sorted((x.name, x.duct_id) for x in p.fans) == [("F", "D1"), ("F_D2", "D2")]
    text = FdsWriter().generate_content(p)
    assert "FAN_ID='F_D2'" in text and text.count("TYPE_ID='FAN'") == 2


def test_damper_and_aircoil_round_trip(api, tmp_path):
    _duct_system(api)
    api.devices.add_time_device(10.0, name="TIMER")
    api.dampers.add_damper("D1", "TIMER")
    api.hvac_aircoils.add_aircoil("D2", 0.5, coolant_temperature=10.0, coolant_specific_heat=4.186,
                                  coolant_mass_flow=1.0, name="COIL")
    text, back = _roundtrip(api, tmp_path)
    assert "DAMPER=.TRUE., DEVC_ID='TIMER'" in text and "AIRCOIL_ID='COIL'" in text
    assert back.dampers[0].duct_id == "D1" and back.dampers[0].ctrl_id == "TIMER"
    assert back.hvac_aircoils[0].duct_id == "D2" and back.hvac_aircoils[0].effectiveness == 0.5


def test_layout_rule_catches_fds_limits(api):
    _duct_system(api)
    api.fans.add_fan("D1", volume_flow_rate=1.0, name="F1")
    api.hvac_aircoils.add_aircoil("D1", 0.5, name="C1")
    api.hvac_filters.add_filter("D1", node_id="A", name="FL")
    api.fans.add_fan("D2", max_flow=1.0, name="F2")
    api.hvac_nodes.update("C", ambient=True)
    api.hvac_nodes.add_node([5, 5, 1], ambient=True, name="E")
    got = _rules(api, "HvacLayout")
    assert ("HvacLayout", "D1") in got                     # fan and aircoil
    assert ("HvacLayout", "FL") in got                     # filter at a one-duct node
    assert ("HvacLayout", "F2") in got                     # quadratic fan missing MAX_PRESSURE
    assert ("HvacLayout", "E") in got                      # terminal node with no duct


# -- fan curves (HVC-04) ---------------------------------------------------------------------------
def test_quadratic_curve_matches_fds_guide_values():
    pts = quadratic_curve(10.0, 500.0, n=12)
    assert len(pts) == 12
    assert pts[0] == (-10.0, 1000.0)                                       # FDS guide: V=-10 -> 1000 Pa
    assert pts[-1][0] == 17.0 and pts[-1][1] == pytest.approx(500 * (1 - 1.7 ** 2))
    assert all(b[1] <= a[1] for a, b in zip(pts, pts[1:]))                 # pressure falls as flow rises
    assert dict(quadratic_curve(10.0, 500.0, n=40)).get(0.0, 500.0) == 500.0


def test_set_curve_replaces_other_definition_and_validates(api, tmp_path):
    _duct_system(api)
    api.fans.add_fan("D1", volume_flow_rate=2.0, name="F")
    api.fans.set_curve("F", [0, 5, 10], [500, 300, 0])
    assert api.fans.curve("F") == {"kind": "curve", "ramp_id": "F_CURVE", "points": [(0.0, 500.0), (5.0, 300.0), (10.0, 0.0)]}
    fan = api.fans.get("F")
    assert fan.volume_flow_rate is None
    text, back = _roundtrip(api, tmp_path)
    assert "TYPE_ID='FAN', ID='F', RAMP_ID='F_CURVE'" in text and "ID='F_CURVE', T=5.0, F=300.0" in text
    api.fans.set_curve("F", [0, 10], [400, 0])                 # editing again replaces the ramp
    assert len([r for r in api.ramps.all() if r.name == "F_CURVE"]) == 1
    api.history.undo()
    assert api.fans.curve("F")["points"][0] == (0.0, 500.0)
    for flows, pres in (([0, 0], [1, 0]), ([0, 5], [0, 100]), ([0], [1]), ([0, 1, 2], [3, 2])):
        with pytest.raises(ValueError):
            api.fans.set_curve("F", flows, pres)


# -- jet fan (HVC-07) -------------------------------------------------------------------------------
def test_jet_fan_thrust_relations():
    assert jet_fan_thrust(6.0, 1.0) == pytest.approx(1.2 * 36)
    assert jet_fan_flow(jet_fan_thrust(3.0, 0.5), 0.5) == pytest.approx(3.0)
    with pytest.raises(ValueError):
        jet_fan_flow(10, 0)


def test_add_jet_fan_builds_a_valid_cell_aligned_system(api, tmp_path):
    r = api.hvac.add_jet_fan([4.0, 2.0, 2.0], "-y", width=1.0, height=1.0, thrust=50.0, name="JF")
    plate = r["obstruction"]
    assert (plate.y_max - plate.y_min) == pytest.approx(0.2)                       # one cell thick, along the blow axis
    assert r["thrust"] == pytest.approx(50.0) and r["fan"].volume_flow_rate == pytest.approx(r["flow"])
    suction, discharge = r["vents"]                                               # blowing toward -y: suction on the +y face
    assert suction.y_min == pytest.approx(plate.y_max) and discharge.y_min == pytest.approx(plate.y_min)
    assert r["duct"].node_id_1 == r["nodes"][0].name
    text, back = _roundtrip(api, tmp_path)
    assert text.count("SURF_ID='HVAC'") == 2 and not _rules(api, "HvacLayout")
    api.history.undo()
    assert not api.obstructions.all() and not api.vents.all() and not api.hvac_ducts.all() and not api.fans.all()
    for bad in (dict(direction="up", flow=1.0), dict(flow=1.0, thrust=1.0), dict(), dict(flow=-1.0)):
        with pytest.raises(ValueError):
            api.hvac.add_jet_fan([4, 2, 2], **{"direction": "+x", **bad})


# -- fire library and pool fire (FIR-06, FIR-03) ---------------------------------------------------------
def test_t2_curves_and_library_burner(api, tmp_path):
    names = api.fires.names()
    assert {"t2 slow", "t2 medium", "t2 fast", "t2 ultrafast", "steady"} <= set(names)
    it = api.fires.get("t2 fast", peak_kw=1055.0)
    assert it.hrr[0] == 0 and it.peak == 1055.0
    assert it.times[1] > 0 and any(t == pytest.approx(math.sqrt(1055 / 0.04689), abs=0.01) for t in it.times)
    out = api.fires.add_from_library("t2 fast", [1, 2, 1, 2, 0], peak_kw=1000.0, scale=0.5)
    s = out["surface"]
    assert s.heat_release_rate == pytest.approx(500.0) and s.tau_q is None and s.ramp_q == out["ramp"].name
    assert max(out["ramp"].values) == 1.0
    text, _ = _roundtrip(api, tmp_path)
    assert "RAMP_Q=" in text and "TAU_Q" not in text
    api.history.undo()
    assert not api.obstructions.all() and not api.ramps.all() and not api.surfaces.get(s.name)
    with pytest.raises(KeyError):
        api.fires.get("nope")
    with pytest.raises(ValueError):
        api.fires.add_from_library("steady", [1, 1, 1, 2, 0])


def test_saved_fire_survives_undo_and_project_save(api, tmp_path):
    api.fires.save_item("my sofa", [0, 60, 120, 300], [0, 200, 900, 0], source="own test, 2026-10-13")
    assert "my sofa" in api.fires.names() and api.fires.get("my sofa").energy_mj == pytest.approx(
        (0 + 200) / 2 * 60 / 1000 + (200 + 900) / 2 * 60 / 1000 + (900 + 0) / 2 * 180 / 1000)
    p = tmp_path / "m.pyfds"
    Serializer().save(api.project, str(p))
    assert Serializer().load(str(p)).editor.fire_items["my sofa"]["source"].startswith("own test")
    api.history.undo()
    assert "my sofa" not in api.fires.names()
    for bad in (([0, 0], [1, 2]), ([0, 1], [-1, 2]), ([0, 1], [0, 0]), ([0], [1])):
        with pytest.raises(ValueError):
            api.fires.save_item("bad", *bad)
    with pytest.raises(ValueError, match="built-in"):
        api.fires.save_item("steady", [0, 1], [1, 1])


def test_pool_fire_needs_a_liquid_fuel(api, tmp_path):
    api.materials.add(__import__("pyfds.domain.model", fromlist=["Material"]).Material(name="WOOD"))
    with pytest.raises(ValueError, match="liquid fuel"):
        api.fires.add_pool_fire("WOOD", [1, 2, 1, 2, 0])
    api.materials.add_liquid_fuel("HEPTANE", "N-HEPTANE", 98.0, 365.0, 680.0, 2.2)
    r = api.fires.add_pool_fire("HEPTANE", [1, 2, 1, 2, 0], depth=0.02, name="POOL")
    assert r["area"] == pytest.approx(1.0) and r["equivalent_diameter"] == pytest.approx(1.1284, abs=1e-3)
    s = r["surface"]
    assert s.layers[0].material_id == "HEPTANE" and s.layers[0].thickness == 0.02 and s.backing == "INSULATED"
    assert r["obstruction"].surface_ids == ["POOL", "INERT", "INERT"]
    api.history.undo()
    assert not api.surfaces.get("POOL")
    with pytest.raises(KeyError):
        api.fires.add_pool_fire("NOPE", [1, 2, 1, 2, 0])


# -- pyrolysis fit and by-products -----------------------------------------------------------------------
def _arrhenius(temps_c, a, e):
    return [a * math.exp(-e / (pk.R * (t + 273.15))) for t in temps_c]


def test_fit_recovers_known_a_and_e():
    temps = list(range(250, 400, 10))
    fit = pk.fit_arrhenius(temps, _arrhenius(temps, 1e10, 120e3))
    assert fit["E"] == pytest.approx(120e3, rel=1e-6) and fit["A"] == pytest.approx(1e10, rel=1e-4) and fit["r2"] > 0.999999
    with pytest.raises(ValueError, match="at least three"):
        pk.fit_arrhenius([1, 2], [1, 2])
    with pytest.raises(ValueError, match="does not increase"):
        pk.fit_arrhenius([100, 200, 300], [3, 2, 1])


def test_kissinger_round_trip():
    e, a = 150e3, 5e11
    betas = [5.0, 10.0, 20.0, 40.0]
    # peak where beta*E/(R Tp^2) = A exp(-E/(R Tp)); solve by bisection for each heating rate
    peaks = []
    for b in betas:
        lo, hi = 300.0, 900.0
        for _ in range(100):
            mid = (lo + hi) / 2
            f = (b / 60) * e / (pk.R * mid * mid) - a * math.exp(-e / (pk.R * mid))
            lo, hi = (mid, hi) if f > 0 else (lo, mid)
        peaks.append((lo + hi) / 2 - 273.15)
    assert pk.kissinger_activation_energy(betas, peaks) == pytest.approx(e, rel=0.02)
    assert pk.from_peak(betas[1], peaks[1], e)["A"] == pytest.approx(a, rel=0.02)


def test_material_fit_and_byproducts_are_undoable(api, tmp_path):
    from pyfds.domain.model import Material
    api.materials.add(Material(name="PINE", reference_temperature=300.0))
    temps = list(range(250, 400, 10))
    fit = api.materials.fit_pyrolysis("PINE", temps, _arrhenius(temps, 1e8, 100e3), n=1.0)
    m = api.materials.get("PINE")
    assert m.e == pytest.approx(100e3, rel=1e-6) and m.n_s == 1.0
    api.history.undo()
    assert m.e is None
    r = api.materials.set_byproducts("PINE", {"CARBON MONOXIDE": 0.1, "CARBON DIOXIDE": 0.5}, residue=0.2)
    assert r["unaccounted"] == pytest.approx(0.2) and api.materials.byproducts("PINE")["residue"] == 0.2
    text, back = _roundtrip(api, tmp_path)
    assert "SPEC_ID='CARBON MONOXIDE','CARBON DIOXIDE'" in text
    with pytest.raises(ValueError, match="exceed 1"):
        api.materials.set_byproducts("PINE", {"A": 0.9}, residue=0.5)
    out = api.materials.pyrolysis_from_peak("PINE", 10.0, 350.0, activation_energy=100e3, apply=False)
    assert out["A"] > 0 and api.materials.get("PINE").a is None


# -- results summaries (TH-03) ------------------------------------------------------------------------------
def test_activation_table_and_hrr_summary_from_fds_files(tmp_path):
    (tmp_path / "c_devc_ctrl_log.csv").write_text(
        "Time (s),Type,ID,State,Value,Units\n"
        " 1.50000E+00,DEVC,SPK1                                                      ,T, 1.50000E+00,s\n"
        " 1.50000E+00,CTRL,C1                                                        ,T\n"
        " 3.00000E+00,DEVC,SPK1                                                      ,F, 3.00000E+00,s\n"
        " 2.00000E+00,DEVC,SMOKE                                                     ,T, 3.10000E+00,%/m\n")
    (tmp_path / "c_hrr.csv").write_text("s,kW\nTime,HRR\n0,0\n10,100\n20,300\n30,200\n")
    api = FdsApi()
    rows = api.results.activation_table(str(tmp_path), "c")
    assert [(r["id"], r["time"]) for r in rows] == [("C1", 1.5), ("SPK1", 1.5), ("SMOKE", 2.0)]
    assert rows[2]["value"] == 3.1 and rows[2]["units"] == "%/m"
    s = api.results.hrr_summary(str(tmp_path), "c", thresholds_kw=[50, 250, 1000])
    assert s["peak_hrr_kw"] == 300 and s["time_of_peak_s"] == 20
    assert s["total_energy_mj"] == pytest.approx((50 * 10 + 200 * 10 + 250 * 10) / 1000)
    assert s["time_to_reach_kw"] == {50: 10.0, 250: 20.0, 1000: None}
    with pytest.raises(FileNotFoundError):
        api.results.activation_table(str(tmp_path), "other")
    with pytest.raises(ValueError, match="output_dir"):
        api.results.hrr_summary()


def test_activation_table_falls_back_to_the_out_file(tmp_path):
    (tmp_path / "c.out").write_text(
        " DEVICE Activation Times\n\n         1    T1                        T           1.221\n"
        "         3    VISDET                    F          -1.0\n\n CONTROL Activation Times\n\n"
        "Device number Device ID                 Final State Final activiation time (s)\n\n"
        "         1    C1                        T           1.221\n\n Time Stepping Wall Clock Time (s):  3.7\n")
    rows = FdsApi().results.activation_table(str(tmp_path), "c")
    assert [(r["id"], r["type"]) for r in rows] == [("C1", "CTRL"), ("T1", "DEVC")]


# -- egress (TH-08) ---------------------------------------------------------------------------------------------
def test_egress_outputs_and_scenario(api, tmp_path):
    api.vents.add_vent([0, 0, 1, 2, 0, 2], surf_id="OPEN", name="DOOR")
    api.holes.add_hole([4, 4.2, 1, 2, 0, 2], name="H1")
    made = api.egress.add_outputs(1.8)
    assert len(made) == 5 and {s.spec_id for s in made} == {None, "CARBON MONOXIDE", "CARBON DIOXIDE", "OXYGEN"}
    assert api.egress.add_outputs(1.8) == []                               # not duplicated
    text, back = _roundtrip(api, tmp_path)
    assert "QUANTITY='VOLUME FRACTION'" in text and "SPEC_ID='CARBON MONOXIDE'" in text
    assert {s.spec_id for s in back.slices} == {None, "CARBON MONOXIDE", "CARBON DIOXIDE", "OXYGEN"}
    sc = api.egress.scenario(t_start_evac=45.0, groups=[{"id": "G", "count": 20, "start_region": [1, 3, 1, 3, 0, 2]}])
    assert sc.exit_ids == ["DOOR", "H1"] and sc.total_occupants == 20 and sc.t_start_evac == 45.0
    data = api.egress.export(str(tmp_path / "e.json"))
    assert data["exits"][0]["id"] == "DOOR" and (tmp_path / "e.json").exists()
    api.history.undo()
    assert not api.slices.all()
    with pytest.raises(ValueError, match="outside"):
        api.egress.add_outputs(9.0)


def test_agent_tools_for_hvac_fire_and_results(api, tmp_path):
    d = AgentToolDispatcher(api)
    _duct_system(api)
    api.fans.add_fan("D1", volume_flow_rate=1.0, name="F")
    d.call("set_fan_curve", {"fan": "F", "flows": [0, 5], "pressures": [300, 0]})
    assert d.call("get_fan_curve", {"fan": "F"})["kind"] == "curve"
    assert "steady" in d.call("list_fires", {})
    d.call("add_fire_from_library", {"item": "t2 slow", "xb": [1, 2, 1, 2, 0], "peak_kw": 500})
    assert d.call("add_jet_fan", {"center": [6, 2, 2], "flow": 3.0})["flow"] == 3.0
    d.call("add_egress_outputs", {})
    (tmp_path / "c_hrr.csv").write_text("s,kW\nTime,HRR\n0,0\n10,100\n")
    assert d.call("hrr_summary", {"output_dir": str(tmp_path), "chid": "c"})["peak_hrr_kw"] == 100
