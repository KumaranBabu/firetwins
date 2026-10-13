"""B4 (part 1) - custom smoke, reaction table, particle kinds, device systems (nozzle, dry pipe, beam, FED,
aspiration, HVAC output, stop controls), multi-edit, new validation rules."""
from __future__ import annotations

import pytest

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh(ijk=(40, 40, 20), xb=(0, 4, 0, 4, 0, 2), name="M")
    return a


def _roundtrip(api, tmp_path):
    f = tmp_path / "m.fds"
    FdsWriter().write(api.project, str(f))
    return f.read_text(), FdsParser().parse(str(f))


def _rules(api):
    return {(r.rule, r.entity_name) for r in api.validation.validate().results}


# -- custom smoke (RXN-05) -------------------------------------------------------------------
def test_set_smoke_writes_soot_species_and_visibility_and_round_trips(api, tmp_path):
    api.reactions.add_simple_reaction("PROPANE", 46000.0, name="R1")
    got = api.reactions.set_smoke(mass_extinction_coefficient=5500.0, soot_yield=0.05, visibility_factor=8.0,
                                  maximum_visibility=20.0)
    assert got["mass_extinction_coefficient"] == 5500.0 and got["soot_yield"] == {"R1": 0.05}
    text, back = _roundtrip(api, tmp_path)
    assert "MASS_EXTINCTION_COEFFICIENT=5500" in text and "VISIBILITY_FACTOR=8" in text
    soot = next(s for s in back.species if s.name == "SOOT")
    assert soot.mass_extinction_coefficient == 5500.0 and soot.lumped_component_only
    assert back.misc.visibility_factor == 8.0 and back.misc.maximum_visibility == 20.0
    api.history.undo()
    assert api.reactions.smoke()["mass_extinction_coefficient"] is None and api.project.misc.visibility_factor is None


def test_set_smoke_rejects_nonsense(api):
    with pytest.raises(ValueError, match="positive"):
        api.reactions.set_smoke(mass_extinction_coefficient=-1)
    with pytest.raises(ValueError, match="no reaction"):
        api.reactions.set_smoke(soot_yield=0.1)
    api.reactions.add_simple_reaction("PROPANE", 46000.0)
    with pytest.raises(ValueError, match="between 0 and 1"):
        api.reactions.set_smoke(soot_yield=1.5)


# -- reaction table (RXN-03) -----------------------------------------------------------------
def test_reaction_table_and_edit(api):
    api.species.add_species("PROPANE")
    r = api.reactions.add_complex_reaction({"PROPANE": 1, "OXYGEN": 5}, {"CARBON DIOXIDE": 3, "WATER VAPOR": 4})
    t = api.reactions.stoichiometry(r)
    assert t["type"] == "complex" and {"species": "OXYGEN", "coefficient": 5.0} in t["reactants"]
    api.reactions.set_stoichiometry(r, {"PROPANE": 1, "OXYGEN": 5}, {"CARBON DIOXIDE": 3, "WATER VAPOR": 4},
                                    exponents={"PROPANE": 1.0})
    assert api.reactions.stoichiometry(r)["exponents"] == {"PROPANE": 1.0}
    with pytest.raises(ValueError):
        api.reactions.set_stoichiometry(r, {"PROPANE": 1}, {"CARBON DIOXIDE": 3})       # does not balance
    api.history.undo()
    assert api.reactions.stoichiometry(r)["exponents"] == {}
    simple = api.reactions.add_simple_reaction("PROPANE", 46000.0, name="S")
    assert api.reactions.stoichiometry(simple)["type"] == "simple"


# -- particle kinds (PRT-01) -----------------------------------------------------------------
def test_particle_kinds_and_round_trip(api, tmp_path):
    api.surfaces.add_typed("basic", name="LEAF")
    t = api.particles.add_tracer("TR")
    d = api.particles.add_droplet("DR", diameter=300.0, monodisperse=True, initial_temperature=20.0)
    s = api.particles.add_solid_particle("LEAF", "SO", stationary=True, target_only=True)
    assert [api.particles.kind(x) for x in (t, d, s)] == ["tracer", "droplet", "solid"]
    text, back = _roundtrip(api, tmp_path)
    assert "MASSLESS=.TRUE." in text and "MONODISPERSE=.TRUE." in text and "TARGET_ONLY=.TRUE." in text
    kinds = {p.name: p.kind for p in back.particles}
    assert kinds == {"TR": "tracer", "DR": "droplet", "SO": "solid"}
    assert next(p for p in back.particles if p.name == "SO").stationary
    for bad in (lambda: api.particles.add_tracer(spec_id="WATER VAPOR"),
                lambda: api.particles.add_droplet(massless=True),
                lambda: api.particles.add_solid_particle("")):
        with pytest.raises(ValueError):
            bad()


def test_particle_rule_flags_contradictions(api):
    api.particles.add_particle_class(name="BAD", massless=True, spec_id="WATER VAPOR")
    assert ("ParticleKind", "BAD") in _rules(api)


# -- nozzle, link, dry pipe (DEV-08, DEV-09) --------------------------------------------------
def test_nozzle_needs_a_spray_property(api):
    api.props.add_prop("NOPART")
    with pytest.raises(ValueError, match="part_id"):
        api.devices.add_nozzle([1, 1, 1.9], "NOPART")
    api.particles.add_droplet("WATER")
    api.props.add_prop("NOZ", part_id="WATER", flow_rate=60.0, k_factor=80.0, orifice_diameter=0.012,
                       pressure_ramp="PR")
    n = api.devices.add_nozzle([1, 1, 1.9], "NOZ", orientation=[0, 0, -1])
    assert n.quantity == "TIME" and n.prop_id == "NOZ"
    with pytest.raises(KeyError):
        api.devices.add_nozzle([1, 1, 1.9], "NOZ", ctrl_id="MISSING")


def test_dry_pipe_sprinkler_builds_link_delay_nozzle_in_one_step(api, tmp_path):
    api.particles.add_droplet("WATER")
    api.props.add_prop("NOZ", part_id="WATER", flow_rate=60.0)
    parts = api.devices.add_dry_pipe_sprinkler([2, 2, 1.9], "NOZ", delay=30.0, name="SPK")
    assert parts["link"].quantity == "LINK TEMPERATURE" and parts["control"].function_type == "TIME_DELAY"
    assert parts["control"].delay == 30.0 and parts["nozzle"].ctrl_id == parts["control"].name
    text, _ = _roundtrip(api, tmp_path)
    assert "FUNCTION_TYPE='TIME_DELAY'" in text and "QUANTITY='CONTROL'" in text and "ID='SPK_link'" in text
    api.history.undo()
    assert not api.devices.all() and not api.controls.all() and not api.props.get("LINK")
    with pytest.raises(ValueError):
        api.devices.add_dry_pipe_sprinkler([2, 2, 1.9], "NOZ", delay=-1)


def test_sprinkler_link_makes_a_property_when_none_given(api):
    d = api.devices.add_sprinkler_link([1, 1, 1.9], rti=30.0, activation_temperature=68.0)
    p = api.props.get(d.prop_id)
    assert (p.rti, p.activation_temperature, p.quantity) == (30.0, 68.0, "LINK TEMPERATURE")
    api.props.add_prop("OTHER", quantity="CHAMBER OBSCURATION")
    with pytest.raises(ValueError, match="thermal link"):
        api.devices.add_sprinkler_link([1, 1, 1.9], "OTHER")


# -- beam detector (DEV-10) -------------------------------------------------------------------
def test_beam_detector_writes_xb_without_xyz(api, tmp_path):
    b = api.devices.add_beam_detector([0.5, 3.5, 2, 2, 1.8, 1.8], setpoint=33.0, name="BEAM1")
    text, back = _roundtrip(api, tmp_path)
    line = next(ln for ln in text.splitlines() if "ID='BEAM1'" in ln)
    assert "XB=0.5,3.5,2.0,2.0,1.8,1.8" in line and "XYZ" not in line and "PATH OBSCURATION" in line
    assert back.devices[0].xb == (0.5, 3.5, 2.0, 2.0, 1.8, 1.8) and b.setpoint == 33.0
    with pytest.raises(ValueError, match="zero length"):
        api.devices.add_beam_detector([1, 1, 1, 1, 1, 1])
    with pytest.raises(ValueError, match="percentage"):
        api.devices.add_beam_detector([0, 1, 0, 0, 1, 1], setpoint=150)
    t = api.devices.add_beam_detector([0, 1, 0, 0, 1, 1], quantity="TRANSMISSION")
    assert t.trip_direction == -1


# -- FED (DEV-14) ------------------------------------------------------------------------------
def test_fed_device_shares_an_activity_property(api, tmp_path):
    a = api.devices.add_fed_device([1, 1, 1.8], activity=3)
    b = api.devices.add_fed_device([2, 2, 1.8], activity=3)
    f = api.devices.add_fed_device([2, 2, 1.8], quantity="FIC")
    assert a.prop_id == b.prop_id and f.prop_id is None
    assert api.props.get(a.prop_id).fed_activity == 3
    text, back = _roundtrip(api, tmp_path)
    assert "FED_ACTIVITY=3" in text and "QUANTITY='FED'" in text
    assert next(p for p in back.props if p.name == a.prop_id).fed_activity == 3
    with pytest.raises(ValueError):
        api.devices.add_fed_device([1, 1, 1], activity=4)


# -- aspiration (DEV-15) ------------------------------------------------------------------------
def test_aspiration_system_round_trips(api, tmp_path):
    r = api.devices.add_aspiration_system(
        [3, 3, 1.5], [{"xyz": [1, 1, 1.9], "flowrate": 0.1, "delay": 20}, {"xyz": [2, 2, 1.9], "flowrate": 0.2}],
        setpoint=0.02, bypass_flowrate=0.4, name="ASP")
    assert [s.devc_id for s in r["samplers"]] == ["ASP", "ASP"] and r["detector"].quantity == "ASPIRATION"
    text, back = _roundtrip(api, tmp_path)
    assert "BYPASS_FLOWRATE=0.4" in text and "DEVC_ID='ASP'" in text and "FLOWRATE=0.1" in text
    s1 = next(d for d in back.devices if d.name == "ASP_sampler_1")
    assert (s1.quantity, s1.spec_id, s1.flowrate, s1.delay) == ("DENSITY", "SOOT", 0.1, 20.0)
    assert not [x for x in _rules(api) if x[0] == "DeviceSystem"]
    with pytest.raises(ValueError, match="flowrate"):
        api.devices.add_aspiration_system([0, 0, 1], [{"xyz": [1, 1, 1], "flowrate": 0}])
    with pytest.raises(ValueError, match="at least one"):
        api.devices.add_aspiration_system([0, 0, 1], [])
    api.history.undo()
    assert len(api.devices.all()) == 0


def test_rule_flags_a_sampler_pointing_at_nothing(api):
    api.devices.add_device("DENSITY", [1, 1, 1], name="S", spec_id="SOOT", devc_id="NOPE", flowrate=0.1)
    assert ("DeviceSystem", "S") in _rules(api)


# -- HVAC output (HVC-06, OUT-08) ---------------------------------------------------------------
def _network(api):
    api.hvac_nodes.add_node([0, 0, 1], name="N1")
    api.hvac_nodes.add_node([1, 0, 1], name="N2")
    api.hvac_ducts.add_duct("N1", "N2", name="D1")


def test_hvac_output_devices_have_no_xyz_and_check_ids(api, tmp_path):
    _network(api)
    a = api.devices.add_hvac_output("DUCT VOLUME FLOW", duct_id="D1", name="Q")
    api.devices.add_hvac_output("NODE PRESSURE DIFFERENCE", node_id=["N1", "N2"], name="DP")
    api.devices.add_hvac_output("DUCT MASS FRACTION", duct_id="D1", spec_id="SOOT", name="Y")
    text, back = _roundtrip(api, tmp_path)
    q_line = next(ln for ln in text.splitlines() if "ID='Q'" in ln)
    assert "DUCT_ID='D1'" in q_line and "XYZ" not in q_line
    dp = next(d for d in back.devices if d.name == "DP")
    assert dp.node_id == ["N1", "N2"] and a.duct_id == "D1"
    for bad, exc in ((lambda: api.devices.add_hvac_output("DUCT VOLUME FLOW"), ValueError),
                     (lambda: api.devices.add_hvac_output("DUCT VOLUME FLOW", duct_id="NOPE"), KeyError),
                     (lambda: api.devices.add_hvac_output("NODE PRESSURE DIFFERENCE", node_id=["N1"]), ValueError),
                     (lambda: api.devices.add_hvac_output("DUCT MASS FRACTION", duct_id="D1"), ValueError),
                     (lambda: api.devices.add_hvac_output("DUCT CELL TEMPERATURE", duct_id="D1"), ValueError),
                     (lambda: api.devices.add_hvac_output("TEMPERATURE", duct_id="D1"), ValueError)):
        with pytest.raises(exc):
            bad()


# -- time device, stop controls (DEV-16, CTL-05) -----------------------------------------------
def test_stop_when_and_stop_at(api, tmp_path):
    api.devices.add_thermocouple([1, 1, 1], "TC", setpoint=500.0)
    k = api.devices.stop_when("TC", restart=True)
    assert k.function_type == "KILL" and {c.function_type for c in api.controls.all()} == {"KILL", "RESTART"}
    api.devices.stop_at(120.0)
    text, _ = _roundtrip(api, tmp_path)
    assert "FUNCTION_TYPE='KILL'" in text and "QUANTITY='TIME'" in text and "SETPOINT=120" in text
    with pytest.raises(KeyError):
        api.devices.stop_when("NOPE")
    n = len(api.controls.all())
    api.history.undo()                                     # stop_at is one step
    assert len(api.controls.all()) == n - 1


# -- multi edit (DEV-18) --------------------------------------------------------------------------
def test_update_many_is_one_undo_step_and_all_or_nothing(api):
    ds = [api.devices.add_thermocouple([i, 1, 1], f"T{i}") for i in range(3)]
    api.devices.update_many(ds[:2] + ["T2"], setpoint=80.0, statistics="MAX")
    assert [d.setpoint for d in ds] == [80.0] * 3
    api.history.undo()
    assert [d.setpoint for d in ds] == [None] * 3
    with pytest.raises(AttributeError):
        api.devices.update_many(["T0", "T1"], nonsense=1)
    with pytest.raises(KeyError):
        api.devices.update_many(["T0", "NOPE"], setpoint=1.0)
    with pytest.raises(ValueError, match="rename"):
        api.devices.update_many(["T0"], name="X")
    assert ds[0].setpoint is None


# -- agent tools ---------------------------------------------------------------------------------
def test_agent_tools_drive_the_new_systems(api, tmp_path):
    d = AgentToolDispatcher(api)
    api.reactions.add_simple_reaction("PROPANE", 46000.0)
    d.call("set_smoke", {"mass_extinction_coefficient": 6000.0})
    assert d.call("get_smoke", {})["mass_extinction_coefficient"] == 6000.0
    d.call("add_tracer_particles", {"name": "TR"})
    d.call("add_beam_detector", {"xb_line": [0, 3, 1, 1, 1.5, 1.5]})
    d.call("add_fed_device", {"xyz": [1, 1, 1.8]})
    d.call("add_aspiration_system", {"detector_xyz": [1, 1, 1], "samplers": [{"xyz": [1, 1, 1.9], "flowrate": 0.1}]})
    d.call("add_time_device", {"setpoint": 10.0, "name": "TIMER"})
    d.call("stop_when", {"device": "TIMER"})
    assert d.call("update_devices", {"names": ["TIMER"], "fields": {"setpoint": 20.0}}) == ["TIMER"]
    assert api.devices.get("TIMER").setpoint == 20.0
